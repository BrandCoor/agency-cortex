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
        "Biçim doğru görünüyor. NOT: Bu canlı bir sınama DEĞİLDİR — Meta'nın "
        "uygulama bilgilerini tek başına doğrulayan salt okuma bir ucu resmî "
        "referansta tanımlı değil; uydurma bir uç çağırmıyoruz. "
        "GERÇEK SINAMA: bir müşteriye gidip \"Instagram hesabı bağla\" "
        "düğmesine basın. Bilgiler yanlışsa Instagram size açıkça söyler."
    )


#: Claude anahtarini dogrulamak icin kullanilan salt okuma uc.
#: Model listesi doner, JETON HARCAMAZ ve UCRET DOGURMAZ.
#: Kaynak: Anthropic Messages API - Models endpoint (GET /v1/models)
ANTHROPIC_MODEL_UCU = "https://api.anthropic.com/v1/models"
ANTHROPIC_SURUM = "2023-06-01"


def anthropic_sina(db: Session) -> tuple[bool, str]:
    """Claude anahtarini GERCEK bir API cagrisiyla dogrular.

    Model listesi ucu salt okumadir: jeton harcamaz, ucret dogurmaz.
    Bu yuzden kullanicinin haberi olmadan para harcamadan sinama yapilabilir.
    """
    import httpx

    anahtar = deger_oku(db, "ANTHROPIC_API_KEY")
    if not anahtar:
        return False, "Claude API anahtarı girilmemiş."

    try:
        yanit = httpx.get(
            ANTHROPIC_MODEL_UCU,
            headers={"x-api-key": anahtar, "anthropic-version": ANTHROPIC_SURUM},
            params={"limit": 1},
            timeout=20.0,
        )
    except httpx.HTTPError as hata:
        # Anahtar hatali olmayabilir; ag sorunu da olabilir. Ayrimi yapiyoruz.
        return False, f"Anthropic'e bağlanılamadı: {type(hata).__name__}"

    if yanit.status_code == 200:
        try:
            modeller = yanit.json().get("data") or []
            ad = modeller[0].get("display_name") or modeller[0].get("id")
        except Exception:  # noqa: BLE001 - yanit bicimi beklenenden farkliysa
            ad = None
        mesaj = "Bağlantı çalışıyor. Anahtar geçerli."
        if ad:
            mesaj += f" (erişilebilen model: {ad})"
        return True, mesaj + " Bu sınama ücret doğurmaz."

    if yanit.status_code == 401:
        return False, (
            "Anahtar kabul edilmedi. console.anthropic.com adresinden yeni "
            "bir anahtar üretip tekrar girin."
        )
    if yanit.status_code == 403:
        return False, (
            "Anahtar tanındı ama yetkisi yok. Anahtarın hangi çalışma alanına "
            "ait olduğunu Anthropic konsolundan kontrol edin."
        )
    if yanit.status_code == 429:
        return False, "Anthropic şu an çok fazla istek aldı; biraz sonra tekrar deneyin."

    # Hata govdesi anahtar icermez ama yine de kisaltilir.
    return False, f"Beklenmeyen yanıt (HTTP {yanit.status_code})."


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
