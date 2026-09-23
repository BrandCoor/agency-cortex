"""Kullanicilar, musteri calisma alanlari ve uyelikler.

Bu dosyadaki `workspace_id` alanlari sistemin en kritik guvenlik sinirini
olusturur: bir musterinin verisi digerinden bu alanla ayrilir.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import Timestamps, UUIDPrimaryKey
from app.models.enums import PermissionPackage


class User(UUIDPrimaryKey, Timestamps, Base):
    """Sisteme giris yapan kisi (ajans calisani veya musteri temsilcisi)."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Sifrenin kendisi DEGIL, geri cevrilemez ozeti saklanir.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Sistem yoneticisi. Calisma alani verisine otomatik erisim VERMEZ.
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Hazir yetki paketi. Yalnizca BASLANGIC noktasidir; her izin kullanici
    # bazinda tek tek acilip kapatilabilir (bkz. models/yetki.py).
    permission_package: Mapped[PermissionPackage] = mapped_column(
        Enum(PermissionPackage, name="permission_package"),
        default=PermissionPackage.VIEWER, nullable=False,
    )

    memberships: Mapped[list[WorkspaceMember]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Workspace(UUIDPrimaryKey, Timestamps, Base):
    """Bir musteri. Tum veri izolasyonunun merkezi."""

    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Istanbul", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Bu musteri icin aylik AI harcama siniri (USD). Asilirsa yeni AI isi baslamaz.
    ai_monthly_budget_usd: Mapped[float] = mapped_column(default=50.0, nullable=False)

    members: Mapped[list[WorkspaceMember]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )


class WorkspaceMember(UUIDPrimaryKey, Timestamps, Base):
    """Hangi kullanicinin hangi musteride calistigi.

    YETKI BILGISI TASIMAZ. Bir kisinin neyi yapabilecegi kullanicinin
    kendisinde tutulur (users.permission_package + user_permissions).
    Burasi yalnizca ERISIMI belirler: uyelik varsa o musteri gorunur.

    Onceden burada bir `role` sutunu vardi. Ayni kisi iki musteride iki
    farkli yetkide olabiliyordu ve "bu kullanici neyi yapabilir?"
    sorusunun tek bir cevabi yoktu.
    """

    __tablename__ = "workspace_members"
    __table_args__ = (
        # Ayni kullanici ayni calisma alaninda iki kez yer alamaz.
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    workspace: Mapped[Workspace] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")
