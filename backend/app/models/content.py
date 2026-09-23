"""Icerik fikirleri, senaryolar ve yayin takvimi."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamps, UUIDPrimaryKey, WorkspaceScoped
from app.models.enums import ContentStatus, MediaType, Platform


class ContentIdea(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Bir icerik fikri. Platforma gore ayri senaryolara donusur."""

    __tablename__ = "content_ideas"

    brand_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    objective: Mapped[str | None] = mapped_column(Text)
    target_metric: Mapped[str | None] = mapped_column(String(100))
    audience_problem: Mapped[str | None] = mapped_column(Text)
    reason_for_recommendation: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, name="content_status"), default=ContentStatus.DRAFT, nullable=False
    )
    # Ayni fikrin tekrar uretilmesini engellemek icin icerik imzasi.
    idea_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("workspace_id", "idea_fingerprint", name="uq_idea_fingerprint"),
    )


class ContentScript(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Bir fikrin belirli bir platform icin senaryosu.

    Ayni fikir tum platformlara kopyalanmaz; her platform icin ayri uyarlama
    uretilir (Reel, Short, carousel, story, LinkedIn vb.).
    """

    __tablename__ = "content_scripts"

    idea_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("content_ideas.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    platform: Mapped[Platform] = mapped_column(Enum(Platform, name="platform"), nullable=False)
    format: Mapped[MediaType] = mapped_column(Enum(MediaType, name="media_type"), nullable=False)
    hook: Mapped[str | None] = mapped_column(Text)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    scene_plan: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    spoken_script: Mapped[str | None] = mapped_column(Text)
    on_screen_text: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    visual_production_brief: Mapped[str | None] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(Text)
    cta: Mapped[str | None] = mapped_column(Text)
    alternative_hooks: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    required_assets: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    production_difficulty: Mapped[str | None] = mapped_column(String(50))
    brand_risks: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    # Dogrulanmasi gereken iddialar. Bos degilse insan kontrolu zorunludur.
    claims_to_verify: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, name="content_status"), default=ContentStatus.DRAFT, nullable=False
    )
    # Ilk surumde her zaman True. Insan onayi olmadan yayin yok.
    human_approval_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ai_run_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))


class ContentCalendar(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Onaylanmis icerigin planlandigi zaman."""

    __tablename__ = "content_calendar"

    script_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("content_scripts.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Istanbul", nullable=False)
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, name="content_status"), default=ContentStatus.SCHEDULED, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)
    # Kim planladi. Bir icerigin takvime nasil girdigi sorulabilmeli.
    planned_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    # YAYIN ELLE ISARETLENIR.
    #
    # Sistem bu surumde hicbir seyi kendisi paylasmaz (yayin izinleri
    # bilerek istenmiyor). Paylasimi kullanici yapar ve buradan isaretler;
    # boylece takvim gercegi gosterir, varsayimi degil.
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
