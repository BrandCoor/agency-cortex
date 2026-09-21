"""Panelden girilen sistem ayarlarini okur ve yazar.

TASARIM:
- Deger veritabaninda YALNIZCA sifreli durur (Fernet).
- Okuma sirasinda cozulur; cagiran taraf dogrudan kullanir.
- Panel tam degeri HICBIR ZAMAN geri gostermez; yalnizca "tanimli mi" ve
  son dort karakter gosterilir.
- Veritabaninda deger yoksa ortam degiskenine duser. Boylece sunucuda
  tanimli degerler calismaya devam eder.
"""

from __future__ import annotations

import os
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.core.security import decrypt_secret, encrypt_secret
from app.models.ops import SystemSetting

log = get_logger("sistem_ayarlari")


class AyarTanimi:
    """Panelde gosterilecek bir ayarin tanimi."""

    def __init__(self, anahtar: str, etiket: str, aciklama: str, *, gizli: bool = True):
        self.anahtar = anahtar
        self.etiket = etiket
        self.aciklama = aciklama
        # gizli=False olanlar (surum, adres gibi) panelde acikca gosterilir.
        self.gizli = gizli


# Panelde gosterilen ayarlar. Sira, doldurma sirasini da anlatir.
AYARLAR: list[AyarTanimi] = [
    AyarTanimi(
        "ANTHROPIC_API_KEY", "Claude API anahtarı",
        "İçerik senaryoları ve raporlar bu anahtarla üretilir. "
        "console.anthropic.com adresinden alınır.",
    ),
    AyarTanimi(
        "GEMINI_API_KEY", "Gemini API anahtarı",
        "İsteğe bağlı. Toplu sınıflandırma ve özetleme için kullanılacak.",
    ),
    AyarTanimi(
        "MANUS_API_KEY", "Manus API anahtarı",
        "Rakip ve trend araştırması için. Adres doğrulanmadan kullanılmayacak.",
    ),
    AyarTanimi(
        "META_APP_ID", "Meta uygulama kimliği",
        "Instagram/Facebook bağlantısı için. developers.facebook.com üzerindeki "
        "uygulamanızın kimliği. Gizli değildir ama burada tutulur.",
        gizli=False,
    ),
    AyarTanimi(
        "META_APP_SECRET", "Meta uygulama gizli anahtarı",
        "Instagram/Facebook bağlantısı için. Bu değer gizlidir.",
    ),
    AyarTanimi(
        "META_API_VERSION", "Meta API sürümü",
        "Örn: v21.0 — Meta'nın resmî dokümanından alınmalı, tahmin edilmemeli.",
        gizli=False,
    ),
    AyarTanimi(
        "META_AUTHORIZE_URL", "Meta izin adresi",
        "İzin ekranının tam adresi. Resmî dokümandan alınmalı.",
        gizli=False,
    ),
    AyarTanimi(
        "META_TOKEN_URL", "Meta anahtar değişim adresi",
        "İzin kodunun anahtara çevrildiği adres. Resmî dokümandan alınmalı.",
        gizli=False,
    ),
    AyarTanimi(
        "META_GRAPH_BASE_URL", "Meta Graph API adresi",
        "Veri çekilen ana adres. Resmî dokümandan alınmalı.",
        gizli=False,
    ),
    AyarTanimi(
        "META_SCOPES", "Meta izin listesi",
        "Virgülle ayrılmış izin adları. Resmî dokümandan alınmalı; "
        "tahminle yazılırsa bağlantı yanlış izinlerle kurulur.",
        gizli=False,
    ),
]

AYAR_ANAHTARLARI = {a.anahtar for a in AYARLAR}


def deger_oku(db: Session, anahtar: str) -> str | None:
    """Ayari once veritabanindan, yoksa ortam degiskeninden okur."""
    kayit = db.execute(
        select(SystemSetting).where(SystemSetting.anahtar == anahtar)
    ).scalar_one_or_none()
    if kayit is not None:
        try:
            return decrypt_secret(kayit.sifreli_deger)
        except Exception:  # noqa: BLE001 - cozulemeyen deger yokmus gibi davranir
            # Sifre cozulemiyorsa (ornegin ENCRYPTION_KEY degistiyse) degeri
            # uydurmak yerine "tanimsiz" deriz. Sessizce yanlis deger
            # dondurmek, teshisi imkansiz hatalara yol acar.
            log.error("ayar_cozulemedi", anahtar=anahtar)
            return None
    return os.environ.get(anahtar) or None


def deger_yaz(db: Session, anahtar: str, deger: str, *, user_id: uuid.UUID | None) -> None:
    """Ayari sifreleyerek kaydeder. Deger loglanmaz."""
    if anahtar not in AYAR_ANAHTARLARI:
        raise ValueError(f"Bilinmeyen ayar: {anahtar}")
    deger = deger.strip()
    if not deger:
        raise ValueError("Değer boş olamaz.")

    kayit = db.execute(
        select(SystemSetting).where(SystemSetting.anahtar == anahtar)
    ).scalar_one_or_none()
    if kayit is None:
        kayit = SystemSetting(anahtar=anahtar, sifreli_deger="")
        db.add(kayit)

    kayit.sifreli_deger = encrypt_secret(deger)
    kayit.son_dort = deger[-4:] if len(deger) >= 4 else None
    kayit.degistiren_user_id = user_id
    # Yalnizca HANGI ayarin degistigi loglanir; degerin kendisi asla.
    log.info("ayar_guncellendi", anahtar=anahtar, user_id=str(user_id) if user_id else None)


def deger_sil(db: Session, anahtar: str) -> bool:
    kayit = db.execute(
        select(SystemSetting).where(SystemSetting.anahtar == anahtar)
    ).scalar_one_or_none()
    if kayit is None:
        return False
    db.delete(kayit)
    log.info("ayar_silindi", anahtar=anahtar)
    return True


def durum_listesi(db: Session) -> list[dict]:
    """Panelde gosterilecek durum. TAM DEGER ICERMEZ."""
    kayitlar = {
        k.anahtar: k
        for k in db.execute(select(SystemSetting)).scalars().all()
    }
    satirlar = []
    for tanim in AYARLAR:
        kayit = kayitlar.get(tanim.anahtar)
        ortamda = bool(os.environ.get(tanim.anahtar))
        satirlar.append(
            {
                "anahtar": tanim.anahtar,
                "etiket": tanim.etiket,
                "aciklama": tanim.aciklama,
                "gizli": tanim.gizli,
                "tanimli": kayit is not None or ortamda,
                "kaynak": "panel" if kayit is not None else ("sunucu" if ortamda else None),
                "son_dort": kayit.son_dort if kayit else None,
                "guncellendi": kayit.updated_at if kayit else None,
            }
        )
    return satirlar
