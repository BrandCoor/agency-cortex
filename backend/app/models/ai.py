"""AI gorevleri, calistirmalari ve maliyet kayitlari.

Her AI cagrisi izlenebilir olmalidir: hangi model, hangi istem surumu,
ne kadar token, ne kadar maliyet, ne kadar sure, basarili mi.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamps, UUIDPrimaryKey, WorkspaceScoped
from app.models.enums import AIProviderName, AITaskStatus


class AITask(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Bir AI isi (icerik uretimi, arastirma, rapor yorumu)."""

    __tablename__ = "ai_tasks"

    task_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[AITaskStatus] = mapped_column(
        Enum(AITaskStatus, name="ai_task_status"), default=AITaskStatus.PENDING, nullable=False
    )
    provider: Mapped[AIProviderName] = mapped_column(
        Enum(AIProviderName, name="ai_provider"), nullable=False
    )
    # Manus gibi dis sistemlerin kendi gorev kimligi. Webhook eslestirmesi icin.
    external_task_id: Mapped[str | None] = mapped_column(String(200), index=True)
    input_summary: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AIRun(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Tek bir AI cagrisi. Bir gorev birden fazla cagri icerebilir (tekrar deneme)."""

    __tablename__ = "ai_runs"

    ai_task_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_tasks.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    provider: Mapped[AIProviderName] = mapped_column(
        Enum(AIProviderName, name="ai_provider"), nullable=False
    )
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[AITaskStatus] = mapped_column(
        Enum(AITaskStatus, name="ai_task_status"), nullable=False
    )
    error_code: Mapped[str | None] = mapped_column(String(100))
    # Cikti metninin ozeti. Ayni ciktinin tekrar uretildigini anlamak icin.
    output_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    confidence: Mapped[str | None] = mapped_column(String(20))


class AICostEvent(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Musteri bazinda AI harcama kaydi. Butce siniri bunun uzerinden isler."""

    __tablename__ = "ai_cost_events"

    ai_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_runs.id", ondelete="SET NULL")
    )
    provider: Mapped[AIProviderName] = mapped_column(
        Enum(AIProviderName, name="ai_provider"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    amount_usd: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
