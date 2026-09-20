"""Anomali tespiti testleri."""

from __future__ import annotations

from app.services.anomalies import MIN_OBSERVATIONS, Severity, detect, detect_many

NORMAL = [100, 105, 98, 102, 99, 101, 103]


def test_normal_deger_anomali_sayilmaz():
    assert detect("reach", NORMAL, 104) is None


def test_ani_dusus_yakalanir():
    a = detect("reach", NORMAL, 20)
    assert a is not None
    assert a.direction == "drop"
    assert "altinda" in a.explanation


def test_ani_artis_yakalanir():
    a = detect("reach", NORMAL, 900)
    assert a is not None
    assert a.direction == "spike"


def test_yetersiz_gecmisle_tespit_yapilmaz():
    """Az veriyle 'anormal' demek guvenilir degil."""
    assert detect("reach", [100, 102], 5000) is None
    assert len([100, 102]) < MIN_OBSERVATIONS


def test_deger_bilinmiyorsa_tespit_yapilmaz():
    """Veri yoksa 'anormal degil' denmez, 'soyleyemem' denir."""
    assert detect("reach", NORMAL, None) is None


def test_tek_viral_icerik_sonraki_gunleri_anormal_gostermez():
    """Ortalama kullanilsaydi viral gunden sonraki normal gunler
    'anormal dusuk' gorunurdu. Medyan bunu engeller."""
    gecmis = [100, 102, 98, 50000, 101, 99, 103]
    assert detect("reach", gecmis, 100) is None


def test_sabit_gecmiste_kucuk_degisim_anomali_degil():
    assert detect("reach", [100] * 7, 120) is None


def test_sabit_gecmiste_buyuk_degisim_anomali():
    a = detect("reach", [100] * 7, 500)
    assert a is not None


def test_onem_seviyesi_atanir():
    a = detect("reach", NORMAL, 20)
    assert a.severity in (Severity.WARNING, Severity.CRITICAL)


def test_coklu_tarama_onem_sirasina_gore_doner():
    sonuc = detect_many({
        "az_sapan": (NORMAL, 130),
        "cok_sapan": (NORMAL, 5),
    })
    if len(sonuc) > 1:
        assert sonuc[0].deviation_score >= sonuc[1].deviation_score
