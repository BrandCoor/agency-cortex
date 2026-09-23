"""Panel gorunum tercihleri: tema ve vurgu rengi.

Korunan kurallar:
- Tercih KISIYE ozeldir; baskasinin ekranini degistirmez
- Bilinmeyen deger sayfayi BOZMAZ, varsayilana duser
- Tercih sayfa kaynagina yansir (tema secildiginde gercekten uygulanir)
- Tek tiklik gecis acik yonlendirmeye izin vermez
"""

from __future__ import annotations

import pytest

from app.panel.auth import COOKIE_NAME
from app.services.gorunum import tema_gecerli, vurgu_gecerli

SIFRE = "GucluSifre123!"


def _giris(client, kullanici):
    yanit = client.post(
        "/panel/giris", data={"email": kullanici.email, "password": SIFRE},
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    return yanit.cookies.get(COOKIE_NAME)


@pytest.fixture
def kisi(client, db, make_user):
    def _kur():
        k = make_user(password=SIFRE)
        db.commit()
        _giris(client, k)
        return k

    return _kur


# --- Dogrulama ----------------------------------------------------------------

@pytest.mark.parametrize("deger", ["sistem", "koyu", "acik"])
def test_gecerli_temalar_kabul_ediliyor(deger):
    assert tema_gecerli(deger) == deger


@pytest.mark.parametrize("deger", ["", "mor-tema", "DARK", None])
def test_bilinmeyen_tema_varsayilana_dusuyor(deger):
    """Tema gibi zararsiz bir ayar sayfayi ASLA bozmamali."""
    assert tema_gecerli(deger) == "sistem"


@pytest.mark.parametrize("deger", ["", "fusya", "#ff0000"])
def test_bilinmeyen_vurgu_varsayilana_dusuyor(deger):
    assert vurgu_gecerli(deger) == "mavi"


# --- Panel --------------------------------------------------------------------

def test_sayfa_aciliyor(client, kisi):
    kisi()
    yanit = client.get("/panel/gorunum")
    assert yanit.status_code == 200
    assert "Vurgu rengi" in yanit.text


def test_secilen_tema_sayfaya_yansiyor(client, db, kisi):
    k = kisi()
    client.post("/panel/gorunum", data={"tema": "acik", "vurgu": "yesil"})

    sayfa = client.get("/panel/gorunum")
    assert 'data-tema="acik"' in sayfa.text
    assert 'data-vurgu="yesil"' in sayfa.text
    db.expire_all()
    assert db.get(type(k), k.id).tema == "acik"


def test_bilinmeyen_deger_kaydedilmiyor(client, db, kisi):
    k = kisi()
    client.post("/panel/gorunum", data={"tema": "uydurma", "vurgu": "fusya"})
    db.expire_all()
    taze = db.get(type(k), k.id)
    assert taze.tema == "sistem"
    assert taze.vurgu == "mavi"


def test_tercih_kisiye_ozel(client, db, make_user):
    """Birinin temasi digerinin ekranini DEGISTIRMEMELI."""
    biri = make_user(password=SIFRE)
    digeri = make_user(password=SIFRE)
    db.commit()

    _giris(client, biri)
    client.post("/panel/gorunum", data={"tema": "acik", "vurgu": "mor"})
    client.post("/panel/cikis")

    _giris(client, digeri)
    sayfa = client.get("/panel/gorunum")
    assert 'data-tema="sistem"' in sayfa.text
    assert 'data-vurgu="mavi"' in sayfa.text


def test_tek_tiklik_gecis_calisiyor(client, db, kisi):
    k = kisi()
    client.post("/panel/gorunum/degistir", data={"nereye": "/panel"},
                follow_redirects=False)
    db.expire_all()
    assert db.get(type(k), k.id).tema == "koyu"

    client.post("/panel/gorunum/degistir", data={"nereye": "/panel"},
                follow_redirects=False)
    db.expire_all()
    assert db.get(type(k), k.id).tema == "acik"


def test_gecis_disariya_yonlendirmiyor(client, kisi):
    """Acik yonlendirme: baska siteye goturulemez."""
    kisi()
    yanit = client.post(
        "/panel/gorunum/degistir",
        data={"nereye": "https://kotu.example/calindi"},
        follow_redirects=False,
    )
    assert yanit.headers["location"] == "/panel"


def test_giris_yapmadan_degistirilemiyor(client):
    yanit = client.post("/panel/gorunum/degistir", data={"nereye": "/panel"},
                        follow_redirects=False)
    assert yanit.headers["location"] == "/panel/giris"
