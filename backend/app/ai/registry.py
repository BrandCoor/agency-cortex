"""AI saglayicilarinin kayit defteri."""

from __future__ import annotations

from app.ai.base import AIProvider, ProviderNotConfigured
from app.ai.claude import ClaudeProvider
from app.ai.fake import FakeProvider
from app.ai.gemini import GeminiProvider
from app.ai.manus import ManusProvider
from app.core.config import get_settings
from app.core.logging_config import get_logger

log = get_logger("ai_registry")

# Hangi gorev hangi saglayiciya gider.
#
# BU LISTE ARTIK YALNIZCA ILK KURULUMUN VARSAYILANIDIR. Gercek dagilim
# veritabaninda durur ve panelden degistirilir (Yapay zeka sayfasi).
# Kodda birakilmasinin sebebi, veritabani henuz doldurulmamisken sistemin
# yine de calismasidir.
TASK_ROUTING: dict[str, str] = {
    "content_script": "claude",
    "strategic_commentary": "claude",
    "brand_voice_check": "claude",
    "competitor_research": "manus",
    "competitor_discovery": "manus",
    "trend_research": "manus",
    "bulk_classification": "gemini",
}


def _ayar_oku(anahtar: str) -> str | None:
    """API anahtarini panel ayarlarindan okur; yoksa ortam degiskeninden.

    Panelden girilen deger onceliklidir (bkz. DECISIONS.md K-024).
    Veritabanina ulasilamazsa sessizce None donmek yerine ortam
    degiskenine duseriz; boylece anahtar sunucuda tanimliysa sistem calisir.
    """
    import os

    try:
        from app.core.db import SessionLocal
        from app.services.sistem_ayarlari import deger_oku

        with SessionLocal() as db:
            deger = deger_oku(db, anahtar)
            if deger:
                return deger
    except Exception:  # noqa: BLE001 - ayar okunamazsa ortam degiskenine duser
        pass
    return os.environ.get(anahtar)


def get_provider(name: str, *, mode: str | None = None) -> AIProvider:
    """Saglayiciyi doner.

    `mode`: "fake" veya "live". Verilmezse ayarlardaki `ai_provider_mode`.
    """
    settings = get_settings()
    etkin_mod = mode or settings.ai_provider_mode

    if etkin_mod == "fake":
        # ORNEK VERI URETIMDE YASAK.
        #
        # Ornek veri saglayicisi gercek analiz gibi gorunen metinler
        # uretir. Gelistirmede bu faydalidir; uretimde ise kullanicinin
        # gercek sandigi sahte bir rapor demektir. Bu yuzden uretimde
        # sessizce calismak yerine ACIKCA duruyoruz.
        if settings.is_production:
            raise ProviderNotConfigured(
                "ornek-veri",
                ["üretimde örnek veri modu kapalıdır; gerçek bir "
                 "sağlayıcı açın ve sınayın"],
            )
        return FakeProvider()

    if name == "claude":
        return ClaudeProvider()
    if name == "manus":
        # Anahtar once panel ayarlarindan, yoksa ortam degiskeninden okunur.
        return ManusProvider(api_key=_ayar_oku("MANUS_API_KEY"))
    if name == "gemini":
        # Anahtar once panel ayarlarindan, yoksa ortam degiskeninden okunur.
        return GeminiProvider(api_key=_ayar_oku("GEMINI_API_KEY"))

    raise ValueError(f"Bilinmeyen AI saglayicisi: {name}")


def _panelden_saglayici(task_type: str) -> AIProvider | None:
    """Panelde bu goreve atanmis saglayiciyi doner; yoksa None.

    Veritabanina ulasilamazsa None donulur ve cagiran taraf koddaki
    varsayilana duser. Sessizce hicbir sey yapmamak yerine calismaya
    devam etmek, bir ayar tablosu okunamadiginda tum sistemi durdurmaktan
    iyidir; hata zaten loglanir.
    """
    try:
        from app.core.db import SessionLocal
        from app.services.ai_saglayicilar import atamalar, getir, ornek_olustur

        with SessionLocal() as db:
            anahtar = atamalar(db).get(task_type)
            if not anahtar:
                return None
            kayit = getir(db, anahtar)
            if kayit is None or not kayit.kullanilabilir:
                # Atanmis ama kullanilamaz durumda: koddaki varsayilana
                # DUSMEYIZ, cunku kullanicinin secimi bilerek yapilmistir.
                # Hata mesaji ne yapilmasi gerektigini soyler.
                if kayit is not None:
                    raise ProviderNotConfigured(anahtar, ["etkin ve sınanmış olmalı"])
                return None
            return ornek_olustur(db, kayit)
    except ProviderNotConfigured:
        raise
    except Exception as hata:  # noqa: BLE001 - ayar okunamazsa varsayilana duser
        log.warning("gorev_atamasi_okunamadi", gorev=task_type, hata=str(hata))
        return None


def provider_for_task(task_type: str, *, mode: str | None = None) -> AIProvider:
    """Gorev turune gore dogru saglayiciyi secer.

    ONCELIK: panelden yapilan atama > koddaki varsayilan.
    """
    settings = get_settings()
    etkin_mod = mode or settings.ai_provider_mode
    if etkin_mod == "fake":
        # Ornek veri modu: uretimde zaten yasak (get_provider kontrol eder).
        return get_provider("fake", mode="fake")

    panelden = _panelden_saglayici(task_type)
    if panelden is not None:
        return panelden

    ad = TASK_ROUTING.get(task_type)
    if ad is None:
        raise ValueError(
            f"'{task_type}' gorevi icin saglayici tanimli degil. "
            f"Tanimlilar: {sorted(TASK_ROUTING)}"
        )
    return get_provider(ad, mode=mode)


def provider_status() -> list[dict]:
    """Her saglayicinin GERCEK durumu.

    DIKKAT: Durum her zaman "live" saglayiciya sorulur. Sahte moda
    sorulsaydi hepsi "calisiyor" gorunurdu ve panel, gercekte calismayan
    bir saglayiciyi hazir gibi gosterirdi.

    `mode` alani, su an hangi modun etkin oldugunu ayrica bildirir.
    """
    etkin_mod = get_settings().ai_provider_mode
    satirlar = []
    for ad in ("claude", "manus", "gemini"):
        saglayici = get_provider(ad, mode="live")
        calisir, aciklama = saglayici.health_check()
        satirlar.append(
            {
                "provider": ad,
                "adapter": type(saglayici).__name__,
                "available": calisir,
                "model": saglayici.model,
                "detail": aciklama,
                "mode": etkin_mod,
                # Sahte modda hicbir gercek cagri yapilmaz.
                "using_fake": etkin_mod == "fake",
            }
        )
    return satirlar
