"""Sosyal medya hesaplari, icerikler ve metrikler.

Onemli ayrim: platformdan gelen HAM yanit (`media_metrics_raw`) ile
sistemin ortak diline cevrilmis NORMALIZE veri (`media_metrics_normalized`)
ayri tablolarda tutulur. Ham veri hicbir zaman degistirilmez; boylece bir
hesaplama hatasi bulunursa normalize veri ham veriden yeniden uretilebilir.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Enum, ForeignKey, Index, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamps, UUIDPrimaryKey, WorkspaceScoped
from app.models.enums import MediaType, Platform


class SocialAccount(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Musterinin yetkilendirdigi bir sosyal medya hesabi."""

    __tablename__ = "social_accounts"
    __table_args__ = (
        UniqueConstraint("workspace_id", "platform", "external_id", name="uq_social_account"),
    )

    platform: Mapped[Platform] = mapped_column(Enum(Platform, name="platform"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    username: Mapped[str | None] = mapped_column(String(200))
    display_name: Mapped[str | None] = mapped_column(String(300))
    # Instagram'da icgoru verisi yalnizca profesyonel hesaplarda vardir.
    # Kisisel hesaba profesyonel hesap gibi davranmamak icin bu alan tutulur.
    is_professional: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_error: Mapped[str | None] = mapped_column(Text)


class OAuthCredential(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Sifrelenmis erisim anahtarlari.

    Token'lar duz metin olarak ASLA saklanmaz; `_encrypted` alanlar
    uygulama tarafindan sifrelenip yazilir.
    """

    __tablename__ = "oauth_credentials"

    social_account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("social_accounts.id", ondelete="CASCADE"),
        nullable=False, index=True, unique=True,
    )
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text)
    token_type: Mapped[str | None] = mapped_column(String(50))
    scopes: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlatformMedia(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Yayinlanmis bir icerik (gonderi, reel, story vb.)."""

    __tablename__ = "platform_media"
    __table_args__ = (
        UniqueConstraint("workspace_id", "platform", "external_id", name="uq_platform_media"),
        Index("ix_media_published", "workspace_id", "published_at"),
    )

    social_account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("social_accounts.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    platform: Mapped[Platform] = mapped_column(Enum(Platform, name="platform"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    media_type: Mapped[MediaType] = mapped_column(Enum(MediaType, name="media_type"), nullable=False)
    caption: Mapped[str | None] = mapped_column(Text)
    permalink: Mapped[str | None] = mapped_column(String(1000))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Istanbul", nullable=False)


class MediaMetricsRaw(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Platformdan gelen ham API yaniti. Degistirilmez."""

    __tablename__ = "media_metrics_raw"
    __table_args__ = (
        Index("ix_raw_fetch", "workspace_id", "fetched_at"),
    )

    media_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("platform_media.id", ondelete="CASCADE"), index=True
    )
    platform: Mapped[Platform] = mapped_column(Enum(Platform, name="platform"), nullable=False)
    source_endpoint: Mapped[str] = mapped_column(String(500), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Ayni yanitin iki kez islenmesini engellemek icin.
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)


class MediaMetricsNormalized(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Ortak veri modeline cevrilmis olcum."""

    __tablename__ = "media_metrics_normalized"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "media_id", "metric_name", "measurement_period", "measured_at",
            name="uq_normalized_metric",
        ),
    )

    media_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("platform_media.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    raw_reference_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("media_metrics_raw.id", ondelete="SET NULL")
    )
    platform: Mapped[Platform] = mapped_column(Enum(Platform, name="platform"), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_value: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False)
    measurement_period: Mapped[str] = mapped_column(String(50), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AccountMetrics(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Hesap duzeyinde olcumler (takipci, erisim, profil ziyareti)."""

    __tablename__ = "account_metrics"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "social_account_id", "metric_name", "measurement_period", "measured_at",
            name="uq_account_metric",
        ),
    )

    social_account_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("social_accounts.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    platform: Mapped[Platform] = mapped_column(Enum(Platform, name="platform"), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_value: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False)
    measurement_period: Mapped[str] = mapped_column(String(50), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_endpoint: Mapped[str | None] = mapped_column(String(500))
    follower_count: Mapped[int | None] = mapped_column(BigInteger)
