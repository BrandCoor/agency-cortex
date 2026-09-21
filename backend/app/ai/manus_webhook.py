"""Manus webhook imza dogrulamasi.

Her deger resmi dokumandan (open.manus.ai/docs/v2/webhooks-security):
  Algoritma      : RSA-SHA256, 2048-bit
  Basliklar      : X-Webhook-Signature , X-Webhook-Timestamp
  Imzalanan icerik: {timestamp}.{url}.{body_sha256_hex}
  Zaman penceresi : 5 dakika
  Public key      : GET /v2/webhook.publicKey (cache edilmeli)

NEDEN IMZA DOGRULAMASI SART:
Webhook adresi internete aciktir. Dogrulama yapilmazsa adresi bilen herkes
sahte "gorev tamamlandi" bildirimi gonderip sisteme uydurma arastirma
sonucu sokabilir.
"""

from __future__ import annotations

import base64
import hashlib
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.core.logging_config import get_logger

log = get_logger("manus_webhook")

# Kaynak: open.manus.ai/docs/v2/webhooks-security
IMZA_BASLIGI = "X-Webhook-Signature"
ZAMAN_BASLIGI = "X-Webhook-Timestamp"
ZAMAN_PENCERESI_SANIYE = 300  # 5 dakika

# Kaynak: open.manus.ai/docs/v2/webhooks-overview
OLAY_GOREV_OLUSTURULDU = "task_created"
OLAY_GOREV_DURDU = "task_stopped"
DURMA_NEDENI_BITTI = "finish"
DURMA_NEDENI_SORU = "ask"

# Callback endpoint'i 10 saniye icinde HTTP 200 donmelidir.
# Kaynak: open.manus.ai/docs/v2/webhooks-overview
CALLBACK_YANIT_SURESI_SANIYE = 10


class WebhookImzaHatasi(Exception):
    """Imza gecersiz, eksik veya zaman penceresi disinda."""


def imzayi_dogrula(
    *,
    public_key_pem: str,
    url: str,
    body: bytes,
    signature_b64: str,
    timestamp: str,
    simdi: int | None = None,
) -> None:
    """Imza gecerli degilse WebhookImzaHatasi firlatir.

    Sessizce False DONMEZ: cagiran tarafin hatayi gormezden gelmesi
    zorlastirilir.
    """
    if not signature_b64 or not timestamp:
        raise WebhookImzaHatasi("İmza veya zaman damgası başlığı eksik.")

    try:
        zaman = int(timestamp)
    except ValueError as hata:
        raise WebhookImzaHatasi("Zaman damgası sayı değil.") from hata

    # Tekrar oynatma (replay) korumasi: eski bir istegin tekrar
    # gonderilmesini engeller.
    an = simdi if simdi is not None else int(time.time())
    if abs(an - zaman) > ZAMAN_PENCERESI_SANIYE:
        raise WebhookImzaHatasi(
            f"Zaman damgası {ZAMAN_PENCERESI_SANIYE} saniyelik pencere dışında."
        )

    # Imzalanan icerik dokumanda tanimlanan bicimde kurulur.
    govde_ozeti = hashlib.sha256(body).hexdigest()
    imzalanan = f"{zaman}.{url}.{govde_ozeti}".encode()

    try:
        anahtar = serialization.load_pem_public_key(public_key_pem.encode())
    except Exception as hata:  # noqa: BLE001 - bozuk anahtar tek bir hataya cevrilir
        raise WebhookImzaHatasi("Genel anahtar okunamadı.") from hata

    if not isinstance(anahtar, rsa.RSAPublicKey):
        raise WebhookImzaHatasi("Genel anahtar RSA değil.")

    try:
        imza = base64.b64decode(signature_b64)
    except Exception as hata:  # noqa: BLE001
        raise WebhookImzaHatasi("İmza base64 olarak çözülemedi.") from hata

    try:
        anahtar.verify(imza, imzalanan, padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature as hata:
        raise WebhookImzaHatasi("İmza doğrulanamadı.") from hata


def olayi_coz(govde: dict) -> dict:
    """Webhook govdesinden anlamli alanlari cikarir.

    task_stopped + stop_reason=finish  -> nihai sonuc hazir
    task_stopped + stop_reason=ask     -> kullanici girdisi bekleniyor
    Kaynak: open.manus.ai/docs/v2/webhooks-overview
    """
    olay = govde.get("event") or govde.get("type")
    durma_nedeni = govde.get("stop_reason")
    return {
        "olay": olay,
        "task_id": govde.get("task_id"),
        "durma_nedeni": durma_nedeni,
        "sonuc_hazir": olay == OLAY_GOREV_DURDU and durma_nedeni == DURMA_NEDENI_BITTI,
        "girdi_bekliyor": olay == OLAY_GOREV_DURDU and durma_nedeni == DURMA_NEDENI_SORU,
        "structured_output": govde.get("structured_output"),
    }
