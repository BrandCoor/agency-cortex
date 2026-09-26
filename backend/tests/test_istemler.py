"""Duzenlenebilir istemler (prompt).

UC KURAL:
1. Koddaki varsayilan metin KAYBOLMAZ - "Varsayilana don" her zaman calisir
2. Metin degisince SURUM artar - hangi ciktinin hangi metinle uretildigi
   sonradan sorulabilsin diye
3. Veritabani okunamazsa sistem DURMAZ, koddaki metne duser
"""

from __future__ import annotations

import pytest

from app.services.istemler import (
    EN_AZ_UZUNLUK,
    YERLESIK_KODLAR,
    IstemHatasi,
    ekle,
    etkinlik_ayarla,
    getir,
    guncelle,
    listele,
    metin_al,
    sil,
    varsayilana_don,
    varsayilanlari_kur,
    yerlesikler,
)

UZUN_METIN = "Sen bir test istemisin. " * 5


@pytest.fixture
def kurulu(db):
    varsayilanlari_kur(db)
    return db


# --- Kurulum -----------------------------------------------------------------

def test_yerlesik_istemler_kuruluyor(kurulu):
    assert {i.kod for i in listele(kurulu)} >= YERLESIK_KODLAR


def test_kurulum_duzenlemeyi_geri_almiyor(kurulu):
    guncelle(kurulu, "trend_research", UZUN_METIN)
    varsayilanlari_kur(kurulu)
    assert getir(kurulu, "trend_research").metin == UZUN_METIN.strip()


def test_yerlesik_metinler_kodla_ayni_basliyor(kurulu):
    kod_metinleri = {y.kod: y.metin for y in yerlesikler()}
    for kayit in listele(kurulu):
        if kayit.yerlesik:
            assert kayit.metin == kod_metinleri[kayit.kod]


# --- Okuma -------------------------------------------------------------------

def test_metin_al_paneldeki_metni_donuyor(kurulu):
    guncelle(kurulu, "trend_research", UZUN_METIN)
    metin, surum = metin_al(kurulu, "trend_research")
    assert metin == UZUN_METIN.strip()
    assert surum == "trend_research.v2"


def test_kayit_yoksa_koddaki_varsayilana_dusuyor(db):
    """Tablo bos olsa bile is akislari calismaya devam etmeli."""
    metin, surum = metin_al(db, "trend_research")
    assert metin.strip()
    # v0 bilerek: bu cikti PANELDEKI metinle degil koddaki varsayilanla
    # uretilmistir; ikisi ayni etikete sahip olsaydi ayirt edilemezdi.
    assert surum == "trend_research.v0"


def test_bilinmeyen_kod_hata_veriyor(kurulu):
    with pytest.raises(IstemHatasi):
        metin_al(kurulu, "olmayan_istem")


# --- Surum -------------------------------------------------------------------

def test_metin_degisince_surum_artiyor(kurulu):
    once = getir(kurulu, "trend_research").surum
    guncelle(kurulu, "trend_research", UZUN_METIN)
    assert getir(kurulu, "trend_research").surum == once + 1


def test_ayni_metin_surumu_artirmiyor(kurulu):
    """Surum 'kac kez degisti' demektir, 'kac kez kaydete basildi' degil."""
    kayit = getir(kurulu, "trend_research")
    once = kayit.surum
    guncelle(kurulu, "trend_research", kayit.metin)
    assert getir(kurulu, "trend_research").surum == once


# --- Varsayilana donus -------------------------------------------------------

def test_varsayilana_donus_koddaki_metni_geri_getiriyor(kurulu):
    kod_metni = {y.kod: y.metin for y in yerlesikler()}["trend_research"]
    guncelle(kurulu, "trend_research", UZUN_METIN)
    varsayilana_don(kurulu, "trend_research")
    assert getir(kurulu, "trend_research").metin == kod_metni


def test_varsayilana_donus_de_surum_artiriyor(kurulu):
    guncelle(kurulu, "trend_research", UZUN_METIN)
    ara = getir(kurulu, "trend_research").surum
    varsayilana_don(kurulu, "trend_research")
    assert getir(kurulu, "trend_research").surum == ara + 1


def test_ozel_istem_varsayilana_donduruemez(kurulu):
    ekle(kurulu, kod="ozel_istem", ad="Özel", akis="", aciklama="",
         metin=UZUN_METIN)
    with pytest.raises(IstemHatasi, match="varsayılanı yok"):
        varsayilana_don(kurulu, "ozel_istem")


# --- Dogrulama ---------------------------------------------------------------

def test_cok_kisa_istem_reddediliyor(kurulu):
    """Uc kelimelik istem, ciktinin semaya uymamasina yol acar."""
    with pytest.raises(IstemHatasi, match="en az"):
        guncelle(kurulu, "trend_research", "kisa")


def test_bos_istem_reddediliyor(kurulu):
    with pytest.raises(IstemHatasi):
        guncelle(kurulu, "trend_research", "   ")


def test_sinir_uzunlugundaki_istem_kabul_ediliyor(kurulu):
    guncelle(kurulu, "trend_research", "a" * EN_AZ_UZUNLUK)
    assert getir(kurulu, "trend_research").metin == "a" * EN_AZ_UZUNLUK


def test_cok_uzun_istem_reddediliyor(kurulu):
    with pytest.raises(IstemHatasi, match="en fazla"):
        guncelle(kurulu, "trend_research", "a" * 20_001)


# --- Ekleme ve silme ---------------------------------------------------------

def test_ozel_istem_eklenip_silinebiliyor(kurulu):
    ekle(kurulu, kod="ozel_istem", ad="Özel", akis="WF-09",
         aciklama="deneme", metin=UZUN_METIN)
    assert getir(kurulu, "ozel_istem") is not None
    sil(kurulu, "ozel_istem")
    assert getir(kurulu, "ozel_istem") is None


def test_yerlesik_istem_silinemiyor(kurulu):
    with pytest.raises(IstemHatasi, match="silinemez"):
        sil(kurulu, "trend_research")


def test_bozuk_kod_reddediliyor(kurulu):
    with pytest.raises(IstemHatasi, match="Kod"):
        ekle(kurulu, kod="Büyük Harf!", ad="X", akis="", aciklama="",
             metin=UZUN_METIN)


def test_ayni_kod_iki_kez_eklenemiyor(kurulu):
    ekle(kurulu, kod="ozel_istem", ad="Özel", akis="", aciklama="",
         metin=UZUN_METIN)
    with pytest.raises(IstemHatasi, match="kullanılıyor"):
        ekle(kurulu, kod="ozel_istem", ad="Özel", akis="", aciklama="",
             metin=UZUN_METIN)


def test_yerlesik_istem_kapatilamiyor(kurulu):
    """Kapatilsaydi koddaki varsayilan kullanilmaya DEVAM ederdi."""
    with pytest.raises(IstemHatasi, match="kapatılamaz"):
        etkinlik_ayarla(kurulu, "trend_research", False)


def test_ozel_istem_kapatilabiliyor(kurulu):
    ekle(kurulu, kod="ozel_istem", ad="Özel", akis="", aciklama="",
         metin=UZUN_METIN)
    etkinlik_ayarla(kurulu, "ozel_istem", False)
    assert getir(kurulu, "ozel_istem").etkin is False
