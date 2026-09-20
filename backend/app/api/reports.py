"""Rapor uclari."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import DbSession, Workspace_, WorkspaceContext, require_role
from app.models.enums import ReportPeriod, WorkspaceRole
from app.models.reporting import Report, ReportSection
from app.services.reports import generate_report

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/reports", tags=["raporlar"])


@router.get("", summary="Raporlari listele")
def list_reports(
    ctx: Workspace_,
    db: DbSession,
    period: Annotated[ReportPeriod | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[dict]:
    sorgu = select(Report).where(Report.workspace_id == ctx.workspace_id)
    if period is not None:
        sorgu = sorgu.where(Report.period == period)

    raporlar = db.execute(
        sorgu.order_by(Report.period_start.desc()).limit(limit)
    ).scalars().all()

    return [
        {
            "id": str(r.id),
            "period": r.period.value,
            "period_start": r.period_start.isoformat(),
            "period_end": r.period_end.isoformat(),
            "title": r.title,
            "status": r.status.value,
            "has_data_issues": bool(r.data_quality_notes),
        }
        for r in raporlar
    ]


@router.get("/{report_id}", summary="Rapor ayrintisi")
def get_report(report_id: uuid.UUID, ctx: Workspace_, db: DbSession) -> dict:
    rapor = db.execute(
        select(Report).where(
            Report.id == report_id,
            # Baska musterinin raporu okunamaz.
            Report.workspace_id == ctx.workspace_id,
        )
    ).scalar_one_or_none()

    if rapor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rapor bulunamadi.")

    bolumler = db.execute(
        select(ReportSection)
        .where(ReportSection.report_id == rapor.id)
        .order_by(ReportSection.order_index)
    ).scalars().all()

    return {
        "id": str(rapor.id),
        "period": rapor.period.value,
        "period_start": rapor.period_start.isoformat(),
        "period_end": rapor.period_end.isoformat(),
        "title": rapor.title,
        "status": rapor.status.value,
        "assumptions": rapor.assumptions,
        "data_quality_notes": rapor.data_quality_notes,
        "sections": [
            {
                "heading": b.heading,
                "body": b.body,
                "data": b.data,
                # "fact": olcume dayali. "hypothesis": kanit yetersiz, yorum.
                "claim_type": b.claim_type,
            }
            for b in bolumler
        ],
    }


@router.post("/generate", summary="Raporu simdi uret")
def create_report(
    ctx: Annotated[WorkspaceContext, Depends(require_role(WorkspaceRole.STRATEGIST))],
    db: DbSession,
    period: Annotated[ReportPeriod, Query()] = ReportPeriod.DAILY,
    force: Annotated[bool, Query(description="Mevcut raporu yenile")] = False,
) -> dict:
    """Donem raporunu uretir.

    Ayni donemin raporu varsa yenisi uretilmez; `force=true` ile yenilenir.
    """
    rapor = generate_report(
        db,
        workspace_id=ctx.workspace_id,
        period=period,
        reference=date.today(),
        force=force,
    )
    db.commit()
    return {
        "id": str(rapor.id),
        "title": rapor.title,
        "period": rapor.period.value,
        "period_start": rapor.period_start.isoformat(),
        "data_quality_notes": rapor.data_quality_notes,
    }
