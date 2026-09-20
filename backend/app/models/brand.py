"""Marka hafizasi, marka dili ve kampanyalar."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamps, UUIDPrimaryKey, WorkspaceScoped
from app.models.enums import ContentStatus


class Brand(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Musterinin markasi ve temel tanimi."""

    __tablename__ = "brands"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(String(500))


class BrandGuideline(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Marka dili, hedef kitle, yasakli ifadeler ve KPI hedefleri.

    AI'ya gonderilen her istem (prompt) bu kurallari temel alir.
    """

    __tablename__ = "brand_guidelines"

    brand_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tone_of_voice: Mapped[str | None] = mapped_column(Text)
    target_audience: Mapped[str | None] = mapped_column(Text)
    # Markanin asla kullanmamasi gereken ifadeler. Uretilen icerik bunlara karsi denetlenir.
    forbidden_phrases: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    preferred_phrases: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    kpi_targets: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class Campaign(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Belirli bir donem ve hedefe yonelik kampanya."""

    __tablename__ = "campaigns"

    brand_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    objective: Mapped[str | None] = mapped_column(Text)
    starts_on: Mapped[date | None] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, name="content_status"), default=ContentStatus.DRAFT, nullable=False
    )
    kpi_targets: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
