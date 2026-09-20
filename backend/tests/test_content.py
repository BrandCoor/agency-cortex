"""Icerik senaryosu uretimi testleri.

Korunan kurallar:
- Ayni fikir tum platformlara kopyalanmaz
- Yasakli ifadeler yakalanir
- Insan onayi HER ZAMAN gerekli
- Ham API verisi AI'ya gonderilmez
- Veri yoksa model veri varmis gibi davranmaz
- Ayni fikir iki kez uretilmez
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.ai.fake import FakeProvider
from app.models.brand import Brand, BrandGuideline
from app.models.content import ContentIdea, ContentScript
from app.models.enums import Platform
from app.services.content import build_context, check_forbidden, generate_scripts


@pytest.fixture
def marka(db, make_workspace):
    ws = make_workspace(name="Icerik Testi")
    b = Brand(workspace_id=ws.id, name="Test Markasi", sector="Kahve")
    db.add(b)
    db.flush()
    db.add(BrandGuideline(
        workspace_id=ws.id, brand_id=b.id,
        tone_of_voice="Samimi ve sade",
        target_audience="25-35 yas, sehirli",
        forbidden_phrases=["en iyisi", "mucize"],
        preferred_phrases=["ozenle"],
        kpi_targets={"reach": 10000},
    ))
    db.flush()
    return ws, b


# --- Baglam olusturma --------------------------------------------------------

def test_marka_hafizasi_isteme_girer(db, marka):
    ws, b = marka
    baglam = build_context(db, workspace_id=ws.id, brand=b)
    metin = baglam.to_prompt()

    assert "Test Markasi" in metin
    assert "Samimi ve sade" in metin
    assert "25-35 yas" in metin
    assert "en iyisi" in metin  # yasakli ifade modele bildirilmeli


def test_veri_yoksa_acikca_soylenir(db, marka):
    """Model veri varmis gibi davranmamali."""
    ws, b = marka
    baglam = build_context(db, workspace_id=ws.id, brand=b)
    assert baglam.data_note is not None
    assert "icerik yok" in baglam.data_note
    assert "dayandirma" in baglam.data_note


def test_baska_musterinin_markasi_baglama_girmez(db, marka, make_workspace):
    ws, b = marka
    diger = make_workspace(name="Diger")
    b2 = Brand(workspace_id=diger.id, name="GIZLI MARKA", sector="Gizli")
    db.add(b2)
    db.flush()
    db.add(BrandGuideline(
        workspace_id=diger.id, brand_id=b2.id,
        tone_of_voice="GIZLI MARKA DILI",
        forbidden_phrases=["gizli-yasak"],
    ))
    db.flush()

    metin = build_context(db, workspace_id=ws.id, brand=b).to_prompt()
    assert "GIZLI" not in metin
    assert "gizli-yasak" not in metin


# --- Yasakli ifadeler --------------------------------------------------------

def test_yasakli_ifade_bulunur():
    assert check_forbidden("Bu urun en iyisi!", ["en iyisi"]) == ["en iyisi"]


def test_buyuk_kucuk_harf_farki_onemli_degil():
    assert check_forbidden("EN IYISI budur", ["en iyisi"]) == ["en iyisi"]


def test_temiz_metinde_ihlal_yok():
    assert check_forbidden("Ozenle hazirlanmis kahve", ["en iyisi", "mucize"]) == []


# --- Senaryo uretimi ---------------------------------------------------------

def test_her_platform_icin_ayri_senaryo(db, marka):
    """Ayni fikir tum platformlara KOPYALANMAZ."""
    ws, b = marka
    sonuc = generate_scripts(
        db, workspace=ws, brand=b,
        platforms=[Platform.INSTAGRAM, Platform.TIKTOK, Platform.LINKEDIN],
        brief="Yeni kahve cesidi tanitimi",
        provider=FakeProvider(),
    )
    assert len(sonuc.scripts) == 3
    assert len({s.platform for s in sonuc.scripts}) == 3


def test_senaryolar_insan_onayi_bekler(db, marka):
    """Ilk surumde insan onayi olmadan yayin YOK."""
    ws, b = marka
    sonuc = generate_scripts(
        db, workspace=ws, brand=b, platforms=[Platform.INSTAGRAM],
        brief="Test", provider=FakeProvider(),
    )
    assert all(s.human_approval_required is True for s in sonuc.scripts)
    assert all(s.status.value == "draft" for s in sonuc.scripts)


def test_senaryo_tum_alanlari_doldurulur(db, marka):
    ws, b = marka
    sonuc = generate_scripts(
        db, workspace=ws, brand=b, platforms=[Platform.INSTAGRAM],
        brief="Test", provider=FakeProvider(),
    )
    s = sonuc.scripts[0]
    assert s.hook and s.spoken_script and s.caption and s.cta
    assert s.scene_plan and s.on_screen_text
    assert s.duration_seconds > 0
    assert s.claims_to_verify is not None


def test_ayni_fikir_iki_kez_uretilmez(db, marka):
    ws, b = marka
    s1 = generate_scripts(db, workspace=ws, brand=b, platforms=[Platform.INSTAGRAM],
                          brief="Test", provider=FakeProvider())
    db.flush()
    s2 = generate_scripts(db, workspace=ws, brand=b, platforms=[Platform.INSTAGRAM],
                          brief="Test", provider=FakeProvider())

    assert s2.was_duplicate is True
    assert s1.idea.id == s2.idea.id
    assert db.execute(
        select(func.count()).select_from(ContentIdea)
        .where(ContentIdea.workspace_id == ws.id)
    ).scalar_one() == 1


def test_senaryolar_dogru_musteriye_yazilir(db, marka, make_workspace):
    ws, b = marka
    diger = make_workspace(name="Ilgisiz")
    generate_scripts(db, workspace=ws, brand=b, platforms=[Platform.INSTAGRAM],
                     brief="Test", provider=FakeProvider())
    db.flush()

    assert db.execute(
        select(func.count()).select_from(ContentScript)
        .where(ContentScript.workspace_id == diger.id)
    ).scalar_one() == 0


def test_ai_gorevi_kaydedilir(db, marka):
    ws, b = marka
    sonuc = generate_scripts(db, workspace=ws, brand=b, platforms=[Platform.INSTAGRAM],
                             brief="Test", provider=FakeProvider())
    from app.models.ai import AITask

    gorev = db.get(AITask, sonuc.ai_task_id)
    assert gorev is not None
    assert gorev.workspace_id == ws.id
    assert gorev.input_summary["prompt_version"] == "content_script.v1"


def test_ham_veri_isteme_konulmaz(db, marka):
    """Claude'a ham sosyal medya API yaniti gonderilmez."""
    ws, b = marka
    metin = build_context(db, workspace_id=ws.id, brand=b).to_prompt()
    # Ham yanitlarda bulunan teknik anahtarlar isteme sizmamali.
    for anahtar in ("raw_payload", "access_token", "source_endpoint", "media_metrics_raw"):
        assert anahtar not in metin
