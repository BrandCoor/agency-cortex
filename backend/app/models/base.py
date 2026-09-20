"""Tum modellerin ortak parcalari."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class UUIDPrimaryKey:
    """Sayisal id yerine tahmin edilemez kimlik.

    Sirali sayilar, baska musterilerin kayit sayisini ve varligini ele verir
    (ornegin /workspaces/1, /workspaces/2 denenerek). UUID bunu engeller.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class Timestamps:
    """Her kaydin ne zaman olusturuldugu ve guncellendigi."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class WorkspaceScoped:
    """Musteriye ait her tablonun tasimasi gereken alan.

    Bu alan olmadan bir tablo musteri verisi tutamaz; izolasyon bunun
    uzerine kuruludur.
    """

    @declared_attr
    def workspace_id(cls) -> Mapped[uuid.UUID]:  # noqa: N805
        return mapped_column(
            PGUUID(as_uuid=True),
            ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
