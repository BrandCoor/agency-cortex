"""KPI hesap motoru testleri.

Bu testlerin cogu tek bir kurali korur: EKSIK VERI SIFIR DEGILDIR.
"""

from __future__ import annotations

from decimal import Decimal

from app.services.kpi import (
    DataQuality,
    Direction,
    MetricSet,
    RankedItem,
    average,
    compare,
    engagement_rate,
    engagement_total,
    median,
    rank,
    safe_divide,
    to_float,
    total,
)

# --- Sifira bolme ve eksik veri ---------------------------------------------

def test_sifira_bolme_hata_firlatmaz_ve_sifir_dondurmez():
    """Sifira bolme None dondurmeli.

    0 donseydi rapor 'etkilesim orani %0' derdi; oysa oran HESAPLANAMIYOR.
    Ikisi farkli seylerdir.
    """
    assert safe_divide(10, 0) is None


def test_eksik_deger_none_doner():
    assert safe_divide(None, 100) is None
    assert safe_divide(100, None) is None


def test_normal_bolme_dogru_calisir():
    assert safe_divide(50, 200) == 0.25


def test_erisim_sifirken_etkilesim_orani_hesaplanmaz():
    m = MetricSet(values={"likes": 10, "comments": 5, "reach": 0})
    assert engagement_rate(m) is None


def test_erisim_bilinmiyorken_oran_hesaplanmaz():
    m = MetricSet(values={"likes": 10, "comments": 5})
    assert engagement_rate(m) is None


def test_hicbir_etkilesim_metrigi_yoksa_none_doner():
    m = MetricSet(values={"reach": 1000})
    assert engagement_total(m) is None


def test_kismi_metrikler_toplanir_ve_eksikler_kaydedilir():
    m = MetricSet(values={"likes": 10, "comments": 5})
    assert engagement_total(m) == 15
    assert "saves" in m.missing
    assert "shares" in m.missing


def test_sifir_etkilesim_gercek_sifirdir():
    """Veri VAR ve degeri 0 ise bu gercek bir sifirdir, None degil."""
    m = MetricSet(values={"likes": 0, "comments": 0, "saves": 0, "shares": 0, "reach": 500})
    assert engagement_total(m) == 0
    assert engagement_rate(m) == 0.0


# --- Karsilastirma -----------------------------------------------------------

def test_artis_dogru_hesaplanir():
    k = compare(120, 100)
    assert k.direction is Direction.UP
    assert k.change_absolute == 20
    assert abs(k.change_percent - 0.2) < 1e-9


def test_azalis_dogru_hesaplanir():
    k = compare(80, 100)
    assert k.direction is Direction.DOWN
    assert abs(k.change_percent + 0.2) < 1e-9


def test_kucuk_degisim_sabit_sayilir():
    """Gurultuyu trend gibi sunmamali."""
    assert compare(100.2, 100).direction is Direction.FLAT


def test_onceki_donem_sifirken_yuzde_hesaplanmaz():
    """'Sonsuz artis' veya '%100 artis' yazmak yaniltici olur."""
    k = compare(50, 0)
    assert k.change_percent is None
    assert k.direction is Direction.UP
    assert k.change_absolute == 50


def test_veri_yoksa_karsilastirma_guvenilir_degil():
    k = compare(None, 100)
    assert k.direction is Direction.UNKNOWN
    assert k.is_reliable is False


# --- Toplu istatistikler -----------------------------------------------------

def test_ortalama_eksikleri_atlar():
    assert average([10, None, 20]) == 15


def test_hepsi_eksikse_ortalama_none():
    assert average([None, None]) is None
    assert median([None]) is None
    assert total([None, None]) is None


def test_medyan_asiri_degerden_etkilenmez():
    """Tek viral icerik ortalamayi bozar, medyani bozmaz."""
    veriler = [100, 105, 98, 102, 100000]
    assert median(veriler) == 102
    assert average(veriler) > 20000


def test_decimal_donusumu():
    assert to_float(Decimal("12.50")) == 12.5
    assert to_float(None) is None


# --- Siralama ----------------------------------------------------------------

def test_en_iyiler_dogru_siralanir():
    items = [RankedItem("a", 10), RankedItem("b", 30), RankedItem("c", 20)]
    assert [r.key for r in rank(items, top=2)] == ["b", "c"]


def test_en_zayiflar_dogru_siralanir():
    items = [RankedItem("a", 10), RankedItem("b", 30), RankedItem("c", 20)]
    assert [r.key for r in rank(items, top=2, ascending=True)] == ["a", "c"]


# --- Veri kalitesi -----------------------------------------------------------

def test_kapsam_hesaplanir():
    k = DataQuality(expected_items=10, items_with_data=8)
    assert k.coverage == 0.8
    assert k.is_sufficient is True


def test_dusuk_kapsam_yetersiz_sayilir():
    k = DataQuality(expected_items=10, items_with_data=3)
    assert k.is_sufficient is False


def test_icerik_yoksa_kapsam_hesaplanmaz():
    """Sifira bolme burada da olmamali."""
    k = DataQuality(expected_items=0, items_with_data=0)
    assert k.coverage is None
    assert k.is_sufficient is False
