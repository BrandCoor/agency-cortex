"""Platform adaptorlerinin ortak arayuzu.

TASARIM KURALI: Bir adaptor, gercekte yapamadigi bir isi "hazir" gostermez.
Her adaptor neleri yapabildigini `capabilities` ile acikca bildirir; bildirmedigi
bir is cagrildiginda sessizce bos sonuc donmek yerine acik bir hata firlatir.

Bunun sebebi: sahte calisan bir entegrasyon, hic calismayan bir entegrasyondan
daha tehlikelidir. Rapor "erisim 0" derse, bu gercek bir sifir mi yoksa
calismayan bir baglanti mi, ayirt edilemez.
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.models.enums import MediaType, Platform


class Capability(str, enum.Enum):
    """Bir adaptorun gercekten yapabildigi isler."""

    AUTHORIZE = "authorize"
    REFRESH_TOKEN = "refresh_token"
    LIST_MEDIA = "list_media"
    FETCH_MEDIA_METRICS = "fetch_media_metrics"
    FETCH_ACCOUNT_METRICS = "fetch_account_metrics"
    FETCH_COMMENTS = "fetch_comments"
    PUBLISH_DRAFT = "publish_draft"


class PlatformError(Exception):
    """Platform katmanindaki tum hatalarin atasi."""


class CapabilityNotSupported(PlatformError):
    """Adaptorun desteklemedigi bir is istendi."""

    def __init__(self, platform: Platform, capability: Capability) -> None:
        super().__init__(
            f"'{platform.value}' adaptoru '{capability.value}' islemini desteklemiyor."
        )
        self.platform = platform
        self.capability = capability


class PlatformNotImplemented(PlatformError):
    """Platform henuz gelistirilmedi."""

    def __init__(self, platform: Platform) -> None:
        super().__init__(
            f"'{platform.value}' entegrasyonu henuz gelistirilmedi. "
            "Bu platform icin veri toplanamaz."
        )
        self.platform = platform


class PublishingDisabled(PlatformError):
    """Yayinlama kilidi kapali oldugu halde yayin denendi.

    Ilk surumde bu kilit her zaman kapalidir; insan onayi olmadan hicbir sey
    yayinlanamaz.
    """


class RateLimited(PlatformError):
    """Platform istek sinirina takildik."""

    def __init__(self, platform: Platform, retry_after_seconds: int | None = None) -> None:
        super().__init__(f"'{platform.value}' istek sinirina takildi.")
        self.platform = platform
        self.retry_after_seconds = retry_after_seconds


class TokenExpired(PlatformError):
    """Erisim anahtarinin suresi dolmus; yenilenmeli."""


# ---------------------------------------------------------------------------
# Veri tasiyicilari
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AuthorizationRequest:
    """Kullanicinin yonlendirilecegi izin ekrani."""

    url: str
    state: str


@dataclass(frozen=True)
class TokenBundle:
    """Platformdan alinan erisim anahtarlari.

    Bu nesne loglanmamalidir; `__repr__` degerleri gizler.
    """

    access_token: str
    refresh_token: str | None = None
    token_type: str | None = None
    expires_at: datetime | None = None
    scopes: tuple[str, ...] = ()

    def __repr__(self) -> str:  # pragma: no cover - guvenlik amacli
        return (
            f"TokenBundle(access_token='***', refresh_token="
            f"{'***' if self.refresh_token else 'None'}, expires_at={self.expires_at!r})"
        )


@dataclass(frozen=True)
class AccountProfile:
    """Baglanan hesabin temel bilgileri."""

    external_id: str
    username: str | None = None
    display_name: str | None = None
    # Instagram'da icgoru verisi YALNIZCA profesyonel hesaplarda vardir.
    is_professional: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MediaItem:
    """Yayinlanmis bir icerik."""

    external_id: str
    media_type: MediaType
    caption: str | None = None
    permalink: str | None = None
    published_at: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MetricPoint:
    """Tek bir olcum.

    `raw` alani, bu olcumun hangi ham yanittan turedigini saklar; normalize
    veri her zaman ham veriye kadar izlenebilir olmalidir.
    """

    metric_name: str
    value: float
    measurement_period: str
    measured_at: datetime
    source_endpoint: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CommentItem:
    external_id: str
    text: str
    created_at: datetime | None = None
    author_username: str | None = None


@dataclass(frozen=True)
class HealthStatus:
    ok: bool
    detail: str | None = None


# ---------------------------------------------------------------------------
# Adaptor arayuzu
# ---------------------------------------------------------------------------

class PlatformAdapter(ABC):
    """Her sosyal medya platformu icin ortak arayuz."""

    #: Hangi platform
    platform: Platform
    #: Bu adaptorun GERCEKTEN yapabildigi isler
    capabilities: frozenset[Capability] = frozenset()

    def supports(self, capability: Capability) -> bool:
        return capability in self.capabilities

    def _require(self, capability: Capability) -> None:
        """Desteklenmeyen is cagrildiginda acik hata verir."""
        if not self.supports(capability):
            raise CapabilityNotSupported(self.platform, capability)

    # --- Yetkilendirme ---

    @abstractmethod
    def authorize(self, *, state: str, redirect_uri: str) -> AuthorizationRequest:
        """Kullanicinin izin verecegi adresi uretir."""

    @abstractmethod
    def callback(self, *, code: str, redirect_uri: str) -> tuple[TokenBundle, AccountProfile]:
        """Izin ekranindan donen kodu anahtara cevirir."""

    def refresh_token(self, *, refresh_token: str) -> TokenBundle:
        """Suresi dolan anahtari yeniler."""
        self._require(Capability.REFRESH_TOKEN)
        raise NotImplementedError

    # --- Veri okuma ---

    def list_media(
        self, *, access_token: str, account_external_id: str, limit: int = 50
    ) -> list[MediaItem]:
        self._require(Capability.LIST_MEDIA)
        raise NotImplementedError

    def fetch_media_metrics(
        self, *, access_token: str, media_external_id: str
    ) -> list[MetricPoint]:
        self._require(Capability.FETCH_MEDIA_METRICS)
        raise NotImplementedError

    def fetch_account_metrics(
        self, *, access_token: str, account_external_id: str
    ) -> list[MetricPoint]:
        self._require(Capability.FETCH_ACCOUNT_METRICS)
        raise NotImplementedError

    def fetch_comments_if_allowed(
        self, *, access_token: str, media_external_id: str
    ) -> list[CommentItem]:
        """Yorumlari okur. Izin yoksa CapabilityNotSupported firlatir."""
        self._require(Capability.FETCH_COMMENTS)
        raise NotImplementedError

    # --- Yazma (ilk surumde kilitli) ---

    def publish_draft_if_enabled(
        self, *, access_token: str, account_external_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Yayin yapar. Kilit kapaliysa PublishingDisabled firlatir.

        Kilidin kontrolu bu metodu cagiran katmanda DEGIL, burada yapilir;
        boylece hicbir cagri yolu kilidi atlayamaz.
        """
        from app.core.config import get_settings

        if not get_settings().feature_publishing_enabled:
            raise PublishingDisabled(
                "Yayinlama kapali. Insan onayi olmadan icerik yayinlanamaz."
            )
        self._require(Capability.PUBLISH_DRAFT)
        raise NotImplementedError

    # --- Saglik ---

    @abstractmethod
    def health_check(self) -> HealthStatus:
        """Adaptorun calisir durumda olup olmadigini bildirir."""


class NotImplementedAdapter(PlatformAdapter):
    """Henuz gelistirilmemis platformlar icin durak.

    Hicbir yetenek bildirmez. Cagrilan her is acik hata verir; boylece
    "calisiyor gibi gorunen ama calismayan" bir entegrasyon olusmaz.
    """

    capabilities = frozenset()

    def __init__(self, platform: Platform) -> None:
        self.platform = platform

    def authorize(self, *, state: str, redirect_uri: str) -> AuthorizationRequest:
        raise PlatformNotImplemented(self.platform)

    def callback(self, *, code: str, redirect_uri: str) -> tuple[TokenBundle, AccountProfile]:
        raise PlatformNotImplemented(self.platform)

    def health_check(self) -> HealthStatus:
        return HealthStatus(ok=False, detail="Bu platform entegrasyonu henuz gelistirilmedi.")
