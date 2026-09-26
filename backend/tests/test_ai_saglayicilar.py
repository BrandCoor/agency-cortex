"""Yapay zeka saglayicilari ve gorev dagilimi.

EN ONEMLI KURAL: SINANMAMIS SAGLAYICI GOREVE ATANAMAZ.
"Etkin" isaretlemek tek basina yetmez. Bu kural olmasaydi panelde
"acik" gorunen bir saglayici ilk gercek iste anlasilmaz bir hatayla
cokerdi - ve kullanici ayarin dogru oldugunu sanirdi.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.security import decrypt_secret
from app.models.ai_saglayici import SaglayiciTuru
from app.models.ops import SystemSetting
from app.services.ai_saglayicilar import (
    GOREVLER,
    SaglayiciHatasi,
    atama_yap,
    atamalar,
    etkinlik_ayarla,
    getir,
    kullanilabilir_saglayicilar,
    listele,
    ozel_ekle,
    sil,
    varsayilanlari_kur,
)

SIFRE = "GucluSifre123!"


@pytest.fixture
def kurulu(db):
    varsayilanlari_kur(db)
    return db


# --- Kurulum -----------------------------------------------------------------

def test_yerlesik_saglayicilar_kuruluyor(kurulu):
    anahtarlar = {s.anahtar for s in listele(kurulu)}
    assert {"claude", "gemini", "manus"} <= anahtarlar


def test_yerlesikler_kapali_baslar(kurulu):
    """Anahtar girilmeden hicbir saglayici acik olmamali."""
    assert all(not s.etkin for s in listele(kurulu))


def test_kurulum_tekrar_calistirilabilir(kurulu):
    """Ikinci kurulum kullanicinin secimlerini GERI ALMAMALI."""
    etkinlik_ayarla(kurulu, "claude", True)
    varsayilanlari_kur(kurulu)
    assert getir(kurulu, "claude").etkin is True
    assert len([s for s in listele(kurulu) if s.anahtar == "claude"]) == 1


def test_her_gorev_icin_varsayilan_atama_var(kurulu):
    mevcut = atamalar(kurulu)
    for gorev in GOREVLER:
        assert mevcut[gorev.kod] == gorev.varsayilan


# --- Sinanmamis saglayici --------------------------------------------------

def test_sinanmamis_saglayici_goreve_atanamaz(kurulu):
    etkinlik_ayarla(kurulu, "claude", True)
    with pytest.raises(SaglayiciHatasi, match="Bağlantıyı sına"):
        atama_yap(kurulu, "content_script", "claude")


def test_sinamasi_basarisiz_saglayici_atanamaz(kurulu):
    saglayici = getir(kurulu, "claude")
    saglayici.etkin = True
    saglayici.son_sinama_basarili = False
    kurulu.flush()
    with pytest.raises(SaglayiciHatasi):
        atama_yap(kurulu, "content_script", "claude")


def test_kapali_ama_sinanmis_saglayici_atanamaz(kurulu):
    """Sinama basarili olsa bile KAPALI saglayici is yapmamali."""
    saglayici = getir(kurulu, "claude")
    saglayici.etkin = False
    saglayici.son_sinama_basarili = True
    kurulu.flush()
    with pytest.raises(SaglayiciHatasi):
        atama_yap(kurulu, "content_script", "claude")


def test_acik_ve_sinanmis_saglayici_atanir(kurulu):
    saglayici = getir(kurulu, "claude")
    saglayici.etkin = True
    saglayici.son_sinama_basarili = True
    kurulu.flush()
    atama_yap(kurulu, "content_script", "claude")
    assert atamalar(kurulu)["content_script"] == "claude"


def test_kullanilabilir_listesi_ikisini_de_arar(kurulu):
    a = getir(kurulu, "claude")
    a.etkin, a.son_sinama_basarili = True, True
    b = getir(kurulu, "gemini")
    b.etkin, b.son_sinama_basarili = True, False
    c = getir(kurulu, "manus")
    c.etkin, c.son_sinama_basarili = False, True
    kurulu.flush()
    assert [s.anahtar for s in kullanilabilir_saglayicilar(kurulu)] == ["claude"]


def test_bilinmeyen_gorev_reddediliyor(kurulu):
    with pytest.raises(SaglayiciHatasi, match="görev"):
        atama_yap(kurulu, "olmayan_gorev", "claude")


# --- Ozel saglayici ----------------------------------------------------------

def _ozel(db, **degisiklik):
    veri = {
        "anahtar": "yerel-model", "ad": "Yerel model",
        "taban_url": "https://ornek.gecersiz/v1", "model": "m-1",
        "api_anahtari": "gizli-anahtar-123", "user_id": None,
    }
    veri.update(degisiklik)
    return ozel_ekle(db, **veri)


def test_ozel_saglayici_eklenebiliyor(kurulu):
    saglayici = _ozel(kurulu)
    assert saglayici.tur is SaglayiciTuru.OPENAI_UYUMLU
    assert saglayici.yerlesik is False
    assert saglayici.etkin is False  # eklemek ACMAK degildir


def test_ozel_saglayici_anahtari_sifreli_saklaniyor(kurulu):
    saglayici = _ozel(kurulu)
    kayit = kurulu.execute(
        select(SystemSetting).where(SystemSetting.anahtar == saglayici.anahtar_ayari)
    ).scalar_one()
    assert "gizli-anahtar-123" not in kayit.sifreli_deger
    assert decrypt_secret(kayit.sifreli_deger) == "gizli-anahtar-123"


def test_http_adres_reddediliyor(kurulu):
    """http:// olsaydi API anahtari ag uzerinde ACIK giderdi."""
    with pytest.raises(SaglayiciHatasi, match="https"):
        _ozel(kurulu, taban_url="http://ornek.gecersiz/v1")


