"""Gunluk, haftalik ve aylik raporlar."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamps, UUIDPrimaryKey, WorkspaceScoped
from app.models.enums import ContentStatus, ReportPeriod


class Report(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Bir donemin raporu."""

    __tablename__ = "reports"
    __table_args__ = (
        # Ayni musteri icin ayni donemin raporu iki kez uretilmez.
        UniqueConstraint(
            "workspace_id", "period", "period_start", name="uq_report_period"
        ),
    )

    period: Mapped[ReportPeriod] = mapped_column(
        Enum(ReportPeriod, name="report_period"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, name="content_status"), default=ContentStatus.DRAFT, nullable=False
    )
    # Hangi verilerin eksik veya guvenilmez oldugu raporda acikca belirtilir.
    data_quality_notes: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    assumptions: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    ai_run_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))


class ReportSection(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Raporun bir bolumu."""

    __tablename__ = "report_sections"

    report_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    heading: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # "fact" | "hypothesis" - yeterli kanit yoksa kesin neden yazilmaz.
    claim_type: Mapped[str] = mapped_column(String(20), default="fact", nullable=False)
