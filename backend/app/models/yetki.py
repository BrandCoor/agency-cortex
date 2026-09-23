"""Rol bazli izin ozellestirmeleri.

Her musteri icin, her rolun hangi izne sahip oldugu burada tutulur.
YALNIZCA VARSAYILANDAN FARKLI olanlar saklanir; boylece varsayilan
degistiginde ozellestirilmemis roller yeni varsayilani alir.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Enum, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamps, UUIDPrimaryKey, WorkspaceScoped
from app.models.enums import WorkspaceRole


class RoleGrant(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Bir musteride bir rolun bir izne sahip olup olmadigi."""

    __tablename__ = "role_grants"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "role", "permission", name="uq_role_grant"
        ),
    )

    role: Mapped[WorkspaceRole] = mapped_column(
        Enum(WorkspaceRole, name="workspace_role"), nullable=False, index=True
    )
    permission: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
