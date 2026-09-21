"""AI saglayicilarinin kayit defteri."""

from __future__ import annotations

from app.ai.base import AIProvider
from app.ai.claude import ClaudeProvider, GeminiProviderStub
from app.ai.fake import FakeProvider
from app.ai.manus import ManusProvider
from app.core.config import get_settings

# Hangi gorev hangi saglayiciya gider (urun karari).
TASK_ROUTING: dict[str, str] = {
    "content_script": "claude",
    "strategic_commentary": "claude",
    "brand_voice_check": "claude",
    "competitor_research": "manus",
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
        return FakeProvider()

    if name == "claude":
        return ClaudeProvider()
    if name == "manus":
        # Anahtar once panel ayarlarindan, yoksa ortam degiskeninden okunur.
        return ManusProvider(api_key=_ayar_oku("MANUS_API_KEY"))
    if name == "gemini":
        return GeminiProviderStub()

    raise ValueError(f"Bilinmeyen AI saglayicisi: {name}")


def provider_for_task(task_type: str, *, mode: str | None = None) -> AIProvider:
    """Gorev turune gore dogru saglayiciyi secer."""
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
