"""AI is yurutucusu testleri.

Korunan kurallar:
- Aylik butce asilmissa cagri BASLAMAZ (beklenmedik fatura gelmez)
- Her cagri kaydedilir: model, istem surumu, token, maliyet, sure
- Basarisiz deneme de para harcar; maliyeti kaydedilir
- AI ciktisi dogrudan dogru kabul edilmez, semayla dogrulanir
- Sonsuz tekrar yapilmaz
- Bir musterinin AI kaydi digerine karismaz
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from app.ai.base import AIProvider, AIProviderError, AIResponse, AIStatus, SchemaValidationFailed
from app.ai.fake import FakeProvider
from app.ai.schemas import ContentScriptBatch
from app.models.ai import AICostEvent, AIRun, AITask
from app.models.enums import AITaskStatus
from app.services.ai_runner import BudgetExceeded, check_budget, month_spend, run_ai_task


class Basit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: str


def _calistir(db, workspace, **kw):
    varsayilan = dict(
        workspace=workspace,
        task_type="content_script",
        prompt_version="v1",
        system="sistem",
        user_content="kullanici",
        output_model=ContentScriptBatch,
        metadata={"platforms": ["instagram"]},
        provider=FakeProvider(),
    )
    varsayilan.update(kw)
    return run_ai_task(db, **varsayilan)


# --- Butce kontrolu ----------------------------------------------------------

def test_butce_asilmamissa_cagri_calisir(db, make_workspace):
    ws = make_workspace(name="Butce Testi")
    sonuc = _calistir(db, ws)
    assert sonuc.parsed["scripts"]


def test_butce_asilmissa_cagri_baslamaz(db, make_workspace):
    """Beklenmedik fatura gelmemesi icin kontrol cagriDAN ONCE yapilir."""
    ws = make_workspace(name="Butce Dolu")
    ws.ai_monthly_budget_usd = 10.0
    db.add(AICostEvent(
        workspace_id=ws.id, provider="claude", occurred_at=datetime.now(UTC),
        amount_usd=Decimal("10.50"), description="onceki harcama",
    ))
    db.flush()

    with pytest.raises(BudgetExceeded):
        _calistir(db, ws)

    # Hicbir AI isi olusturulmamis olmali.
    assert db.execute(
        select(func.count()).select_from(AITask).where(AITask.workspace_id == ws.id)
    ).scalar_one() == 0


def test_butce_tam_sinirda_da_engellenir(db, make_workspace):
    ws = make_workspace(name="Tam Sinir")
    ws.ai_monthly_budget_usd = 5.0
    db.add(AICostEvent(
        workspace_id=ws.id, provider="claude", occurred_at=datetime.now(UTC),
        amount_usd=Decimal("5.00"), description="tam sinir",
    ))
    db.flush()
    with pytest.raises(BudgetExceeded):
        check_budget(db, ws)


def test_gecen_ayin_harcamasi_bu_ayi_engellemez(db, make_workspace):
    """Butce AYLIK'tir; gecen ayin harcamasi bu ayi kilitlememeli."""
    ws = make_workspace(name="Gecen Ay")
    ws.ai_monthly_budget_usd = 10.0
    gecen_ay = datetime.now(UTC).replace(day=1) - timedelta(days=5)
    db.add(AICostEvent(
        workspace_id=ws.id, provider="claude", occurred_at=gecen_ay,
        amount_usd=Decimal("50.00"), description="gecen ay",
    ))
    db.flush()

    assert month_spend(db, ws.id) == Decimal("0")
    check_budget(db, ws)  # hata firlatmamali


def test_baska_musterinin_harcamasi_sayilmaz(db, make_workspace):
    ws_a = make_workspace(name="A")
    ws_b = make_workspace(name="B")
    ws_a.ai_monthly_budget_usd = 10.0
    db.add(AICostEvent(
        workspace_id=ws_b.id, provider="claude", occurred_at=datetime.now(UTC),
        amount_usd=Decimal("100.00"), description="B musterisi",
    ))
    db.flush()

    assert month_spend(db, ws_a.id) == Decimal("0")
    check_budget(db, ws_a)


# --- Muhasebe ----------------------------------------------------------------

def test_her_cagri_kaydedilir(db, make_workspace):
    ws = make_workspace(name="Kayit")
    sonuc = _calistir(db, ws)

    gorev = db.get(AITask, sonuc.task_id)
    assert gorev.status is AITaskStatus.SUCCEEDED
    assert gorev.started_at and gorev.finished_at
    assert gorev.input_summary["prompt_version"] == "v1"

    calistirmalar = db.execute(
        select(AIRun).where(AIRun.ai_task_id == gorev.id)
    ).scalars().all()
    assert len(calistirmalar) == 1

    c = calistirmalar[0]
    # Urun tanimindaki zorunlu alanlarin hepsi kayitli olmali.
    assert c.model and c.prompt_version == "v1"
    assert c.input_tokens is not None and c.output_tokens is not None
    assert c.estimated_cost_usd is not None
    assert c.latency_ms is not None
    assert c.output_hash and len(c.output_hash) == 64
    assert c.attempt == 1


