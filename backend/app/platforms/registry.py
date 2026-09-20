"""Platform adaptorlerinin kayit defteri.

Hangi platformun hangi adaptorle calisacagini tek yerden belirler.
Gelistirme ortaminda sahte adaptor, uretimde gercek adaptor kullanilir.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.models.enums import Platform
from app.platforms.base import NotImplementedAdapter, PlatformAdapter
from app.platforms.fake import FakeInstagramAdapter
from app.platforms.meta import MetaAdapter

# Henuz gelistirilmemis platformlar. Arayuz hazir; gercek entegrasyon yok.
# Bu liste bilerek acik tutulur: "yakinda" demek yerine "yok" denir.
_PLANNED: tuple[Platform, ...] = (
    Platform.TIKTOK,
    Platform.YOUTUBE,
    Platform.LINKEDIN,
    Platform.X,
    Platform.PINTEREST,
)


def get_adapter(platform: Platform, *, mode: str | None = None) -> PlatformAdapter:
    """Platform icin uygun adaptoru doner.

    `mode`: "fake" veya "live". Verilmezse ayarlardaki `platform_mode` kullanilir.
    """
    settings = get_settings()
    effective_mode = mode or settings.platform_mode

    if platform in (Platform.INSTAGRAM, Platform.FACEBOOK):
        if effective_mode == "fake":
            return FakeInstagramAdapter()
        return MetaAdapter()

    if platform in _PLANNED:
        return NotImplementedAdapter(platform)

    raise ValueError(f"Bilinmeyen platform: {platform}")


def platform_status() -> list[dict]:
    """Her platformun gercek durumunu bildirir.

    Panelde ve `/api/v1/platforms` ucunda gosterilir; kullanici hangi
    platformun gercekten calistigini net gorur.
    """
    rows: list[dict] = []
    for platform in Platform:
        adapter = get_adapter(platform)
        health = adapter.health_check()
        rows.append(
            {
                "platform": platform.value,
                "adapter": type(adapter).__name__,
                "available": health.ok,
                "capabilities": sorted(c.value for c in adapter.capabilities),
                "detail": health.detail,
            }
        )
    return rows
