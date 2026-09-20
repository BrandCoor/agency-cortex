"""AI uclari: saglayici durumu, maliyet ve icerik uretimi."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.ai.base import AIProviderError
from app.ai.registry import provider_status
from app.api.deps import CurrentUser, DbSession, Workspace_, WorkspaceContext, require_role
from app.models.ai import AIRun, AITask
from app.models.brand import Brand
from app.models.enums import Platform, WorkspaceRole
from app.models.identity import Workspace
from app.services.ai_runner import BudgetExceeded, month_spend
from app.services.content import generate_scripts

router = APIRouter(prefix="/api/v1", tags=["yapay zeka"])


@router.get("/ai/providers", summary="AI saglayicilarinin gercek durumu")
def list_providers(_: CurrentUser) -> list[dict]:
    """Hangi saglayicinin gercekten calistigini bildirir.

    `using_fake` true ise sistem sahte saglayici ile calisiyordur;
    uretilen icerik gercek AI ciktisi DEGILDIR.
    """
    return provider_status()


@router.get("/workspaces/{workspace_id}/ai/usage", summary="AI kullanimi ve butce")
def ai_usage(ctx: Workspace_, db: DbSession) -> dict:
    workspace = db.get(Workspace, ctx.workspace_id)
    harcanan = month_spend(db, ctx.workspace_id)
    sinir = float(workspace.ai_monthly_budget_usd)

    gorev_sayisi = db.execute(
        select(func.count()).select_from(AITask)
        .where(AITask.workspace_id == ctx.workspace_id)
    ).scalar_one()

    son_calistirmalar = db.execute(
        select(AIRun).where(AIRun.workspace_id == ctx.workspace_id)
        .order_by(AIRun.created_at.desc()).limit(10)
    ).scalars().all()

    return {
        "month": datetime.now(UTC).strftime("%Y-%m"),
        "spent_usd": float(harcanan),
        "budget_usd": sinir,
        "remaining_usd": max(0.0, sinir - float(harcanan)),
        "budget_exceeded": float(harcanan) >= sinir,
        "task_count": gorev_sayisi,
        "recent_runs": [
            {
                "model": r.model,
                "prompt_version": r.prompt_version,
                "attempt": r.attempt,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "cost_usd": float(r.estimated_cost_usd) if r.estimated_cost_usd else None,
                "latency_ms": r.latency_ms,
                "status": r.status.value,
                "error_code": r.error_code,
            }
            for r in son_calistirmalar
        ],
    }


class ScriptRequest(BaseModel):
    brand_id: uuid.UUID
    platforms: list[Platform] = Field(min_length=1, max_length=6)
    brief: str = Field(min_length=10, max_length=2000)


@router.post(
    "/workspaces/{workspace_id}/ai/content-scripts",
    summary="Icerik senaryosu uret",
)
def create_scripts(
    payload: ScriptRequest,
    ctx: Annotated[WorkspaceContext, Depends(require_role(WorkspaceRole.STRATEGIST))],
    db: DbSession,
) -> dict:
    """Marka baglamina gore platforma ozel senaryolar uretir.

    Uretilen senaryolar TASLAK durumundadir ve insan onayi bekler.
    """
    marka = db.execute(
        select(Brand).where(
            Brand.id == payload.brand_id,
            # Baska musterinin markasi kullanilamaz.
            Brand.workspace_id == ctx.workspace_id,
        )
    ).scalar_one_or_none()

    if marka is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marka bulunamadi.")

    workspace = db.get(Workspace, ctx.workspace_id)

    try:
        sonuc = generate_scripts(
            db, workspace=workspace, brand=marka,
            platforms=payload.platforms, brief=payload.brief,
        )
    except BudgetExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(exc)
        ) from exc
    except AIProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    db.commit()

    return {
        "idea_id": str(sonuc.idea.id),
        "title": sonuc.idea.title,
        "was_duplicate": sonuc.was_duplicate,
        "ai_task_id": str(sonuc.ai_task_id),
        # Yasakli ifade bulunduysa bu ACIKCA bildirilir.
        "forbidden_phrase_violations": sonuc.violations,
        "scripts": [
            {
                "id": str(s.id),
                "platform": s.platform.value,
                "format": s.format.value,
                "hook": s.hook,
                "duration_seconds": s.duration_seconds,
                "status": s.status.value,
                "human_approval_required": s.human_approval_required,
                "brand_risks": s.brand_risks,
                "claims_to_verify": s.claims_to_verify,
            }
            for s in sonuc.scripts
        ],
    }


@router.get("/workspaces/{workspace_id}/content-scripts/{script_id}", summary="Senaryo ayrintisi")
def get_script(script_id: uuid.UUID, ctx: Workspace_, db: DbSession) -> dict:
    from app.models.content import ContentScript

    s = db.execute(
        select(ContentScript).where(
            ContentScript.id == script_id,
            ContentScript.workspace_id == ctx.workspace_id,
        )
    ).scalar_one_or_none()

    if s is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Senaryo bulunamadi.")

    return {
        "id": str(s.id),
        "platform": s.platform.value,
        "format": s.format.value,
        "hook": s.hook,
        "duration_seconds": s.duration_seconds,
        "scene_plan": s.scene_plan,
        "spoken_script": s.spoken_script,
        "on_screen_text": s.on_screen_text,
        "visual_production_brief": s.visual_production_brief,
        "caption": s.caption,
        "cta": s.cta,
        "alternative_hooks": s.alternative_hooks,
        "required_assets": s.required_assets,
        "production_difficulty": s.production_difficulty,
        "brand_risks": s.brand_risks,
        "claims_to_verify": s.claims_to_verify,
        "status": s.status.value,
        "human_approval_required": s.human_approval_required,
    }