def test_cikti_parmak_izi_kaydedilir(db, make_workspace):
    ws = make_workspace(name="Parmak Izi")
    sonuc = _calistir(db, ws, metadata={"seed": "sabit", "platforms": ["instagram"]})
    c = db.execute(select(AIRun).where(AIRun.ai_task_id == sonuc.task_id)).scalar_one()
    assert c.output_hash == sonuc.output_hash


# --- Sema dogrulamasi --------------------------------------------------------

class BozukSaglayici(AIProvider):
    """Her zaman semaya uymayan cikti ureten saglayici."""

    name = "fake"
    model = "fake-model-v1"

    def __init__(self):
        self.cagri_sayisi = 0

    def complete(self, request):
        self.cagri_sayisi += 1
        return AIResponse(
            text='{"yanlis_alan": 1}', parsed={"yanlis_alan": 1},
            provider=self.name, model=self.model,
            prompt_version=request.prompt_version,
            input_tokens=10, output_tokens=5,
            estimated_cost_usd=Decimal("0"), latency_ms=100,
            status=AIStatus.SUCCEEDED,
        )

    def health_check(self):
        return True, None


def test_semaya_uymayan_cikti_reddedilir(db, make_workspace):
    """AI ciktisi DOGRUDAN DOGRU KABUL EDILMEZ."""
    ws = make_workspace(name="Bozuk Cikti")
    with pytest.raises(SchemaValidationFailed):
        _calistir(db, ws, provider=BozukSaglayici())


def test_sonsuz_tekrar_yapilmaz(db, make_workspace):
    """Her deneme para harcar; tekrar sayisi sinirlidir."""
    ws = make_workspace(name="Tekrar Siniri")
    saglayici = BozukSaglayici()
    with pytest.raises(SchemaValidationFailed):
        _calistir(db, ws, provider=saglayici, max_attempts=2)
    assert saglayici.cagri_sayisi == 2


def test_basarisiz_denemeler_de_kaydedilir(db, make_workspace):
    ws = make_workspace(name="Basarisiz Kayit")
    with pytest.raises(SchemaValidationFailed):
        _calistir(db, ws, provider=BozukSaglayici(), max_attempts=2)

    calistirmalar = db.execute(
        select(AIRun).where(AIRun.workspace_id == ws.id)
    ).scalars().all()
    assert len(calistirmalar) == 2
    assert all(c.error_code == "SchemaValidationFailed" for c in calistirmalar)


class PahaliBozukSaglayici(BozukSaglayici):
    """Basarisiz ama ucretli cagri."""

    def complete(self, request):
        yanit = super().complete(request)
        return AIResponse(
            **{**yanit.__dict__, "estimated_cost_usd": Decimal("0.25")}
        )


def test_basarisiz_cagrinin_maliyeti_de_kaydedilir(db, make_workspace):
    """Basarisiz deneme de para harcar; butceye yansimali."""
    ws = make_workspace(name="Basarisiz Maliyet")
    with pytest.raises(SchemaValidationFailed):
        _calistir(db, ws, provider=PahaliBozukSaglayici(), max_attempts=2)

    assert month_spend(db, ws.id) == Decimal("0.50")


# --- Saglayici hatalari ------------------------------------------------------

class HataliSaglayici(AIProvider):
    name = "fake"
    model = "fake-model-v1"

    def complete(self, request):
        raise AIProviderError("baglanti koptu")

    def health_check(self):
        return False, "hatali"


def test_saglayici_hatasi_kaydedilir_ve_gizlenmez(db, make_workspace):
    ws = make_workspace(name="Saglayici Hatasi")
    with pytest.raises(SchemaValidationFailed):
        _calistir(db, ws, provider=HataliSaglayici(), max_attempts=2)

    gorev = db.execute(select(AITask).where(AITask.workspace_id == ws.id)).scalar_one()
    assert gorev.status is AITaskStatus.FAILED
    assert gorev.error_message


def test_ai_kayitlari_dogru_musteriye_yazilir(db, make_workspace):
    ws_a = make_workspace(name="A")
    ws_b = make_workspace(name="B")
    _calistir(db, ws_a)
    db.flush()

    for model in (AITask, AIRun, AICostEvent):
        sayi = db.execute(
            select(func.count()).select_from(model).where(model.workspace_id == ws_b.id)
        ).scalar_one()
        assert sayi == 0, f"{model.__name__} baska musteriye yazilmis"