def test_bozuk_kisa_ad_reddediliyor(kurulu):
    with pytest.raises(SaglayiciHatasi, match="Kısa ad"):
        _ozel(kurulu, anahtar="Yerel Model!")


def test_ayni_kisa_ad_iki_kez_eklenemiyor(kurulu):
    _ozel(kurulu)
    with pytest.raises(SaglayiciHatasi, match="kullanılıyor"):
        _ozel(kurulu)


def test_bos_model_reddediliyor(kurulu):
    with pytest.raises(SaglayiciHatasi, match="Model"):
        _ozel(kurulu, model="   ")


# --- Silme -------------------------------------------------------------------

def test_yerlesik_saglayici_silinemiyor(kurulu):
    with pytest.raises(SaglayiciHatasi, match="silinemez"):
        sil(kurulu, "claude")


def test_kullanilan_saglayici_silinemiyor(kurulu):
    saglayici = _ozel(kurulu)
    saglayici.etkin, saglayici.son_sinama_basarili = True, True
    kurulu.flush()
    atama_yap(kurulu, "content_script", saglayici.anahtar)
    with pytest.raises(SaglayiciHatasi, match="kullanılıyor"):
        sil(kurulu, saglayici.anahtar)


def test_silince_api_anahtari_da_gidiyor(kurulu):
    """Anahtar kalsaydi, silinmis bir saglayicinin sirri sistemde dururdu."""
    saglayici = _ozel(kurulu)
    ayar_adi = saglayici.anahtar_ayari
    sil(kurulu, saglayici.anahtar)
    kalan = kurulu.execute(
        select(SystemSetting).where(SystemSetting.anahtar == ayar_adi)
    ).scalar_one_or_none()
    assert kalan is None
    assert getir(kurulu, "yerel-model") is None


def test_olmayan_saglayici_silinmeye_calisilinca_hata(kurulu):
    with pytest.raises(SaglayiciHatasi, match="bulunamadı"):
        sil(kurulu, "yok-boyle-bir-sey")


# --- Uretimde ornek veri ------------------------------------------------------

def test_uretimde_ornek_veri_saglayicisi_verilmiyor(monkeypatch):
    """Uretimde sahte cikti, kullanicinin gercek sandigi sahte rapordur."""
    from app.ai import registry
    from app.ai.base import ProviderNotConfigured
    from app.core.config import get_settings

    ayarlar = get_settings()
    monkeypatch.setattr(type(ayarlar), "is_production", property(lambda self: True))
    with pytest.raises(ProviderNotConfigured):
        registry.get_provider("claude", mode="fake")


def test_gelistirmede_ornek_veri_saglayicisi_calisiyor():
    from app.ai import registry
    from app.ai.fake import FakeProvider

    assert isinstance(registry.get_provider("claude", mode="fake"), FakeProvider)
