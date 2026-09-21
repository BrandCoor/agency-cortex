"""Dort is akisinin calismasi.

Korunan kurallar:
- Veri yokken SAHTE SONUC uretilmez; "yapilacak is yoktu" denir
- Basarisizlik gizlenmez; nedeni kaydedilir ve kullaniciya gosterilir
- Butce dolduysa akis calismaz
- Uretilen her sey TASLAKTIR; hicbiri yayinlanmaz
- Kapali akis calistirilamaz
- Kapanmadan kalmis calistirma sonsuza kadar "calisiyor" gorunmez
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models.ai import AICostEvent
from app.models.brand import Brand
from app.models.content import ContentScript
from app.models.enums import (
    AutomationStatus,
    ContentStatus,
    Platform,
)
from app.models.otomasyon import AutomationRun
from app.models.research import TrendObservation
from app.models.social import SocialAccount
from app.services.is_akislari import (
    IsAkisiHatasi,
    wf01_gunluk_zeka,
    wf02_trend_arastirmasi,
    wf03_icerik_zekasi,
    wf04_haftalik_rapor,
)
from app.services.makine_kimligi import olustur
from app.services.otomasyon import (
    akis_durumlari,
    ayar_yaz,
    calistirma_baslat,
    takilan_calistirmalari_kapat,
)


@pytest.fixture
def musteri(db, make_workspace):
    ws = make_workspace(name="Akis Musterisi")
    db.flush()
    return ws


@pytest.fixture
def marka(db, musteri):
    b = Brand(workspace_id=musteri.id, name="Taha Usta", sector="Restoran")
    db.add(b)
    db.flush()
    return b


# --- WF-01: gunluk zeka ------------------------------------------------------

def test_wf01_bagli_hesap_yoksa_sahte_sonuc_uretmiyor(db, musteri):
    sonuc = wf01_gunluk_zeka(db, musteri)

    assert sonuc.yapilacak_is_yoktu is True
    assert sonuc.ozet["hesap"] == 0
    assert "bağlı sosyal medya hesabı yok" in sonuc.notlar[0]


def test_wf01_anahtarsiz_hesapta_acikca_hata_veriyor(db, musteri):
    """Erisim anahtari olmayan hesaptan veri cekilemez; sessizce gecilmez."""
    db.add(SocialAccount(
        workspace_id=musteri.id, platform=Platform.INSTAGRAM,
        external_id="123", username="tahausta", is_active=True,
    ))
    db.flush()

    with pytest.raises(IsAkisiHatasi) as hata:
        wf01_gunluk_zeka(db, musteri)
    assert "Hiçbir hesaptan veri çekilemedi" in str(hata.value)


# --- WF-02: trend arastirmasi ------------------------------------------------

def test_wf02_marka_yoksa_arastirma_yapmiyor(db, musteri):
    sonuc = wf02_trend_arastirmasi(db, musteri)

    assert sonuc.yapilacak_is_yoktu is True
    assert "Marka bilgisi girilmemiş" in sonuc.notlar[0]
    assert db.execute(select(TrendObservation)).scalars().all() == []


def test_wf02_butce_dolmussa_calismiyor(db, musteri, marka):
    musteri.ai_monthly_budget_usd = 1.0
    db.add(AICostEvent(
        workspace_id=musteri.id, provider="claude", occurred_at=datetime.now(UTC),
        amount_usd=Decimal("1.50"), description="onceki",
    ))
    db.flush()

    with pytest.raises(IsAkisiHatasi) as hata:
        wf02_trend_arastirmasi(db, musteri)
    assert "butcesi" in str(hata.value).lower() or "bütçe" in str(hata.value).lower()


def test_wf02_bulgular_kaydediliyor(db, musteri, marka, monkeypatch):
    from app.ai.base import AIResponse, AIStatus
    from app.ai.fake import FakeProvider

    bulgular = {
        "findings": [
            {
                "topic": "Ev yapimi baklava videolari",
                "summary": "Kisa tarif videolari yayiliyor.",
                "relevance_to_brand": "Tatli menusu one cikarilabilir.",
                "platform": "instagram",
                "claim_type": "fact",
                "confidence": "high",
                "source_urls": ["https://ornek.test/1"],
                "uncertainties": [],
            },
            {
                "topic": "Gece yarisi acilislari",
                "summary": "Gec saatte acik olan mekanlar konusuluyor.",
                "relevance_to_brand": "Belirsiz.",
                "platform": "bilinmeyen_platform",
                "claim_type": "hypothesis",
                "confidence": "high",
                "source_urls": [],
                "uncertainties": ["Ornek sayisi az"],
            },
        ],
        "research_note": "Yalnizca Instagram'a bakildi.",
    }

    def sahte_complete(self, request):
        import json
        metin = json.dumps(bulgular, ensure_ascii=False)
        return AIResponse(
            text=metin, parsed=bulgular, provider="fake", model="fake-model-v1",
            prompt_version=request.prompt_version, input_tokens=10, output_tokens=20,
            estimated_cost_usd=Decimal("0"), latency_ms=5, status=AIStatus.SUCCEEDED,
        )

    monkeypatch.setattr(FakeProvider, "complete", sahte_complete)

    sonuc = wf02_trend_arastirmasi(db, musteri)
    assert sonuc.ozet["bulgu"] == 2
    assert sonuc.ozet["yeni_kayit"] == 2

    kayitlar = db.execute(
        select(TrendObservation).order_by(TrendObservation.topic)
    ).scalars().all()
    assert len(kayitlar) == 2

    ev = next(k for k in kayitlar if k.topic.startswith("Ev"))
    assert ev.platform is Platform.INSTAGRAM
    assert ev.confidence == "high"

    # Hipotez, "high" dese bile DUSUK guvenle kaydedilir.
    gece = next(k for k in kayitlar if k.topic.startswith("Gece"))
    assert gece.confidence == "low"
    # Tanimadigimiz platform UYDURULMAZ.
    assert gece.platform is None


def test_wf02_ayni_gun_ayni_konu_tekrar_yazilmiyor(db, musteri, marka, monkeypatch):
    from app.ai.base import AIResponse, AIStatus
    from app.ai.fake import FakeProvider

    veri = {
        "findings": [{
            "topic": "Tek konu", "summary": "x", "relevance_to_brand": "y",
            "platform": "instagram", "claim_type": "fact", "confidence": "medium",
            "source_urls": [], "uncertainties": [],
        }],
        "research_note": "",
    }

    def sahte_complete(self, request):
        import json
        return AIResponse(
            text=json.dumps(veri), parsed=veri, provider="fake",
            model="fake-model-v1", prompt_version=request.prompt_version,
            input_tokens=1, output_tokens=1, estimated_cost_usd=Decimal("0"),
            latency_ms=1, status=AIStatus.SUCCEEDED,
        )

    monkeypatch.setattr(FakeProvider, "complete", sahte_complete)

    wf02_trend_arastirmasi(db, musteri)
    ikinci = wf02_trend_arastirmasi(db, musteri)

    assert ikinci.ozet["yeni_kayit"] == 0
    assert db.execute(
        select(func.count()).select_from(TrendObservation)
    ).scalar_one() == 1


# --- WF-03: icerik zekasi ----------------------------------------------------

def test_wf03_trend_yoksa_icerik_uretmiyor(db, musteri, marka):
    """Bulgusuz icerik uretmek tahmin olurdu."""
    sonuc = wf03_icerik_zekasi(db, musteri)

    assert sonuc.yapilacak_is_yoktu is True
    assert "trend bulgusu yok" in sonuc.notlar[0]
    assert db.execute(select(ContentScript)).scalars().all() == []


def test_wf03_uretilen_senaryolar_taslak_ve_onay_bekliyor(db, musteri, marka):
    db.add(TrendObservation(
        workspace_id=musteri.id, observed_at=datetime.now(UTC),
        platform=Platform.INSTAGRAM, topic="Kisa tarif videolari",
        summary="Yayiliyor", relevance_to_brand="Uygun",
        source_urls=[], confidence="high", uncertainties=[],
    ))
    db.flush()

    sonuc = wf03_icerik_zekasi(db, musteri)
    assert sonuc.ozet["senaryo"] >= 1

    senaryolar = db.execute(
        select(ContentScript).where(ContentScript.workspace_id == musteri.id)
    ).scalars().all()
    assert senaryolar
    for s in senaryolar:
        assert s.status is ContentStatus.DRAFT
        assert s.human_approval_required is True


# --- WF-04: haftalik rapor ---------------------------------------------------

def test_wf04_rapor_uretiliyor_ve_taslak(db, musteri):
    sonuc = wf04_haftalik_rapor(db, musteri)

    assert sonuc.ozet["durum"] == "draft"
    assert "-" in sonuc.ozet["donem"]


def test_wf04_ayni_hafta_ikinci_rapor_uretmiyor(db, musteri):
    ilk = wf04_haftalik_rapor(db, musteri)
    ikinci = wf04_haftalik_rapor(db, musteri)
    assert ilk.ozet["rapor_id"] == ikinci.ozet["rapor_id"]


# --- Takilan calistirmalar ---------------------------------------------------

def test_kapanmayan_calistirma_hata_olarak_kapatiliyor(db, musteri):
    ayar_yaz(db, musteri.id, "wf01_gunluk_zeka", acik=True)
    kayit = calistirma_baslat(
        db, workspace_id=musteri.id, workflow_key="wf01_gunluk_zeka",
        trigger="schedule",
    )
    # Surec cokmus gibi geriye al.
    kayit.started_at = datetime.now(UTC) - timedelta(hours=3)
    db.flush()

    kapatilan = takilan_calistirmalari_kapat(db)
    assert kapatilan == 1
    db.refresh(kayit)
    assert kayit.status is AutomationStatus.FAILED
    assert "Zaman asimi" in kayit.error_message


def test_takilan_calistirma_panelde_calisiyor_gorunmuyor(db, musteri):
    ayar_yaz(db, musteri.id, "wf02_trend", acik=True)
    kayit = calistirma_baslat(
        db, workspace_id=musteri.id, workflow_key="wf02_trend", trigger="schedule",
    )
    kayit.started_at = datetime.now(UTC) - timedelta(hours=5)
    db.flush()

    durum = next(d for d in akis_durumlari(db, musteri.id) if d["anahtar"] == "wf02_trend")
    assert durum["son_durum"] == "failed"
    assert durum["takildi"] is True


# --- Makine ucu: bastan sona ------------------------------------------------

def test_makine_ucu_akisi_calistirip_kaydediyor(client, db, musteri):
    ayar_yaz(db, musteri.id, "wf04_haftalik_rapor", acik=True)
    _, anahtar = olustur(
        db, ad="n8n", olusturan_user_id=None, workspace_ids=[musteri.id],
    )
    db.commit()

    yanit = client.post(
        f"/api/v1/makine/workspaces/{musteri.id}/akis/wf04_haftalik_rapor/calistir",
        headers={"X-API-Key": anahtar},
        json={"external_execution_id": "n8n-7"},
    )
    assert yanit.status_code == 200, yanit.text[:400]
    veri = yanit.json()
    assert veri["durum"] == "succeeded"

    kayit = db.get(AutomationRun, uuid.UUID(veri["run_id"]))
    db.refresh(kayit)
    assert kayit.status is AutomationStatus.SUCCEEDED
    assert kayit.external_execution_id == "n8n-7"
    assert kayit.finished_at is not None


def test_makine_ucu_basarisizligi_kaydediyor(client, db, musteri):
    """Hesap yokken WF-01 hata verir; kayit 'hata' olarak kapanir."""
    db.add(SocialAccount(
        workspace_id=musteri.id, platform=Platform.INSTAGRAM,
        external_id="yok", username="yok", is_active=True,
    ))
    ayar_yaz(db, musteri.id, "wf01_gunluk_zeka", acik=True)
    _, anahtar = olustur(
        db, ad="n8n", olusturan_user_id=None, workspace_ids=[musteri.id],
    )
    db.commit()

    yanit = client.post(
        f"/api/v1/makine/workspaces/{musteri.id}/akis/wf01_gunluk_zeka/calistir",
        headers={"X-API-Key": anahtar}, json={},
    )
    assert yanit.status_code == 422
    assert "veri çekilemedi" in yanit.json()["detail"]

    kayit = db.execute(
        select(AutomationRun).where(AutomationRun.workspace_id == musteri.id)
    ).scalar_one()
    db.refresh(kayit)
    assert kayit.status is AutomationStatus.FAILED
    assert kayit.error_message


def test_makine_ucu_kapali_akisi_calistirmiyor(client, db, musteri):
    _, anahtar = olustur(
        db, ad="n8n", olusturan_user_id=None, workspace_ids=[musteri.id],
    )
    db.commit()

    yanit = client.post(
        f"/api/v1/makine/workspaces/{musteri.id}/akis/wf04_haftalik_rapor/calistir",
        headers={"X-API-Key": anahtar}, json={},
    )
    assert yanit.status_code == 409
    assert db.execute(select(AutomationRun)).scalars().all() == []


def test_makine_ucu_kapsam_disindaki_musteride_calismiyor(
    client, db, musteri, make_workspace
):
    baskasi = make_workspace(name="Baskasi")
    ayar_yaz(db, baskasi.id, "wf04_haftalik_rapor", acik=True)
    _, anahtar = olustur(
        db, ad="n8n", olusturan_user_id=None, workspace_ids=[musteri.id],
    )
    db.commit()

    yanit = client.post(
        f"/api/v1/makine/workspaces/{baskasi.id}/akis/wf04_haftalik_rapor/calistir",
        headers={"X-API-Key": anahtar}, json={},
    )
    assert yanit.status_code == 404
    assert db.execute(
        select(AutomationRun).where(AutomationRun.workspace_id == baskasi.id)
    ).scalars().all() == []
