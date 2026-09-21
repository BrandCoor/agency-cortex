"""Panelden girilen ayarlarin GERCEKTEN calistigini dogrular.

NEDEN GEREKLI:
Bir anahtari kaydetmek, calistigi anlamina gelmez. Yanlis kopyalanmis,
suresi dolmus veya yetkisi yetersiz bir anahtar sessizce durur ve sorun
ancak aylar sonra, gercek bir is sirasinda ortaya cikar.

KURAL: Sinama sonucu HICBIR ZAMAN anahtarin kendisini icermez.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.services.sistem_ayarlari import deger_oku

log = get_logger("baglanti_sinama")


def manus_sina(db: Session) -> tuple[bool, str]:
    """Manus anahtarini gercek bir API cagrisiyla dogrular."""
    from app.ai.manus import ManusProvider

    anahtar = deger_oku(db, "MANUS_API_KEY")
    if not anahtar:
        return False, "Manus API anahtarı girilmemiş."
    return ManusProvider(api_key=anahtar).baglantiyi_sina()


def meta_sina(db: Session) -> tuple[bool, str]:
    """Meta ayarlarini BICIM olarak denetler.

    DIKKAT - BU CANLI BIR SINAMA DEGILDIR.
    Meta'nin uygulama kimlik bilgilerini tek basina dogrulayan salt okuma
    bir ucu, elimizdeki resmi referansta TANIMLI DEGIL. Tahminle bir uc
    cagirmak yerine yalnizca bicim denetimi yapiyoruz ve bunu acikca
    soyluyoruz. Gercek dogrulama, ilk hesap baglandiginda olur.
    """
    eksikler = []
    for anahtar, etiket in [
        ("META_APP_ID", "Uygulama kimliği"),
        ("META_APP_SECRET", "Uygulama gizli anahtarı"),
    ]:
        if not deger_oku(db, anahtar):
            eksikler.append(etiket)

    from app.core.config import get_settings

    ayarlar = get_settings()
    if not ayarlar.meta_redirect_uri:
        eksikler.append("Yönlendirme adresi (META_REDIRECT_URI)")

    if eksikler:
        return False, "Eksik: " + ", ".join(eksikler)

    app_id = deger_oku(db, "META_APP_ID") or ""
    if not app_id.isdigit():
        return False, "Uygulama kimliği yalnızca rakamlardan oluşmalı."

    return True, (
        "Biçim doğru görünüyor. NOT: Bu canlı bir sınama değildir — "
        "Meta'nın kimlik bilgilerini tek başına doğrulayan salt okuma bir ucu "
        "elimizdeki resmî referansta tanımlı değil. Gerçek doğrulama, ilk "
        "Instagram hesabı bağlandığında olacak."
    )


def anthropic_sina(db: Session) -> tuple[bool, str]:
    """Claude anahtarini kontrol eder."""
    anahtar = deger_oku(db, "ANTHROPIC_API_KEY")
    if not anahtar:
        return False, "Claude API anahtarı girilmemiş."
    # Canli sinama icin en ucuz yol kisa bir istek gondermektir; bu da
    # ucret dogurur. Kullanicinin haberi olmadan ucret dogurmuyoruz.
    return True, (
        "Anahtar kayıtlı. Canlı sınama yapılmadı: en ucuz sınama bile "
        "ücret doğurur ve haberiniz olmadan harcama yapmıyoruz. Anahtar "
        "ilk içerik üretiminde denenecek."
    )


SINAYICILAR = {
    "MANUS_API_KEY": ("Manus", manus_sina),
    "META_APP_SECRET": ("Meta", meta_sina),
    "ANTHROPIC_API_KEY": ("Claude", anthropic_sina),
}


def sina(db: Session, anahtar: str) -> tuple[bool, str]:
    kayit = SINAYICILAR.get(anahtar)
    if kayit is None:
        return False, "Bu ayar için sınama tanımlı değil."
    ad, islev = kayit
    basarili, mesaj = islev(db)
    # Yalnizca HANGI saglayicinin sinandigi loglanir; anahtar asla.
    log.info("baglanti_sinandi", saglayici=ad, basarili=basarili)
    return basarili, mesaj
