"""Rakip ve trend gozlemleri.

Yalnizca KAMUYA ACIK veriler ve kullanicinin elle girdigi gozlemler saklanir.
Rakibin erisim, kaydetme sayisi, demografi gibi ozel icgoru verileri
sisteme girmez; bunlar yalnizca hesap sahibine aciktir.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamps, UUIDPrimaryKey, WorkspaceScoped
from app.models.enums import Platform


class CompetitorAccount(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Takip edilen rakip hesap."""

    __tablename__ = "competitor_accounts"

    platform: Mapped[Platform] = mapped_column(Enum(Platform, name="platform"), nullable=False)
    username: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(300))
    notes: Mapped[str | None] = mapped_column(Text)


class CompetitorObservation(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Rakip hakkinda tek bir gozlem."""

    __tablename__ = "competitor_observations"

    competitor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("competitor_accounts.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # "public_api" | "manual" | "research" - verinin nereden geldigi her zaman bilinir.
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_urls: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # Bulgunun ne kadar guvenilir oldugu. Dusukse rapora "hipotez" olarak girer.
    confidence: Mapped[str | None] = mapped_column(String(20))
    uncertainties: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)


class TrendObservation(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Marka baglaminda degerlendirilmis trend bulgusu."""

    __tablename__ = "trend_observations"

    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    platform: Mapped[Platform | None] = mapped_column(Enum(Platform, name="platform"))
    topic: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    relevance_to_brand: Mapped[str | None] = mapped_column(Text)
    source_urls: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    confidence: Mapped[str | None] = mapped_column(String(20))
    uncertainties: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    ai_task_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
