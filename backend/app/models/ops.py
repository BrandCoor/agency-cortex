"""Onaylar, bildirimler, webhook kayitlari, denetim kaydi ve hatalar."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamps, UUIDPrimaryKey, WorkspaceScoped
from app.models.enums import ContentStatus


class Approval(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Insan onayi kaydi.

    Yayin, yorum ve mesaj gonderimi yalnizca burada `APPROVED` kaydi varsa
    mumkundur. Bu tablo sistemin guvenlik kilididir.
    """

    __tablename__ = "approvals"

    # "content_script" | "report" | "campaign"
    subject_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    subject_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    status: Mapped[ContentStatus] = mapped_column(
        Enum(ContentStatus, name="content_status"), nullable=False
    )
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comment: Mapped[str | None] = mapped_column(Text)
    # Onay aninda icerigin neye benzedigi. Sonradan degistirilirse fark edilir.
    snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class Notification(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Kullaniciya gosterilecek bildirim."""

    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class WebhookEvent(UUIDPrimaryKey, Timestamps, Base):
    """Disaridan gelen webhook bildirimi.

    `provider` + `external_event_id` benzersizdir: ayni bildirim ikinci kez
    gelirse tekrar islenmez (idempotency).
    """

    __tablename__ = "webhooks"
    __table_args__ = (
        UniqueConstraint("provider", "external_event_id", name="uq_webhook_event"),
    )

    # Calisma alani bildirim cozuldukten SONRA belli olur; bu yuzden zorunlu degil.
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    external_event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signature_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)


class AuditLog(UUIDPrimaryKey, Timestamps, Base):
    """Kim, ne zaman, neyi degistirdi.

    Silinmez ve degistirilmez. Guvenlik incelemesinin temelidir.
    """

    __tablename__ = "audit_logs"

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="SET NULL"), index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    subject_type: Mapped[str | None] = mapped_column(String(50))
    subject_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class SystemError(UUIDPrimaryKey, Timestamps, Base):
    """Yakalanan sistem hatalari. Sorunlar gizlenmez, kaydedilir."""

    __tablename__ = "system_errors"

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="SET NULL"), index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    component: Mapped[str] = mapped_column(String(100), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100), index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SystemSetting(UUIDPrimaryKey, Timestamps, Base):
    """Panelden girilen sistem ayarlari (API anahtarlari dahil).

    NEDEN VERITABANINDA?
    Bu degerler kuruluma degil, ajansin hesaplarina aittir ve zamanla
    degisir. Her degisiklik icin sunucuya girmek gerekmemeli.

    NEDEN SIFRELI?
    Deger, Fernet ile sifrelenmis olarak saklanir. Veritabani yedegi ele
    gecse bile anahtarlar dogrudan okunamaz; cozmek icin sunucudaki
    ENCRYPTION_KEY de gerekir.

    HICBIR ZAMAN GERI GOSTERILMEZ.
    Panel yalnizca "tanimli / tanimsiz" bilgisini ve son dort karakteri
    gosterir. Tam deger ekrana da loga da basilmaz.
    """

    __tablename__ = "system_settings"
    __table_args__ = (UniqueConstraint("anahtar", name="uq_system_setting_anahtar"),)

    anahtar: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # Fernet ile sifrelenmis deger.
    sifreli_deger: Mapped[str] = mapped_column(Text, nullable=False)
    # Kullaniciya "hangi anahtari girmistim?" dedirtmemek icin son 4 karakter.
    son_dort: Mapped[str | None] = mapped_column(String(8))
    # Kim, ne zaman degistirdi (denetim icin).
    degistiren_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
