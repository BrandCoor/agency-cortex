"""Webhook guvenligi: imza dogrulama ve tekrar koruma (idempotency).

Webhook adresi internete aciktir; herkes istek gonderebilir. Iki koruma
zorunludur:

1. IMZA: Istegin gercekten Meta'dan geldigini kanitlar. Imzasi dogrulanmayan
   istek islenmez.
2. TEKRAR KORUMA: Meta ayni bildirimi birden fazla kez gonderebilir. Ayni olay
   iki kez islenirse veriler bozulur.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models.ops import WebhookEvent

log = get_logger("webhook")


def verify_signature(*, payload: bytes, header_value: str | None, app_secret: str) -> bool:
    """Meta'nin imza basligini dogrular.

    Beklenen bicim: "sha256=<onaltilik ozet>".
    Karsilastirma `compare_digest` ile yapilir; boylece yanit suresinden
    imzanin ne kadari dogru oldugu anlasilamaz (zamanlama saldirisi).
    """
    if not header_value or not app_secret:
        return False

    algoritma, _, gonderilen = header_value.partition("=")
    if algoritma != "sha256" or not gonderilen:
        return False

    beklenen = hmac.new(
        app_secret.encode("utf-8"), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(beklenen, gonderilen)


def verify_token_matches(*, sent: str | None, expected: str) -> bool:
    """Webhook kurulum dogrulamasindaki verify token kontrolu."""
    if not sent or not expected:
        return False
    return hmac.compare_digest(sent, expected)


def record_event(
    db: Session,
    *,
    provider: str,
    external_event_id: str,
    payload: dict,
    signature_valid: bool,
    workspace_id: uuid.UUID | None = None,
) -> tuple[WebhookEvent, bool]:
    """Olayi kaydeder.

    Doner: (kayit, yeni_mi). `yeni_mi` False ise bu olay daha once islenmistir
    ve tekrar islenmemelidir.

    Tekrar korumasi veritabani benzersizlik kisiti ile saglanir; iki es zamanli
    istek gelse bile yalnizca biri yeni kayit olusturabilir.
    """
    event = WebhookEvent(
        workspace_id=workspace_id,
        provider=provider,
        external_event_id=external_event_id,
        received_at=datetime.now(UTC),
        signature_valid=signature_valid,
        payload=payload,
    )

    # SAVEPOINT icinde denenir. Kayit zaten varsa YALNIZCA bu ekleme geri
    # alinir; ayni islemde yapilmis diger degisiklikler korunur.
    # (Duz `db.rollback()` kullanilsaydi tum islem geri alinir ve o ana
    # kadar yapilan is kaybolurdu.)
    try:
        with db.begin_nested():
            db.add(event)
            db.flush()
    except IntegrityError:
        # SAVEPOINT geri alindiginda basarisiz nesne oturumdan zaten
        # cikarilir; ayrica expunge etmek gerekmez.
        mevcut = (
            db.query(WebhookEvent)
            .filter(
                WebhookEvent.provider == provider,
                WebhookEvent.external_event_id == external_event_id,
            )
            .one()
        )
        log.info(
            "webhook_tekrar_geldi",
            provider=provider,
            external_event_id=external_event_id,
        )
        return mevcut, False

    log.info(
        "webhook_kaydedildi",
        provider=provider,
        external_event_id=external_event_id,
        signature_valid=signature_valid,
    )
    return event, True
