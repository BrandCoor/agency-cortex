"""Meta webhook ucu.

Bu adres internete aciktir; herkes istek gonderebilir. Uc katmanli koruma:
1. Kurulum dogrulamasi (GET) - verify token kontrolu
2. Imza dogrulama (POST)     - istek gercekten Meta'dan mi geliyor
3. Tekrar koruma             - ayni olay iki kez islenmez
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status

from app.api.deps import DbSession
from app.core.config import get_settings
from app.core.logging_config import get_logger
from app.services.webhook_guard import record_event, verify_signature, verify_token_matches

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhook"])
log = get_logger("webhook_api")


@router.get("/meta", summary="Meta webhook kurulum dogrulamasi")
def verify_webhook(
    hub_mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    hub_challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
    hub_verify_token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
) -> Response:
    """Meta, webhook adresini kurarken bu ucu cagirir.

    Dogru verify token gonderilirse challenge degeri aynen geri donulur.
    """
    settings = get_settings()

    if not verify_token_matches(
        sent=hub_verify_token, expected=settings.meta_webhook_verify_token
    ):
        log.warning("webhook_dogrulama_reddedildi", hub_mode=hub_mode)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Verify token hatali."
        )

    if hub_mode != "subscribe" or not hub_challenge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Gecersiz dogrulama istegi."
        )

    log.info("webhook_dogrulandi")
    # Meta duz metin bekler.
    return Response(content=hub_challenge, media_type="text/plain")


@router.post("/meta", summary="Meta olay bildirimi")
async def receive_webhook(
    request: Request,
    db: DbSession,
    x_hub_signature_256: Annotated[str | None, Header(alias="x-hub-signature-256")] = None,
) -> dict:
    """Meta'dan gelen olay bildirimini alir.

    Imzasi dogrulanmayan istek ISLENMEZ. Ancak reddedilen istek de kayda
    gecer; boylece sahte istek denemeleri gorunur olur.
    """
    settings = get_settings()
    raw_body = await request.body()

    imza_gecerli = verify_signature(
        payload=raw_body,
        header_value=x_hub_signature_256,
        app_secret=settings.meta_webhook_app_secret,
    )

    if not imza_gecerli:
        log.warning(
            "webhook_imza_gecersiz",
            body_size=len(raw_body),
            has_signature_header=bool(x_hub_signature_256),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Imza dogrulanamadi."
        )

    try:
        payload = json.loads(raw_body or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Gecersiz JSON."
        ) from exc

    # Olay kimligi: Meta bir kimlik gondermezse govdenin parmak izi kullanilir.
    # Boylece ayni govde iki kez gelse de tekrar islenmez.
    event_id = _extract_event_id(payload, raw_body)

    _, yeni_mi = record_event(
        db,
        provider="meta",
        external_event_id=event_id,
        payload=payload,
        signature_valid=True,
    )
    db.commit()

    if not yeni_mi:
        # Meta'ya yine 200 donulur; aksi halde tekrar tekrar gonderir.
        return {"status": "duplicate_ignored", "event_id": event_id}

    return {"status": "accepted", "event_id": event_id}


def _extract_event_id(payload: dict, raw_body: bytes) -> str:
    """Olay icin kararli bir kimlik uretir."""
    entry = payload.get("entry")
    if isinstance(entry, list) and entry:
        ilk = entry[0]
        if isinstance(ilk, dict):
            entry_id = ilk.get("id")
            zaman = ilk.get("time")
            if entry_id and zaman is not None:
                return f"{entry_id}:{zaman}"
    return hashlib.sha256(raw_body).hexdigest()
