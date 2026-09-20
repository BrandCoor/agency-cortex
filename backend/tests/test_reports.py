"""Rapor uretimi testleri.

Korunan kurallar:
- Ayni donemin raporu iki kez uretilmez
- Eksik veri gizlenmez, raporda acikca yazar
- Kanit yetersizse yorum "hipotez" olarak isaretlenir
- Bir musterinin raporu digerinin verisini icermez
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models.enums import MediaType, Platform, ReportPeriod
from app.models.reporting import Report, ReportSection
from app.models.social import MediaMetricsNormalized, PlatformMedia, SocialAccount
from app.services.reports import build_window, generate_report

BUGUN = date(2026, 9, 20)


@pytest.fixture
def hesap(db, make_workspace):
    ws = make_workspace(name="Rapor Testi")
    acc = SocialAccount(
        workspace_id=ws.id, platform=Platform.INSTAGRAM,
        external_id="ig_rapor", username="marka", is_professional=True,
    )
    db.add(acc)
    db.flush()
    return acc


def icerik_ekle(db, hesap, *, gun_once: int, metrikler: dict,
                tur: MediaType = MediaType.REEL, baslik: str = "Test icerigi"):
    """Belirli bir gun yayinlanmis, verilen metriklere sahip icerik olusturur."""
    yayin = datetime.combine(BUGUN - timedelta(days=gun_once), datetime.min.time(), UTC)
    m = PlatformMedia(
        workspace_id=hesap.workspace_id, social_account_id=hesap.id,
        platform=Platform.INSTAGRAM, external_id=f"m_{uuid.uuid4().hex[:8]}",
        media_type=tur, caption=baslik, published_at=yayin,
    )
    db.add(m)
    db.flush()
    for ad, deger in metrikler.items():
        db.add(MediaMetricsNormalized(
            workspace_id=hesap.workspace_id, media_id=m.id, platform=Platform.INSTAGRAM,
            metric_name=ad, metric_value=deger, measurement_period="lifetime",
            measured_at=yayin, fetched_at=yayin,
        ))
    db.flush()
    return m


def bolumler(db, rapor) -> dict[str, ReportSection]:
    satirlar = db.execute(
        select(ReportSection).where(ReportSection.report_id == rapor.id)
        .order_by(ReportSection.order_index)
    ).scalars().all()
    return {s.heading: s for s in satirlar}


# --- Donem hesabi ------------------------------------------------------------

def test_gunluk_rapor_dunu_kapsar():
    """Bugun henuz bitmedigi icin yarim veri raporlanmaz."""
    p = build_window(ReportPeriod.DAILY, BUGUN)
    assert p.start == p.end == BUGUN - timedelta(days=1)
    assert p.previous_start == BUGUN - timedelta(days=2)


def test_haftalik_rapor_yedi_gun_kapsar():
    p = build_window(ReportPeriod.WEEKLY, BUGUN)
    assert (p.end - p.start).days == 6
    assert (p.previous_end - p.previous_start).days == 6
    assert p.previous_end < p.start


# --- Rapor uretimi -----------------------------------------------------------

def test_gunluk_rapor_uretilir(db, hesap):
    icerik_ekle(db, hesap, gun_once=1,
                metrikler={"likes": 100, "comments": 20, "saves": 10, "shares": 5, "reach": 2000})

    r = generate_report(db, workspace_id=hesap.workspace_id,
                        period=ReportPeriod.DAILY, reference=BUGUN)

    assert r.period is ReportPeriod.DAILY
    b = bolumler(db, r)
    assert "Donem ozeti" in b
    assert "Veri kalitesi ve eksikler" in b
    assert b["Donem ozeti"].data["icerik_sayisi"] == 1
    assert b["Donem ozeti"].data["toplam_etkilesim"] == 135


def test_ayni_donem_iki_kez_uretilmez(db, hesap):
    """Zamanlayici ayni isi tekrar tetiklerse ikinci rapor olusmamali."""
    icerik_ekle(db, hesap, gun_once=1, metrikler={"likes": 10, "reach": 100})

    r1 = generate_report(db, workspace_id=hesap.workspace_id,
                         period=ReportPeriod.DAILY, reference=BUGUN)
    db.flush()
    r2 = generate_report(db, workspace_id=hesap.workspace_id,
                         period=ReportPeriod.DAILY, reference=BUGUN)

    assert r1.id == r2.id
    sayi = db.execute(
        select(func.count()).select_from(Report)
        .where(Report.workspace_id == hesap.workspace_id)
    ).scalar_one()
    assert sayi == 1


def test_force_ile_rapor_yenilenir(db, hesap):
    icerik_ekle(db, hesap, gun_once=1, metrikler={"likes": 10, "reach": 100})
    r1 = generate_report(db, workspace_id=hesap.workspace_id,
                         period=ReportPeriod.DAILY, reference=BUGUN)
    db.flush()
    bolum_sayisi_1 = db.execute(
        select(func.count()).select_from(ReportSection)
        .where(ReportSection.report_id == r1.id)
    ).scalar_one()

    r2 = generate_report(db, workspace_id=hesap.workspace_id, period=ReportPeriod.DAILY,
                         reference=BUGUN, force=True)
    db.flush()
    bolum_sayisi_2 = db.execute(
        select(func.count()).select_from(ReportSection)
        .where(ReportSection.report_id == r2.id)
    ).scalar_one()

    assert r1.id == r2.id
    # Bolumler cogalmamali - eskiler silinip yenileri yazilmali.
    assert bolum_sayisi_1 == bolum_sayisi_2


# --- Eksik veri durusu -------------------------------------------------------

def test_icerik_yoksa_rapor_yine_uretilir_ve_durumu_soyler(db, hesap):
    """Veri yoksa rapor 'her sey sifir' demez; 'icerik yok' der."""
    r = generate_report(db, workspace_id=hesap.workspace_id,
                        period=ReportPeriod.DAILY, reference=BUGUN)
    b = bolumler(db, r)
    assert "icerik bulunamadi" in b["Veri kalitesi ve eksikler"].body
    assert r.data_quality_notes


def test_olcum_verisi_yoksa_acikca_bildirilir(db, hesap):
    """Icerik var ama metrik yok - bu bir baglanti sorunudur, sifir degil."""
    icerik_ekle(db, hesap, gun_once=1, metrikler={})

    r = generate_report(db, workspace_id=hesap.workspace_id,
                        period=ReportPeriod.DAILY, reference=BUGUN)
    b = bolumler(db, r)
    assert "olcum verisi alinamadi" in b["Veri kalitesi ve eksikler"].body
    assert b["En iyi ve en zayif icerikler"].data["en_iyi"] == []


def test_eksik_metrikler_raporda_listelenir(db, hesap):
    icerik_ekle(db, hesap, gun_once=1, metrikler={"likes": 50, "reach": 500})

    r = generate_report(db, workspace_id=hesap.workspace_id,
                        period=ReportPeriod.DAILY, reference=BUGUN)
    b = bolumler(db, r)
    eksikler = b["Veri kalitesi ve eksikler"].data["eksik_metrikler"]
    assert "saves" in eksikler and "shares" in eksikler


def test_erisim_sifirken_rapor_cokmez(db, hesap):
    """Sifira bolme rapor uretimini durdurmamali."""
    icerik_ekle(db, hesap, gun_once=1,
                metrikler={"likes": 5, "comments": 0, "saves": 0, "shares": 0, "reach": 0})
    r = generate_report(db, workspace_id=hesap.workspace_id,
                        period=ReportPeriod.DAILY, reference=BUGUN)
    assert r is not None


# --- Kanit seviyesi ----------------------------------------------------------

def test_az_veriyle_yorum_hipotez_olarak_isaretlenir(db, hesap):
    """Yeterli kanit yoksa 'kesin neden' yazilmamali."""
    icerik_ekle(db, hesap, gun_once=1, metrikler={"likes": 100, "reach": 1000})
    icerik_ekle(db, hesap, gun_once=1, metrikler={"likes": 10, "reach": 1000})

    r = generate_report(db, workspace_id=hesap.workspace_id,
                        period=ReportPeriod.DAILY, reference=BUGUN)
    b = bolumler(db, r)
    assert b["En iyi ve en zayif icerikler"].claim_type == "hypothesis"
    assert b["Bu donemin onerileri"].claim_type == "hypothesis"


def test_yeterli_veriyle_siralama_olgu_sayilir(db, hesap):
    tam = {"likes": 100, "comments": 10, "saves": 5, "shares": 2, "reach": 1000}
    for i in range(6):
        icerik_ekle(db, hesap, gun_once=1, metrikler={**tam, "likes": 100 + i * 10})

    r = generate_report(db, workspace_id=hesap.workspace_id,
                        period=ReportPeriod.DAILY, reference=BUGUN)
    b = bolumler(db, r)
    assert b["En iyi ve en zayif icerikler"].claim_type == "fact"


def test_dusuk_kapsamda_varsayim_eklenir(db, hesap):
    icerik_ekle(db, hesap, gun_once=1, metrikler={"likes": 10, "reach": 100})
    for _ in range(4):
        icerik_ekle(db, hesap, gun_once=1, metrikler={})

    r = generate_report(db, workspace_id=hesap.workspace_id,
                        period=ReportPeriod.DAILY, reference=BUGUN)
    assert any("nedensel yorum yapilmamistir" in v for v in r.assumptions)


# --- Karsilastirma -----------------------------------------------------------

def test_onceki_donemle_karsilastirma_yapilir(db, hesap):
    icerik_ekle(db, hesap, gun_once=1, metrikler={"likes": 200, "reach": 2000})
    icerik_ekle(db, hesap, gun_once=2, metrikler={"likes": 100, "reach": 1000})

    r = generate_report(db, workspace_id=hesap.workspace_id,
                        period=ReportPeriod.DAILY, reference=BUGUN)
    b = bolumler(db, r)
    degisim = b["Donem ozeti"].data["etkilesim_degisimi"]
    assert degisim["guvenilir"] is True
    assert degisim["yon"] == "up"
    assert abs(degisim["yuzde"] - 1.0) < 1e-9


def test_onceki_donem_verisi_yoksa_karsilastirma_guvenilir_degil(db, hesap):
    icerik_ekle(db, hesap, gun_once=1, metrikler={"likes": 200, "reach": 2000})

    r = generate_report(db, workspace_id=hesap.workspace_id,
                        period=ReportPeriod.DAILY, reference=BUGUN)
    b = bolumler(db, r)
    assert b["Donem ozeti"].data["etkilesim_degisimi"]["guvenilir"] is False


# --- Musteri izolasyonu ------------------------------------------------------

def test_rapor_baska_musterinin_verisini_icermez(db, hesap, make_workspace):
    """En kritik kural: raporlar birbirine karismamali."""
    diger_ws = make_workspace(name="Baska Musteri")
    diger_hesap = SocialAccount(
        workspace_id=diger_ws.id, platform=Platform.INSTAGRAM,
        external_id="ig_diger", is_professional=True,
    )
    db.add(diger_hesap)
    db.flush()

    icerik_ekle(db, hesap, gun_once=1, metrikler={"likes": 100, "reach": 1000})
    for _ in range(5):
        icerik_ekle(db, diger_hesap, gun_once=1, metrikler={"likes": 9999, "reach": 99999})

    r = generate_report(db, workspace_id=hesap.workspace_id,
                        period=ReportPeriod.DAILY, reference=BUGUN)
    b = bolumler(db, r)

    assert b["Donem ozeti"].data["icerik_sayisi"] == 1
    assert b["Donem ozeti"].data["toplam_etkilesim"] == 100
    assert b["Donem ozeti"].data["toplam_erisim"] == 1000


def test_rapor_bolumleri_dogru_calisma_alanina_yazilir(db, hesap):
    icerik_ekle(db, hesap, gun_once=1, metrikler={"likes": 10, "reach": 100})
    r = generate_report(db, workspace_id=hesap.workspace_id,
                        period=ReportPeriod.DAILY, reference=BUGUN)
    db.flush()
    for s in db.execute(
        select(ReportSection).where(ReportSection.report_id == r.id)
    ).scalars():
        assert s.workspace_id == hesap.workspace_id


# --- Haftalik rapor ----------------------------------------------------------

def test_haftalik_rapor_format_analizi_yapar(db, hesap):
    for i in range(3):
        icerik_ekle(db, hesap, gun_once=i + 1, tur=MediaType.REEL,
                    metrikler={"likes": 500, "comments": 50, "saves": 20, "shares": 10, "reach": 5000})
    for i in range(3):
        icerik_ekle(db, hesap, gun_once=i + 1, tur=MediaType.IMAGE,
                    metrikler={"likes": 50, "comments": 5, "saves": 2, "shares": 1, "reach": 1000})

    r = generate_report(db, workspace_id=hesap.workspace_id,
                        period=ReportPeriod.WEEKLY, reference=BUGUN)
    b = bolumler(db, r)
    formatlar = b["Format analizi"].data["formatlar"]
    assert "reel" in formatlar and "image" in formatlar
    assert formatlar["reel"]["ortalama_etkilesim"] > formatlar["image"]["ortalama_etkilesim"]


def test_oneriler_en_fazla_uc_tane(db, hesap):
    """Uzun oneri listeleri uygulanmaz."""
    icerik_ekle(db, hesap, gun_once=1, metrikler={"likes": 10})
    icerik_ekle(db, hesap, gun_once=1, metrikler={})

    r = generate_report(db, workspace_id=hesap.workspace_id,
                        period=ReportPeriod.DAILY, reference=BUGUN)
    b = bolumler(db, r)
    assert len(b["Bu donemin onerileri"].data["oneriler"]) <= 3
