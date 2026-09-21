"""AI cagrilarinin yurutulmesi, muhasebesi ve butce kontrolu.

HER AI CAGRISI BURADAN GECER. Dogrudan saglayici cagirmak yasaktir; aksi
halde maliyet kaydi tutulmaz ve butce siniri islemez.

YAPILANLAR:
1. Aylik butce kontrolu - ATOMIK; ayni anda calisan iki is butceyi asamaz
   (bkz. app/services/ai_butce.py)
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
from app.services.ai_butce import (
    BudgetExceeded,
    check_budget,
    kesinlestir,
    month_spend,
    rezerve_et,
    serbest_birak,
)

log = get_logger("ai_runner")

# Butce mantigi ai_butce.py'ye tasindi; eski cagri noktalari bozulmasin diye
# adlar buradan da erisilebilir kalir.
__all__ = [
    "BudgetExceeded",
    "RunResult",
    "available_task_types",
    "check_budget",
    "month_spend",
    "run_ai_task",
]


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
    # 1) Butce on kontrolu - bos yere kayit acilmasin diye.
    # Esszamanlilik guvencesi asagidaki rezervasyondadir.
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
        aciklama = f"{task_type} (deneme {deneme})"

        # 1b) ATOMIK butce kontrolu: cagriDAN ONCE tahmini tutar rezerve
        # edilir. Ayni anda calisan ikinci is bu rezervasyonu gorur.
        try:
            rezervasyon = rezerve_et(
                workspace_id=workspace.id,
                provider=gorev.provider,
                tutar=saglayici.tahmini_ust_maliyet(istek),
                aciklama=aciklama,
            )
        except BudgetExceeded:
            gorev.status = AITaskStatus.FAILED
            gorev.error_code = "BudgetExceeded"
            gorev.finished_at = datetime.now(UTC)
            db.flush()
            raise

        try:
            yanit = saglayici.complete(istek)
        except AIProviderError as exc:
            # Cagri yapilamadi; ayrilan butce geri birakilir.
            if rezervasyon is not None:
                serbest_birak(rezervasyon)
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

        if rezervasyon is not None:
            # Rezervasyon gercek maliyete cekilir.
            kesinlestir(
                rezervasyon,
                gercek_tutar=yanit.estimated_cost_usd,
                aciklama=aciklama,
            )
        elif yanit.estimated_cost_usd:
            # Rezervasyon yapilamadi (fiyati bilinmeyen model) ama saglayici
            # maliyet bildirdi: kayit yine de tutulur.
            db.add(
                AICostEvent(
                    workspace_id=workspace.id,
                    provider=gorev.provider,
                    occurred_at=datetime.now(UTC),
                    amount_usd=yanit.estimated_cost_usd,
                    description=aciklama,
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
