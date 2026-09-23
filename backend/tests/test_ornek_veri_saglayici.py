"""Ornek veri (sahte) saglayicisi semaya UYMAK ZORUNDA.

NEDEN BU DOSYA VAR:
Ornek veri modunda WF-02 (trend arastirmasi) her calismada HATA
veriyordu: "AI ciktisi 2 denemede de beklenen yapiya uymadi". Sebebi,
sahte saglayicinin 'trend_research' gorev turunu tanimamasi ve
{"result": "sahte-cikti-..."} donmesiydi. Bu deger hicbir semaya uymaz.

Panelde kirmizi bir hata goruluyordu ama kimse nedenini bilmiyordu ve
sistem "calisiyor" saniliyordu. Asagidaki testler, kodda kullanilan HER
gorev turunun sahte saglayicida gecerli cikti uretmesini zorunlu kilar.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.ai.base import AIRequest
from app.ai.fake import FakeProvider
from app.ai.schemas import (
    CompetitorResearchBatch,
    ContentScriptBatch,
    StrategicCommentary,
    TrendResearchBatch,
)

#: Gorev turu -> ciktisinin uymasi gereken sema.
GOREV_SEMALARI = {
    "content_script": ContentScriptBatch,
    "trend_research": TrendResearchBatch,
    "strategic_commentary": StrategicCommentary,
    "competitor_research": CompetitorResearchBatch,
}


def _istek(gorev: str) -> AIRequest:
    return AIRequest(
        task_type=gorev,
        prompt_version="test-1",
        system="test",
        user_content="test",
        json_schema=None,
        metadata={"platforms": ["instagram"]},
    )


@pytest.mark.parametrize("gorev", sorted(GOREV_SEMALARI))
def test_ornek_cikti_semaya_uyuyor(gorev):
    yanit = FakeProvider().complete(_istek(gorev))
    # Dogrulama basarisiz olursa is akisi panelde HATA olarak gorunurdu.
    GOREV_SEMALARI[gorev].model_validate(yanit.parsed)


def test_tanimsiz_gorev_turu_sessizce_gecmiyor():
    """Uydurma bir sozluk donmek, hatayi gecikvererek gizlerdi."""
    with pytest.raises(NotImplementedError):
        FakeProvider().complete(_istek("henuz_olmayan_gorev"))


def test_kodda_kullanilan_her_gorev_turu_burada_kayitli():
    """Yeni bir gorev turu eklenip sahte saglayici unutulmasin."""
    kok = pathlib.Path(__file__).resolve().parent.parent / "app"
    kullanilan = set()
    for dosya in kok.rglob("*.py"):
        kullanilan |= set(
            re.findall(r'task_type=["\']([a-z_]+)["\']', dosya.read_text(encoding="utf-8"))
        )

    eksik = sorted(kullanilan - set(GOREV_SEMALARI))
    assert eksik == [], (
        "Bu gorev turleri kodda kullaniliyor ama ornek veri saglayicisinda "
        "sinanmiyor: " + ", ".join(eksik)
    )


def test_ornek_veri_asla_kesin_bilgi_gibi_sunulmuyor():
    """Sahte veri 'fact' olarak isaretlenirse gercek sanilir."""
    trend = TrendResearchBatch.model_validate(
        FakeProvider().complete(_istek("trend_research")).parsed
    )
    for bulgu in trend.findings:
        assert bulgu.claim_type == "hypothesis"
        assert bulgu.uncertainties, "Belirsizlikler bos birakilmamali."
