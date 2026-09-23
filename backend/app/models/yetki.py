"""Kullanici bazli izin ozellestirmeleri.

ONCEDEN: izinler (musteri, rol) ciftine baglilydi. Ayni kisi bir
musteride editor, digerinde stratejist olabiliyordu ve "bu kullanici
neyi yapabilir?" sorusunun TEK bir cevabi yoktu. Yetki ekrani da her
musterinin altinda ayri ayri duruyordu.

SIMDI: izinler KULLANICIYA aittir. Musteri uyeligi yalnizca "bu kisi
hangi musterilerde calisiyor" sorusunu yanitlar.

Burada YALNIZCA pakete gore varsayilandan FARKLI olan satirlar tutulur.
Boylece bir paketin varsayilani ileride degisirse, ozellestirilmemis
kullanicilar yeni varsayilani alir.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import Timestamps, UUIDPrimaryKey


class UserPermission(UUIDPrimaryKey, Timestamps, Base):
    """Bir kullanicinin paketinden farklilasan tek bir izni."""

    __tablename__ = "user_permissions"
    __table_args__ = (
        UniqueConstraint("user_id", "permission", name="uq_user_permission"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    permission: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
