"""Onay uclari."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DbSession, Workspace_
from app.models.content import ContentScript
from app.models.enums import ContentStatus
from app.models.reporting import Report
from app.services.approvals import (
    ALLOWED_TRANSITIONS,
    ApprovalError,
    PublishingLocked,
    approval_history,
    can_publish,
    transition,
)

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["onay"])


class TransitionRequest(BaseModel):
    target: ContentStatus
    comment: str | None = Field(default=None, max_length=2000)


def _bul(db, ctx, subject_type: str, subject_id: uuid.UUID):
    model = ContentScript if subject_type == "content_script" else Report
    nesne = db.execute(
        select(model).where(
            model.id == subject_id,
            # Baska musterinin icerigi onaylanamaz.
            model.workspace_id == ctx.workspace_id,
        )
    ).scalar_one_or_none()
    if nesne is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bulunamadi.")
    return nesne


@router.get("/approvals/queue", summary="Onay bekleyenler")
def approval_queue(
    ctx: Workspace_,
    db: DbSession,
    durum: Annotated[ContentStatus | None, Query()] = None,
) -> dict:
    """Insan karari bekleyen icerik ve raporlar."""
    bekleyen_durumlar = (
        [durum] if durum
        else [ContentStatus.INTERNAL_REVIEW, ContentStatus.CLIENT_REVIEW]
    )

    senaryolar = db.execute(
        select(ContentScript).where(
            ContentScript.workspace_id == ctx.workspace_id,
            ContentScript.status.in_(bekleyen_durumlar),
        ).order_by(ContentScript.created_at.desc()).limit(100)
    ).scalars().all()

    raporlar = db.execute(
        select(Report).where(
            Report.workspace_id == ctx.workspace_id,
            Report.status.in_(bekleyen_durumlar),
        ).order_by(Report.period_start.desc()).limit(100)
    ).scalars().all()

    return {
        "scripts": [
            {
                "id": str(s.id),
                "platform": s.platform.value,
                "format": s.format.value,
                "hook": s.hook,
                "status": s.status.value,
                "has_risks": bool(s.brand_risks),
                "needs_verification": bool(s.claims_to_verify),
            }
            for s in senaryolar
        ],
        "reports": [
            {
                "id": str(r.id),
                "title": r.title,
                "period": r.period.value,
                "status": r.status.value,
                "has_data_issues": bool(r.data_quality_notes),
            }
            for r in raporlar
        ],
    }


@router.get("/{subject_type}/{subject_id}/approvals", summary="Onay gecmisi")
def get_history(
    subject_type: str, subject_id: uuid.UUID, ctx: Workspace_, db: DbSession
) -> list[dict]:
    if subject_type not in ("content_script", "report"):
        raise HTTPException(status_code=400, detail="Gecersiz tur.")

    return [
        {
            "status": a.status.value,
            "decided_at": a.decided_at.isoformat() if a.decided_at else None,
            "decided_by": str(a.decided_by_user_id) if a.decided_by_user_id else None,
            "comment": a.comment,
        }
        for a in approval_history(
            db, workspace_id=ctx.workspace_id,
            subject_type=subject_type, subject_id=subject_id,
        )
    ]


@router.post("/{subject_type}/{subject_id}/transition", summary="Durum degistir")
def change_status(
    subject_type: str,
    subject_id: uuid.UUID,
    payload: TransitionRequest,
    ctx: Workspace_,
    db: DbSession,
    request: Request,
) -> dict:
    """Icerigi veya raporu yeni duruma gecirir.

    Tum kontroller onay servisinde yapilir; bu uc yalnizca cagirir.
    """
    if subject_type not in ("content_script", "report"):
        raise HTTPException(status_code=400, detail="Gecersiz tur.")

    nesne = _bul(db, ctx, subject_type, subject_id)

    try:
        sonuc = transition(
            db,
            workspace_id=ctx.workspace_id,
            actor_user_id=ctx.user.id,
            actor_role=ctx.role,
            subject=nesne,
            target=payload.target,
            comment=payload.comment,
            request_id=request.headers.get("x-request-id"),
        )
    except PublishingLocked as exc:
        # Yayin kilidi bir "hata" degil, bilincli bir urun kuralidir.
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=str(exc)) from exc
    except ApprovalError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    db.commit()

    return {
        "subject_type": sonuc.subject_type,
        "subject_id": str(sonuc.subject_id),
        "previous_status": sonuc.previous_status.value,
        "new_status": sonuc.new_status.value,
        "next_possible": sorted(
            s.value for s in ALLOWED_TRANSITIONS.get(sonuc.new_status, set())
        ),
    }


@router.get("/content-scripts/{script_id}/publish-check", summary="Yayinlanabilir mi")
def publish_check(script_id: uuid.UUID, ctx: Workspace_, db: DbSession) -> dict:
    s = _bul(db, ctx, "content_script", script_id)
    olur, gerekce = can_publish(db, workspace_id=ctx.workspace_id, script=s)
    return {"can_publish": olur, "reason": gerekce, "status": s.status.value}
