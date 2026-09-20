"""AI saglayici testleri.

Ana kural: bir saglayici yapamadigi isi 'yapiyormus gibi' gostermez.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.ai.base import AIRequest, ProviderNotConfigured, ProviderNotImplemented
from app.ai.claude import DEFAULT_MODEL, ClaudeProvider, GeminiProviderStub, ManusProviderStub
from app.ai.fake import FakeProvider
from app.ai.pricing import MODEL_PRICING, UnknownModelPricing, estimate_cost
from app.ai.registry import TASK_ROUTING, get_provider, provider_for_task, provider_status
from app.ai.schemas import ContentScriptBatch, StrategicCommentary


def istek(task_type: str = "content_script", **kw) -> AIRequest:
    return AIRequest(
        task_type=task_type,
        prompt_version="v1",
        system="test sistem istemi",
        user_content="test kullanici icerigi",
        **kw,
    )


# --- Fiyatlandirma -----------------------------------------------------------

def test_opus_5_fiyati_dogru():
    """Fiyatlar resmi listeden alindi; yanlissa butce kontrolu bozulur."""
    f = MODEL_PRICING["claude-opus-5"]
    assert f.input_per_million == Decimal("5.00")
    assert f.output_per_million == Decimal("25.00")


def test_maliyet_hesabi_dogru():
    # 1M girdi + 1M cikti = 5 + 25 = 30 USD
    m = estimate_cost("claude-opus-5", input_tokens=1_000_000, output_tokens=1_000_000)
    assert m == Decimal("30.00")


def test_kucuk_cagri_maliyeti():
    m = estimate_cost("claude-opus-5", input_tokens=10_000, output_tokens=2_000)
    # 10k*5/1M + 2k*25/1M = 0.05 + 0.05 = 0.10
    assert m == Decimal("0.10")


def test_token_bilinmiyorsa_maliyet_none():
    """Bilinmeyen maliyeti SIFIR saymak butce kontrolunu sessizce bozardi."""
    assert estimate_cost("claude-opus-5", input_tokens=None, output_tokens=5) is None


def test_bilinmeyen_model_maliyeti_tahmin_edilmez():
    with pytest.raises(UnknownModelPricing):
        estimate_cost("bilinmeyen-model", input_tokens=100, output_tokens=100)


def test_sahte_model_bedava():
    assert estimate_cost("fake-model-v1", input_tokens=None, output_tokens=None) == Decimal("0")


# --- Model kimligi -----------------------------------------------------------

def test_varsayilan_model_opus_5():
    assert DEFAULT_MODEL == "claude-opus-5"


def test_model_kimliginde_tarih_son_eki_yok():
    """Tarih son ekli kimlikler gecersizdir."""
    assert "-2026" not in DEFAULT_MODEL
    for ad in MODEL_PRICING:
        assert not ad[-8:].isdigit(), f"{ad} tarih son eki iceriyor"


# --- Saglayici durumu --------------------------------------------------------

def test_claude_anahtarsizken_hazir_gorunmez():
    p = ClaudeProvider()
    assert p.is_configured is False
    assert "ANTHROPIC_API_KEY" in p.missing_config
    assert p.health_check()[0] is False


def test_claude_anahtarsizken_acik_hata_verir():
    with pytest.raises(ProviderNotConfigured):
        ClaudeProvider().complete(istek())


def test_manus_tamamlanmadigini_soyler():
    """Resmi dokumana erisilemedigi icin tahminle yazilmadi."""
    p = ManusProviderStub()
    assert p.health_check()[0] is False
    with pytest.raises(ProviderNotImplemented):
        p.complete(istek("competitor_research"))


def test_gemini_ilk_surumde_kapsam_disi():
    p = GeminiProviderStub()
    assert p.health_check()[0] is False
    with pytest.raises(ProviderNotImplemented):
        p.complete(istek("bulk_classification"))


def test_saglayici_durumu_durustce_raporlanir():
    satirlar = {r["provider"]: r for r in provider_status()}
    assert satirlar["manus"]["available"] is False
    assert satirlar["gemini"]["available"] is False


# --- Gorev yonlendirme -------------------------------------------------------

def test_gorevler_dogru_saglayiciya_gider():
    """Claude ve Manus birbirinin yerine kullanilmaz."""
    assert TASK_ROUTING["content_script"] == "claude"
    assert TASK_ROUTING["strategic_commentary"] == "claude"
    assert TASK_ROUTING["competitor_research"] == "manus"
    assert TASK_ROUTING["trend_research"] == "manus"


def test_bilinmeyen_gorev_reddedilir():
    with pytest.raises(ValueError):
        provider_for_task("olmayan_gorev", mode="live")


def test_gelistirme_modunda_sahte_saglayici_gelir():
    assert isinstance(get_provider("claude", mode="fake"), FakeProvider)


def test_canli_modda_gercek_saglayici_gelir():
    assert isinstance(get_provider("claude", mode="live"), ClaudeProvider)


# --- Sahte saglayici ---------------------------------------------------------

def test_sahte_cikti_semaya_uyar():
    yanit = FakeProvider().complete(
        istek(metadata={"platforms": ["instagram", "tiktok"]})
    )
    dogrulanmis = ContentScriptBatch.model_validate(yanit.parsed)
    assert len(dogrulanmis.scripts) == 2
    assert {s.platform for s in dogrulanmis.scripts} == {"instagram", "tiktok"}


def test_sahte_senaryo_tum_alanlari_doldurur():
    yanit = FakeProvider().complete(istek())
    s = ContentScriptBatch.model_validate(yanit.parsed).scripts[0]
    assert s.hook and s.cta and s.caption
    assert s.scene_plan and s.spoken_script
    assert s.reason_for_recommendation


def test_sahte_cikti_sahte_oldugunu_soyler():
    """Sahte veri gercek gibi sunulmamali."""
    yanit = FakeProvider().complete(istek())
    s = ContentScriptBatch.model_validate(yanit.parsed).scripts[0]
    assert any("sahte" in c.lower() for c in s.claims_to_verify)


def test_sahte_yorum_her_zaman_hipotezdir():
    yanit = FakeProvider().complete(istek("strategic_commentary"))
    y = StrategicCommentary.model_validate(yanit.parsed)
    assert all(i.claim_type == "hypothesis" for i in y.insights)
    assert y.confidence == "low"


def test_sahte_cikti_tekrarlanabilir():
    a = FakeProvider().complete(istek(metadata={"seed": "x"}))
    b = FakeProvider().complete(istek(metadata={"seed": "x"}))
    assert a.text == b.text
    assert a.output_hash == b.output_hash


def test_farkli_tohum_farkli_cikti():
    a = FakeProvider().complete(istek(metadata={"seed": "x"}))
    b = FakeProvider().complete(istek(metadata={"seed": "y"}))
    assert a.output_hash != b.output_hash


def test_cikti_parmak_izi_uretilir():
    yanit = FakeProvider().complete(istek())
    assert len(yanit.output_hash) == 64


# --- Sema ---------------------------------------------------------------------

def test_sema_fazladan_alan_kabul_etmez():
    """Model semada olmayan alan ekleyememeli."""
    sema = ContentScriptBatch.model_json_schema()
    assert sema.get("additionalProperties") is False


def test_senaryo_semasinda_zorunlu_alanlar_var():
    from app.ai.schemas import ContentScript

    zorunlu = set(ContentScript.model_json_schema()["required"])
    for alan in ("hook", "cta", "claims_to_verify", "reason_for_recommendation",
                 "brand_risks", "scene_plan", "target_metric"):
        assert alan in zorunlu, f"{alan} zorunlu degil"
