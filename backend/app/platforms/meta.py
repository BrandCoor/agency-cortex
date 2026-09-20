"""Gercek Meta (Instagram/Facebook) adaptoru - HENUZ TAMAMLANMADI.

NEDEN BOS:
Bu adaptorun endpoint adresleri, izin (permission) adlari, metrik adlari ve
token yenileme akisi, Meta'nin RESMI dokumantasyonundan dogrulanmadan
yazilamaz. Tahminle yazilan bir entegrasyon, yanlis veri uretir ve bu yanlis
veri raporlara kadar tasinir.

Gelistirme ortamindan `developers.facebook.com` ve `graph.facebook.com`
adreslerine erisim ag politikasi tarafindan engellendi (HTTP 403). Ayrintilar:
`docs/platforms/meta.md`.

DURUM: Bu sinif hicbir yetenek bildirmez. Cagrilan her is acik hata verir.
Boylece sistem, calismayan bir entegrasyonu calisiyor gibi gostermez.
"""

from __future__ import annotations

from app.models.enums import Platform
from app.platforms.base import (
    AccountProfile,
    AuthorizationRequest,
    HealthStatus,
    PlatformAdapter,
    PlatformNotImplemented,
    TokenBundle,
)


class MetaAdapter(PlatformAdapter):
    """Instagram/Facebook profesyonel hesaplari icin gercek adaptor.

    Tamamlanmasi icin gerekenler `docs/platforms/meta.md` icinde listelenmistir.
    """

    platform = Platform.INSTAGRAM
    # Hicbir yetenek bildirilmiyor: dogrulanmamis hicbir is "hazir" sayilmaz.
    capabilities = frozenset()

    def authorize(self, *, state: str, redirect_uri: str) -> AuthorizationRequest:
        raise PlatformNotImplemented(self.platform)

    def callback(self, *, code: str, redirect_uri: str) -> tuple[TokenBundle, AccountProfile]:
        raise PlatformNotImplemented(self.platform)

    def health_check(self) -> HealthStatus:
        return HealthStatus(
            ok=False,
            detail=(
                "Meta entegrasyonu henuz tamamlanmadi. Resmi dokumantasyon "
                "dogrulanmadan endpoint ve izin adlari yazilmayacak. "
                "Ayrintilar: docs/platforms/meta.md"
            ),
        )
