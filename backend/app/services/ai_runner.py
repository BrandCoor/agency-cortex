"""AI cagrilarinin yurutulmesi, muhasebesi ve butce kontrolu.

HER AI CAGRISI BURADAN GECER. Dogrudan saglayici cagirmak yasaktir; aksi
halde maliyet kaydi tutulmaz ve butce siniri islemez.

YAPILANLAR:
1. Aylik butce kontrolu - sinir asilmissa cagri BASLAMAZ
2. ai_tasks ve ai_runs kayitlari
3. Sema dogrulamasi - hatali ciktida sinirli tekrar
4. Maliyet kaydi (ai_cost_events)
5. Musteri verisinin yanlis isteme karismamasi
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.base import (
    AIProvider,
    AIProviderError,
    AIRequest,
    SchemaValidationFailed,
)
from app.ai.registry import TASK_ROUTING, provider_for_task
from app.core.logging_config import get_logger
from app.models.ai import AICostEvent, AIRun, AITask
from app.models.enums import AIProviderName, AITaskStatus
from app.models.identity import Workspace

log = get_logger("ai_runner")


class BudgetExceeded(AIProviderError):
    """Aylik AI butcesi asildi; yeni cagri baslatilamaz.

    Beklenmedik fatura gelmemesi icin bu kontrol cagriDAN ONCE yapilir.
    """

    def __init__(self, workspace_id: uuid.UUID, spent: Decimal, limit: Decimal) -> None:
        super().__init__(
            f"Aylik AI butcesi asildi: {spent:.2f} / {limit:.2f} USD. "
            "Yeni AI isi baslatilmadi."
        )
        self.workspace_id = workspace_id
        self.spent = spent
        self.limit = limit


@dataclass
class RunResult:
    """Bir AI isinin sonucu."""

    task_id: uuid.UUID
    parsed: dict[str, Any]
    model: str
    provider: str
    attempts: int
    total_cost_usd: Decimal
    output_hash: str


def month_spend(db: Session, workspace_id: uuid.UUID, *, now: datetime | None = None) -> Decimal:
    """Bu ay icinde harcanan toplam AI tutari (USD)."""
    simdi = now or datetime.now(UTC)
    ay_basi = simdi.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    toplam = db.execute(
        select(func.coalesce(func.sum(AICostEvent.amount_usd), 0)).where(
            AICostEvent.workspace_id == workspace_id,
            AICostEvent.occurred_at >= ay_basi,
        )
    ).scalar_one()
    return Decimal(str(toplam))


def check_budget(db: Session, workspace: Workspace, *, now: datetime | None = None) -> None:
    """Butce asilmissa hata firlatir."""
    harcanan = month_spend(db, workspace.id, now=now)
    sinir = Decimal(str(workspace.ai_monthly_budget_usd))
    if harcanan >= sinir:
        log.warning(
            "butce_asildi",
            workspace_id=str(workspace.id),
            spent=str(harcanan),
            limit=str(sinir),
        )
        raise BudgetExceeded(workspace.id, harcanan, sinir)


def run_ai_task(
    db: Session,
    *,
    workspace: Workspace,
    task_type: str,
    prompt_version: str,
    system: str,
    user_content: str,
    output_model: type[BaseModel],
    metadata: dict[str, Any] | None = None,
    max_attempts: int = 2,
    effort: str = "high",
    provider: AIProvider | None = None,
) -> RunResult:
    """Bir AI isini bastan sona yurutur ve kaydeder.

    `max_attempts`: sema dogrulamasi basarisiz olursa kac kez tekrar istenir.
    Sonsuz tekrar YAPILMAZ - her deneme para harcar.
    """
    # 1) Butce kontrolu - cagriDAN ONCE
    check_budget(db, workspace)

    saglayici = provider or provider_for_task(task_type)
    sema = output_model.model_json_schema()

    gorev = AITask(
        workspace_id=workspace.id,
        task_type=task_type,
        status=AITaskStatus.RUNNING,
        provider=AIProviderName(
            saglayici.name if saglayici.name in AIProviderName._value2member_map_ else "fake"
        ),
        input_summary={
            "prompt_version": prompt_version,
            "system_chars": len(system),
            "user_chars": len(user_content),
            **(metadata or {}),
        },
        started_at=datetime.now(UTC),
    )
    db.add(gorev)
    db.flush()

    istek = AIRequest(
        task_type=task_type,
        prompt_version=prompt_version,
        system=system,
        user_content=user_content,
        json_schema=sema,
        effort=effort,
        metadata=metadata or {},
    )

    toplam_maliyet = Decimal("0")
    son_hata: str | None = None

    for deneme in range(1, max_attempts + 1):
        try:
            yanit = saglayici.complete(istek)
        except AIProviderError as exc:
            son_hata = f"{type(exc).__name__}: {exc}"
            _kaydet_run(
                db, gorev=gorev, workspace=workspace, provider=saglayici,
                attempt=deneme, prompt_version=prompt_version,
                response=None, error_code=type(exc).__name__,
            )
            log.warning(
                "ai_cagrisi_basarisiz",
                workspace_id=str(workspace.id),
                task_type=task_type,
                attempt=deneme,
                error_code=type(exc).__name__,
            )
            # Yapilandirma veya butce hatasinda tekrar denemek anlamsizdir.
            if type(exc).__name__ in ("ProviderNotConfigured", "ProviderNotImplemented"):
                break
            continue

        # Maliyet her denemede kaydedilir - basarisiz deneme de para harcar.
        if yanit.estimated_cost_usd is not None:
            toplam_maliyet += yanit.estimated_cost_usd
            db.add(
                AICostEvent(
                    workspace_id=workspace.id,
                    provider=gorev.provider,
                    occurred_at=datetime.now(UTC),
                    amount_usd=yanit.estimated_cost_usd,
                    description=f"{task_type} (deneme {deneme})",
                )
            )

        calistirma = _kaydet_run(
            db, gorev=gorev, workspace=workspace, provider=saglayici,
            attempt=deneme, prompt_version=prompt_version,
            response=yanit, error_code=None,
        )

        # 2) AI ciktisi DOGRUDAN DOGRU KABUL EDILMEZ
        try:
            dogrulanmis = output_model.model_validate(yanit.parsed or {})
        except ValidationError as exc:
            son_hata = str(exc)[:400]
            calistirma.status = AITaskStatus.FAILED
            calistirma.error_code = "SchemaValidationFailed"
            db.flush()
            log.warning(
                "ai_semasi_uymadi",
                workspace_id=str(workspace.id),
                task_type=task_type,
                attempt=deneme,
            )
            continue

        gorev.status = AITaskStatus.SUCCEEDED
        gorev.result = dogrulanmis.model_dump()
        gorev.finished_at = datetime.now(UTC)
        db.flush()

        log.info(
            "ai_isi_tamamlandi",
            workspace_id=str(workspace.id),
            ai_task_id=str(gorev.id),
            task_type=task_type,
            provider=saglayici.name,
            model=yanit.model,
            prompt_version=prompt_version,
            attempts=deneme,
            total_cost_usd=str(toplam_maliyet),
        )

        return RunResult(
            task_id=gorev.id,
            parsed=dogrulanmis.model_dump(),
            model=yanit.model,
            provider=saglayici.name,
            attempts=deneme,
            total_cost_usd=toplam_maliyet,
            output_hash=yanit.output_hash,
        )

    gorev.status = AITaskStatus.FAILED
    gorev.error_code = "SchemaValidationFailed"
    gorev.error_message = son_hata
    gorev.finished_at = datetime.now(UTC)
    db.flush()

    raise SchemaValidationFailed(son_hata or "bilinmeyen hata", attempts=max_attempts)


def _kaydet_run(
    db: Session,
    *,
    gorev: AITask,
    workspace: Workspace,
    provider: AIProvider,
    attempt: int,
    prompt_version: str,
    response: Any,
    error_code: str | None,
) -> AIRun:
    """Tek bir AI cagrisinin muhasebesini kaydeder."""
    calistirma = AIRun(
        workspace_id=workspace.id,
        ai_task_id=gorev.id,
        provider=gorev.provider,
        model=response.model if response else provider.model,
        prompt_version=prompt_version,
        attempt=attempt,
        input_tokens=response.input_tokens if response else None,
        output_tokens=response.output_tokens if response else None,
        estimated_cost_usd=response.estimated_cost_usd if response else None,
        latency_ms=response.latency_ms if response else None,
        status=AITaskStatus.SUCCEEDED if response else AITaskStatus.FAILED,
        error_code=error_code,
        output_hash=response.output_hash if response else None,
        confidence=response.confidence if response else None,
    )
    db.add(calistirma)
    db.flush()
    return calistirma


def available_task_types() -> list[str]:
    return sorted(TASK_ROUTING)
