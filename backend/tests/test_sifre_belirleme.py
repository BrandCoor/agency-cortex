"""Tek kullanimlik sifre belirleme bagi testleri.

Bu akis, sifrenin kullanicidan sisteme ulasirken bicim degistirmesinden
kaynaklanan giris arizalarini kokten cozer: sifre hic aktarilmaz, kullanici
dogrudan tarayicida belirler. Bu yuzden guvenlik sinirlari siki test edilir.
"""

from __future__ import annotations

import pytest

from app.core.security import verify_password
from app.panel.auth import COOKIE_NAME
from app.services import sifre_sifirlama
from app.services.sifre_sifirlama import JetonHatasi, jeton_uret, jetonu_tuket

YENI = "YepyeniSifre456!"


@pytest.fixture(autouse=True)
def _temiz_redis():
    """Testler arasinda jeton kalintisi kalmasin."""
    yield
    for anahtar in sifre_sifirlama.redis_client.scan_iter("sifre:belirle:*"):
        sifre_sifirlama.redis_client.delete(anahtar)


# --- Jeton davranisi ---------------------------------------------------------

def test_jeton_tek_kullanimlik(make_user):
    kullanici = make_user()
    jeton = jeton_uret(kullanici.id)

    assert jetonu_tuket(jeton) == kullanici.id
    with pytest.raises(JetonHatasi):
        jetonu_tuket(jeton)


def test_gecersiz_jeton_reddediliyor():
    with pytest.raises(JetonHatasi):
        jetonu_tuket("uydurma-jeton")
    with pytest.raises(JetonHatasi):
        jetonu_tuket("")


def test_jetonun_kendisi_saklanmiyor(make_user):
    """Redis'e erisen biri saklanan degerden jeton uretememeli."""
    kullanici = make_user()
    jeton = jeton_uret(kullanici.id)

    anahtarlar = list(sifre_sifirlama.redis_client.scan_iter("sifre:belirle:*"))
    assert len(anahtarlar) == 1
    assert jeton not in anahtarlar[0]


def test_suresi_dolan_jeton_calismiyor(make_user):
    kullanici = make_user()
    jeton = jeton_uret(kullanici.id, omur_saniye=1)
    # Suresini elle bitir: testi bekletmeden ayni sonucu verir.
    import hashlib
    ozet = hashlib.sha256(jeton.encode()).hexdigest()
    sifre_sifirlama.redis_client.delete(f"sifre:belirle:{ozet}")

    with pytest.raises(JetonHatasi):
        jetonu_tuket(jeton)


# --- Sayfa davranisi ---------------------------------------------------------

def test_gecerli_bagla_form_aciliyor(client, make_user):
    kullanici = make_user()
    jeton = jeton_uret(kullanici.id)

    yanit = client.get(f"/panel/sifre-belirle?jeton={jeton}")

    assert yanit.status_code == 200
    assert 'action="/panel/sifre-belirle"' in yanit.text


def test_gecersiz_bag_404_donuyor(client):
    yanit = client.get("/panel/sifre-belirle?jeton=uydurma")
    assert yanit.status_code == 404
    assert "geçersiz" in yanit.text


def test_sayfayi_acmak_bagi_harcamiyor(client, make_user):
    """Kullanici sayfayi yenilerse bag bozulmamali."""
    kullanici = make_user()
    jeton = jeton_uret(kullanici.id)

    for _ in range(3):
        assert client.get(f"/panel/sifre-belirle?jeton={jeton}").status_code == 200

    yanit = client.post(
        "/panel/sifre-belirle",
        data={"jeton": jeton, "yeni": YENI, "yeni_tekrar": YENI},
        follow_redirects=False,
    )
    assert yanit.status_code == 303


def test_sifre_belirlenince_iceri_aliniyor(client, db, make_user):
    kullanici = make_user(password="EskiSifre1234!")
    jeton = jeton_uret(kullanici.id)

    yanit = client.post(
        "/panel/sifre-belirle",
        data={"jeton": jeton, "yeni": YENI, "yeni_tekrar": YENI},
        follow_redirects=False,
    )

    assert yanit.status_code == 303
    assert yanit.headers["location"] == "/panel"
    assert yanit.cookies.get(COOKIE_NAME)

    db.refresh(kullanici)
    assert verify_password(YENI, kullanici.password_hash)
    assert not verify_password("EskiSifre1234!", kullanici.password_hash)


def test_bag_ikinci_kez_kullanilamiyor(client, db, make_user):
    kullanici = make_user()
    jeton = jeton_uret(kullanici.id)

    ilk = client.post(
        "/panel/sifre-belirle",
        data={"jeton": jeton, "yeni": YENI, "yeni_tekrar": YENI},
        follow_redirects=False,
    )
    assert ilk.status_code == 303

    ikinci = client.post(
        "/panel/sifre-belirle",
        data={"jeton": jeton, "yeni": "BaskaSifre789!", "yeni_tekrar": "BaskaSifre789!"},
        follow_redirects=False,
    )
    assert ikinci.status_code == 404

    db.refresh(kullanici)
    assert verify_password(YENI, kullanici.password_hash)


def test_hatali_girdi_bagi_harcamiyor(client, make_user):
    """Sifreler tutmazsa kullanici ayni bagla tekrar deneyebilmeli."""
    kullanici = make_user()
    jeton = jeton_uret(kullanici.id)

    hatali = client.post(
        "/panel/sifre-belirle",
        data={"jeton": jeton, "yeni": YENI, "yeni_tekrar": "BaskaSey123!"},
    )
    assert hatali.status_code == 400

    dogru = client.post(
        "/panel/sifre-belirle",
        data={"jeton": jeton, "yeni": YENI, "yeni_tekrar": YENI},
        follow_redirects=False,
    )
    assert dogru.status_code == 303


def test_kisa_sifre_reddediliyor_ve_bag_duruyor(client, make_user):
    kullanici = make_user()
    jeton = jeton_uret(kullanici.id)

    kisa = client.post(
        "/panel/sifre-belirle", data={"jeton": jeton, "yeni": "kisa1!", "yeni_tekrar": "kisa1!"}
    )
    assert kisa.status_code == 400

    assert client.get(f"/panel/sifre-belirle?jeton={jeton}").status_code == 200


def test_turkce_harfli_sifre_belirlenip_giris_yapilabiliyor(client, db, make_user):
    """Asil amac: Türkçe harfli şifre artık uçtan uca çalışmalı."""
    kullanici = make_user(email="sahip@ornek.com", password="EskiSifre1234!")
    jeton = jeton_uret(kullanici.id)
    turkce = "Çiğdemİş4103+"

    client.post(
        "/panel/sifre-belirle",
        data={"jeton": jeton, "yeni": turkce, "yeni_tekrar": turkce},
        follow_redirects=False,
    )
    client.post("/panel/cikis")

    giris = client.post(
        "/panel/giris",
        data={"email": kullanici.email, "password": turkce},
        follow_redirects=False,
    )
    assert giris.status_code == 303


def test_pasif_kullanici_sifre_belirleyemiyor(client, db, make_user):
    kullanici = make_user()
    jeton = jeton_uret(kullanici.id)
    kullanici.is_active = False
    db.flush()

    yanit = client.post(
        "/panel/sifre-belirle",
        data={"jeton": jeton, "yeni": YENI, "yeni_tekrar": YENI},
        follow_redirects=False,
    )
    assert yanit.status_code == 404
