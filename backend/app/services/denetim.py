"""Denetim kaydi: kim, ne zaman, neyi degistirdi.

Bu kayitlar SILINMEZ ve DEGISTIRILMEZ. Bir hesap ele gecirilirse veya bir
veri yanlislikla degistirilirse, geriye donuk tek guvenilir kaynak budur.

KURAL: `details` icine ASLA sifre, jeton, API anahtari veya bunlarin bir
parcasi yazilmaz. Yalnizca NE degistigi yazilir, YENI DEGER yazilmaz.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.ops import AuditLog


def _istek_bilgisi(request: Request | None) -> tuple[str | None, str | None]:
    if request is None:
        return None, None
    ip = request.client.host if request.client else None
    # Caddy arkasindayken gercek adres bu baslikta gelir.
    iletilen = request.headers.get("x-forwarded-for")
    if iletilen:
        ip = iletilen.split(",")[0].strip()
    return ip, request.headers.get("x-request-id")


def kaydet(
    db: Session,
    *,
    action: str,
    actor_user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    subject_type: str | None = None,
    subject_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
    request: Request | None = None,
) -> AuditLog:
    """Bir denetim satiri ekler. Cagiran taraf commit eder."""
    ip, istek_kimligi = _istek_bilgisi(request)
    kayit = AuditLog(
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        occurred_at=datetime.now(UTC),
        ip_address=ip,
        request_id=istek_kimligi,
        details=details or {},
    )
    db.add(kayit)
    return kayit
