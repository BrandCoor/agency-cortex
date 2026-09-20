"""Platform durumu ve sosyal hesap uclari.

`/platforms` ucu, hangi platformun GERCEKTEN calistigini durustce bildirir.
Henuz gelistirilmemis platformlar "available: false" olarak gorunur.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, Workspace_, WorkspaceContext, require_role
from app.core.logging_config import get_logger
from app.models.enums import Platform, WorkspaceRole
from app.models.social import SocialAccount
from app.platforms.registry import get_adapter, platform_status
from app.services.sync import sync_social_account

router = APIRouter(prefix="/api/v1", tags=["platformlar"])
log = get_logger("platforms")


@router.get("/platforms", summary="Platformlarin gercek durumu")
def list_platforms(_: CurrentUser) -> list[dict]:
    """Her platformun calisir olup olmadigini ve hangi isleri yapabildigini doner."""
    return platform_status()


@router.get("/workspaces/{workspace_id}/social-accounts", summary="Bagli hesaplar")
def list_social_accounts(ctx: Workspace_, db: DbSession) -> list[dict]:
    accounts = db.execute(
        select(SocialAccount)
        .where(SocialAccount.workspace_id == ctx.workspace_id)
        .order_by(SocialAccount.created_at)
    ).scalars()

    return [
        {
            "id": str(a.id),
            "platform": a.platform.value,
            "username": a.username,
            "display_name": a.display_name,
            "is_professional": a.is_professional,
            "is_active": a.is_active,
            "last_synced_at": a.last_synced_at.isoformat() if a.last_synced_at else None,
            "sync_error": a.sync_error,
        }
        for a in accounts
    ]


@router.post(
    "/workspaces/{workspace_id}/social-accounts/{account_id}/sync",
    summary="Hesabi simdi senkronize et",
)
def sync_account(
    account_id: uuid.UUID,
    ctx: Annotated[WorkspaceContext, Depends(require_role(WorkspaceRole.STRATEGIST))],
    db: DbSession,
) -> dict:
    """Hesabin icerik ve metriklerini ceker.

    Tekrar calistirilabilir: ayni veri iki kez yazilmaz.
    """
    account = db.execute(
        select(SocialAccount).where(
            SocialAccount.id == account_id,
            # Baska musterinin hesabi senkronize edilemez.
            SocialAccount.workspace_id == ctx.workspace_id,
        )
    ).scalar_one_or_none()

    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hesap bulunamadi.")

    adapter = get_adapter(account.platform)
    result = sync_social_account(db, account=account, adapter=adapter)
    db.commit()

    return {
        "media_seen": result.media_seen,
        "media_created": result.media_created,
        "raw_stored": result.raw_stored,
        "raw_skipped_duplicate": result.raw_skipped_duplicate,
        "metrics_written": result.metrics_written,
        "account_metrics_written": result.account_metrics_written,
        "errors": result.errors,
    }


@router.get(
    "/workspaces/{workspace_id}/platforms/{platform}/health",
    summary="Platform saglik kontrolu",
)
def platform_health(platform: Platform, ctx: Workspace_) -> dict:
    adapter = get_adapter(platform)
    health = adapter.health_check()
    return {
        "platform": platform.value,
        "ok": health.ok,
        "detail": health.detail,
        "capabilities": sorted(c.value for c in adapter.capabilities),
    }
