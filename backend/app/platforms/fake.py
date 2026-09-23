"""Sahte Instagram adaptoru.

Gercek API anahtari veya gercek hesap OLMADAN tum sistemin gelistirilip
test edilebilmesini saglar. Uretilen veriler sabittir (ayni girdi -> ayni
cikti); boylece testler guvenilir olur.

Bu adaptor uretimde KULLANILMAZ; `AI_PROVIDER_MODE` benzeri sekilde
`PLATFORM_MODE=fake` ayariyla yalnizca gelistirme ve testte devreye girer.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from app.models.enums import MediaType, Platform
from app.platforms.base import (
    AccountProfile,
    AuthorizationRequest,
    Capability,
    CommentItem,
    HealthStatus,
    MediaItem,
    MetricPoint,
    PlatformAdapter,
    TokenBundle,
)

# Sahte verinin baslangic noktasi. Sabit tarih -> tekrarlanabilir testler.
_EPOCH = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)

_MEDIA_TYPES = [MediaType.REEL, MediaType.CAROUSEL, MediaType.IMAGE, MediaType.STORY]

# Instagram'in gercek metrik adlari resmi dokumanla dogrulanmadan
# kullanilmayacagi icin, sahte adaptor kendi acik isimlerini kullanir.
# Gercek adaptor yazilirken bu adlar Meta dokumanindan alinacaktir.
_MEDIA_METRICS = ["impressions", "reach", "likes", "comments", "saves", "shares"]
_ACCOUNT_METRICS = ["follower_count", "reach", "profile_views"]


def _stable_number(*parts: str, low: int, high: int) -> int:
    """Girdiye bagli, her calistirmada AYNI kalan bir sayi uretir."""
    digest = hashlib.sha256("|".join(parts).encode()).digest()
    span = high - low + 1
    return low + (int.from_bytes(digest[:8], "big") % span)


class FakeInstagramAdapter(PlatformAdapter):
    """Instagram profesyonel hesabini taklit eder."""

    platform = Platform.INSTAGRAM
    capabilities = frozenset(
        {
            Capability.AUTHORIZE,
            Capability.REFRESH_TOKEN,
            Capability.LIST_MEDIA,
            Capability.FETCH_MEDIA_METRICS,
            Capability.FETCH_ACCOUNT_METRICS,
            Capability.FETCH_COMMENTS,
            # PUBLISH_DRAFT bilerek YOK: ilk surumde yayin yapilmaz.
        }
    )

    def __init__(self, *, account_external_id: str = "ig_test_hesap_1") -> None:
        self._account_external_id = account_external_id

    # --- Yetkilendirme ---

    def authorize(self, *, state: str, redirect_uri: str) -> AuthorizationRequest:
        return AuthorizationRequest(
            url=f"https://sahte-instagram.local/oauth?state={state}&redirect_uri={redirect_uri}",
            state=state,
        )

    def callback(self, *, code: str, redirect_uri: str) -> tuple[TokenBundle, AccountProfile]:
        if not code:
            raise ValueError("Yetkilendirme kodu bos olamaz.")
        token = TokenBundle(
            access_token=f"sahte-erisim-anahtari-{code}",
            refresh_token=f"sahte-yenileme-anahtari-{code}",
            token_type="bearer",
            expires_at=datetime.now(UTC) + timedelta(days=60),
            scopes=("instagram_basic", "instagram_manage_insights"),
        )
        profile = AccountProfile(
            external_id=self._account_external_id,
            username="test_markasi",
            display_name="Test Markasi",
            is_professional=True,
            raw={"kaynak": "fake_adapter"},
        )
        return token, profile

    def refresh_token(self, *, refresh_token: str) -> TokenBundle:
        self._require(Capability.REFRESH_TOKEN)
        return TokenBundle(
            access_token=f"yenilenmis-{refresh_token}",
            refresh_token=refresh_token,
            token_type="bearer",
            expires_at=datetime.now(UTC) + timedelta(days=60),
        )

    # --- Veri okuma ---

    def list_media(
        self, *, access_token: str, account_external_id: str, limit: int = 50
    ) -> list[MediaItem]:
        self._require(Capability.LIST_MEDIA)
        count = min(limit, 12)
        items: list[MediaItem] = []
        for i in range(count):
            external_id = f"{account_external_id}_medya_{i:03d}"
            items.append(
                MediaItem(
                    external_id=external_id,
                    media_type=_MEDIA_TYPES[i % len(_MEDIA_TYPES)],
                    caption=f"Test gonderisi {i} #deneme",
                    permalink=f"https://sahte-instagram.local/p/{external_id}",
                    published_at=_EPOCH - timedelta(days=i),
                    raw={"id": external_id, "kaynak": "fake_adapter"},
                )
            )
        return items

    def fetch_media_metrics(
        self, *, access_token: str, media_external_id: str
    ) -> list[MetricPoint]:
        self._require(Capability.FETCH_MEDIA_METRICS)
        measured_at = _EPOCH
        points: list[MetricPoint] = []
        for name in _MEDIA_METRICS:
            value = _stable_number(media_external_id, name, low=0, high=5000)
            points.append(
                MetricPoint(
                    metric_name=name,
                    value=float(value),
                    measurement_period="lifetime",
                    measured_at=measured_at,
                    source_endpoint=f"fake://media/{media_external_id}/insights",
                    raw={"name": name, "values": [{"value": value}]},
                )
            )
        return points

    def fetch_account_metrics(
        self, *, access_token: str, account_external_id: str
    ) -> list[MetricPoint]:
        self._require(Capability.FETCH_ACCOUNT_METRICS)
        points: list[MetricPoint] = []
        for name in _ACCOUNT_METRICS:
            value = _stable_number(account_external_id, name, low=100, high=100_000)
            points.append(
                MetricPoint(
                    metric_name=name,
                    value=float(value),
                    measurement_period="day",
                    measured_at=_EPOCH,
                    source_endpoint=f"fake://account/{account_external_id}/insights",
                    raw={"name": name, "values": [{"value": value}]},
                )
            )
        return points

    def fetch_comments_if_allowed(
        self, *, access_token: str, media_external_id: str
    ) -> list[CommentItem]:
        self._require(Capability.FETCH_COMMENTS)
        return [
            CommentItem(
                external_id=f"{media_external_id}_yorum_{i}",
                text=f"Ornek yorum {i}",
                created_at=_EPOCH - timedelta(hours=i),
                author_username=f"kullanici_{i}",
            )
            for i in range(3)
        ]

    def publish_draft_if_enabled(
        self, *, access_token: str, account_external_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        # Ust sinif once yayin kilidini kontrol eder, sonra yetenegi.
        # Bu adaptor PUBLISH_DRAFT yetenegini bildirmedigi icin kilit acilsa
        # bile yayin yapilamaz.
        return super().publish_draft_if_enabled(
            access_token=access_token,
            account_external_id=account_external_id,
            payload=payload,
        )

    def health_check(self) -> HealthStatus:
        return HealthStatus(ok=True, detail="Sahte sağlayıcı çalışıyor — üretilen veri GERÇEK DEĞİL.")
