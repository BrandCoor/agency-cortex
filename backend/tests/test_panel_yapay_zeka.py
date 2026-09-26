"""Yapay zeka sayfasi: saglayici yonetimi ve gorev dagilimi.

Bu sayfa API anahtarlarina dokundugu icin SISTEM YONETICISINE ozeldir.
"""

from __future__ import annotations

import pytest

from app.services.ai_saglayicilar import atamalar, getir, varsayilanlari_kur

SIFRE = "GucluSifre123!"


def _giris(client, kullanici):
    assert client.post(
        "/panel/giris", data={"email": kullanici.email, "password": SIFRE},
        follow_redirects=False,
    ).status_code == 303


@pytest.fixture
def yonetici(client, db, make_user):
    kullanici = make_user(password=SIFRE)
    kullanici.is_superuser = True
    db.flush()
    return kullanici


def test_sayfa_aciliyor(client, yonetici):
    _giris(client, yonetici)
    yanit = client.get("/panel/yapay-zeka")
    assert yanit.status_code == 200
    assert "Sağlayıcılar" in yanit.text
    assert "Claude" in yanit.text


def test_normal_kullanici_giremiyor(client, db, make_user):
    kisi = make_user(password=SIFRE)
    db.flush()
    _giris(client, kisi)
    yanit = client.get("/panel/yapay-zeka", follow_redirects=False)
    assert yanit.status_code == 303
    assert yanit.headers["location"] == "/panel/giris"


def test_oturumsuz_girise_yonlendiriyor(client):
    yanit = client.get("/panel/yapay-zeka", follow_redirects=False)
    assert yanit.status_code == 303


def test_checkbox_saglayiciyi_aciyor(client, db, yonetici):
    _giris(client, yonetici)
    client.get("/panel/yapay-zeka")
    client.post(
        "/panel/yapay-zeka/etkinlik", data={"anahtar": "claude", "etkin": "evet"},
        follow_redirects=False,
    )
    assert getir(db, "claude").etkin is True


def test_sinanmamis_saglayici_atanmak_istenirse_hata_gorunuyor(client, db, yonetici):
    """Sessizce reddetmek, kullanicinin atamanin yapildigini sanmasina yol acardi."""
    _giris(client, yonetici)
    client.get("/panel/yapay-zeka")
    client.post("/panel/yapay-zeka/etkinlik", data={"anahtar": "claude", "etkin": "evet"})
    yanit = client.post(
        "/panel/yapay-zeka/atama",
        data={"gorev": "content_script", "saglayici": "claude"},
    )
    assert yanit.status_code == 400
    assert "Bağlantıyı sına" in yanit.text


def test_sinama_gercek_cagri_yapiyor_ve_sonucu_yaziyor(client, db, yonetici):
    """Anahtar yokken sinama BASARISIZ olmali; sessizce gecmemeli."""
    _giris(client, yonetici)
    client.get("/panel/yapay-zeka")
    yanit = client.post("/panel/yapay-zeka/sina", data={"anahtar": "claude"})
    assert yanit.status_code == 200
    kayit = getir(db, "claude")
    assert kayit.son_sinama_zamani is not None
    assert kayit.son_sinama_basarili is False
    assert kayit.son_sinama_mesaji


def test_ozel_saglayici_formdan_eklenebiliyor(client, db, yonetici):
    _giris(client, yonetici)
    client.get("/panel/yapay-zeka")
    yanit = client.post("/panel/yapay-zeka/ekle", data={
        "anahtar": "yerel-model", "ad": "Yerel model",
        "taban_url": "https://ornek.gecersiz/v1", "model": "m-1",
        "api_anahtari": "cok-gizli-anahtar",
    })
    assert yanit.status_code == 200
    assert getir(db, "yerel-model") is not None
    # Anahtar ekrana GERI YAZILMAZ.
    assert "cok-gizli-anahtar" not in yanit.text


def test_http_adres_formdan_da_reddediliyor(client, db, yonetici):
    _giris(client, yonetici)
    client.get("/panel/yapay-zeka")
    yanit = client.post("/panel/yapay-zeka/ekle", data={
        "anahtar": "acik-adres", "ad": "Açık adres",
        "taban_url": "http://ornek.gecersiz/v1", "model": "m-1",
        "api_anahtari": "x",
    })
    assert yanit.status_code == 400
    assert getir(db, "acik-adres") is None


def test_atama_calisir_saglayiciyla_kaydediliyor(client, db, yonetici):
    _giris(client, yonetici)
    client.get("/panel/yapay-zeka")
    varsayilanlari_kur(db)
    kayit = getir(db, "gemini")
    kayit.etkin, kayit.son_sinama_basarili = True, True
    db.flush()
    yanit = client.post(
        "/panel/yapay-zeka/atama",
        data={"gorev": "trend_research", "saglayici": "gemini"},
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    assert atamalar(db)["trend_research"] == "gemini"


def test_menude_yapay_zeka_bagi_var(client, yonetici):
    """Gorunmeyen bir ozellik, olmayan bir ozelliktir."""
    _giris(client, yonetici)
    assert "/panel/yapay-zeka" in client.get("/panel").text
