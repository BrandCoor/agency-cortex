"""Makine kimlikleri ve otomasyon calistirmalari.

MIMARI (DECISIONS.md K-032): n8n bir OTOMASYON MOTORUDUR, ikinci bir
uygulama degildir. Is akislari veritabanina dogrudan yazmaz; her zaman
Agency Cortex API'sinden gecer. Bu tablolar o gecisi denetlenebilir kilar.

GUVENLIK: n8n bir INSAN HESABI kullanmaz. Kendi makine kimligi vardir;
kapsami dardir, iptal edilebilir ve her kullanimi kaydedilir.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import Timestamps, UUIDPrimaryKey, WorkspaceScoped
from app.models.enums import AutomationStatus, AutomationTrigger


class ApiClient(UUIDPrimaryKey, Timestamps, Base):
    """Makine kimligi (n8n gibi bir sistemin API hesabi).

    ANAHTAR SAKLANMAZ. Yalnizca SHA-256 ozeti tutulur; veritabanina erisen
    biri anahtari geri uretemez. Ozet icin Argon2 degil SHA-256 kullanildi:
    anahtar 32 bayt rastgeledir, sozluk saldirisi mumkun degildir ve her
    istekte Argon2 calistirmak API'yi yavaslatirdi (bkz. DECISIONS.md K-033).
    """

    __tablename__ = "api_clients"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Anahtarin bas kismi: listede tanimak ve aramak icin. Gizli DEGILDIR.
    key_prefix: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    workspaces: Mapped[list[ApiClientWorkspace]] = relationship(
        back_populates="api_client", cascade="all, delete-orphan"
    )


class ApiClientWorkspace(UUIDPrimaryKey, Timestamps, Base):
    """Bu makine kimliginin HANGI musteride is yapabilecegi.

    Bu tablo olmadan n8n istedigi workspace_id'yi gonderip baska bir
    musterinin verisine yazabilirdi. Istekle gelen workspace_id ASLA tek
    basina yeterli degildir; burada karsiligi olmak zorundadir.
    """

    __tablename__ = "api_client_workspaces"
    __table_args__ = (
        UniqueConstraint("api_client_id", "workspace_id", name="uq_api_client_workspace"),
    )

    api_client_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("api_clients.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    api_client: Mapped[ApiClient] = relationship(back_populates="workspaces")


class AutomationSetting(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Bir musteride bir is akisi acik mi?

    Varsayilan KAPALIDIR. Bir musteri icin otomasyon, panelden bilerek
    acilmadan calismaz.
    """

    __tablename__ = "automation_settings"
    __table_args__ = (
        UniqueConstraint("workspace_id", "workflow_key", name="uq_automation_setting"),
    )

    workflow_key: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AutomationRun(UUIDPrimaryKey, WorkspaceScoped, Timestamps, Base):
    """Bir is akisinin tek bir calismasi.

    Panelin "en son ne zaman calisti, basarili miydi, hata neydi"
    sorularina cevap verdigi yer burasidir. Basarisizlik GIZLENMEZ.
    """

    __tablename__ = "automation_runs"

    workflow_key: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    status: Mapped[AutomationStatus] = mapped_column(
        Enum(AutomationStatus, name="automation_status"), nullable=False, index=True
    )
    trigger: Mapped[AutomationTrigger] = mapped_column(
        Enum(AutomationTrigger, name="automation_trigger"), nullable=False
    )
    # n8n'in kendi calistirma kimligi: bir sorunda n8n kayitlarina bakilabilsin.
    external_execution_id: Mapped[str | None] = mapped_column(String(100), index=True)
    api_client_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("api_clients.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    # Ne yapildi: sayisal ozet ("kac hesap tarandi", "kac trend bulundu").
    # Ham API yaniti BURAYA YAZILMAZ.
    summary: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
