"""Giris ve oturum testleri."""

from __future__ import annotations

from app.core.security import create_token


def test_dogru_bilgiyle_giris_basarili(client, make_user):
    make_user(email="giris@ornek.com", password="DogruSifre123!")
    r = client.post(
        "/api/v1/auth/login", json={"email": "giris@ornek.com", "password": "DogruSifre123!"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["token_type"] == "bearer"


def test_yanlis_sifre_reddedilir(client, make_user):
    make_user(email="giris2@ornek.com", password="DogruSifre123!")
    r = client.post(
        "/api/v1/auth/login", json={"email": "giris2@ornek.com", "password": "YanlisSifre"}
    )
    assert r.status_code == 401


def test_olmayan_kullanici_ve_yanlis_sifre_ayni_yaniti_verir(client, make_user):
    """Yanit farkli olsaydi, hangi e-postalarin kayitli oldugu ogrenilebilirdi."""
    make_user(email="var@ornek.com", password="DogruSifre123!")

    yanlis_sifre = client.post(
        "/api/v1/auth/login", json={"email": "var@ornek.com", "password": "YanlisSifre"}
    )
    olmayan_kullanici = client.post(
        "/api/v1/auth/login", json={"email": "yok@ornek.com", "password": "HerhangiBirSifre"}
    )

    assert yanlis_sifre.status_code == olmayan_kullanici.status_code == 401
    assert yanlis_sifre.json() == olmayan_kullanici.json()


def test_pasif_hesap_giris_yapamaz(client, make_user, db):
    user = make_user(email="pasif@ornek.com", password="DogruSifre123!")
    user.is_active = False
    db.flush()

    r = client.post(
        "/api/v1/auth/login", json={"email": "pasif@ornek.com", "password": "DogruSifre123!"}
    )
    assert r.status_code == 401


def test_me_oturumdaki_kullaniciyi_doner(client, auth_headers, make_user):
    user = make_user(email="ben@ornek.com")
    r = client.get("/api/v1/auth/me", headers=auth_headers(user))
    assert r.status_code == 200
    assert r.json()["email"] == "ben@ornek.com"
    # Sifre ozeti yanitta ASLA bulunmamali.
    assert "password_hash" not in r.json()


def test_yenileme_anahtari_erisim_anahtari_yerine_kullanilamaz(client, make_user):
    """Yenileme anahtari uzun omurludur; erisim icin kullanilirsa
    calinmis bir anahtar cok daha uzun sure gecerli kalirdi."""
    user = make_user()
    refresh = create_token(user.id, "refresh")

    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {refresh}"})
    assert r.status_code == 401


def test_erisim_anahtari_yenileme_icin_kullanilamaz(client, make_user):
    user = make_user()
    access = create_token(user.id, "access")

    r = client.post("/api/v1/auth/refresh", json={"refresh_token": access})
    assert r.status_code == 401


def test_yenileme_calisir(client, make_user):
    user = make_user()
    refresh = create_token(user.id, "refresh")

    r = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_son_giris_zamani_kaydedilir(client, make_user, db):
    user = make_user(email="zaman@ornek.com", password="DogruSifre123!")
    assert user.last_login_at is None

    client.post(
        "/api/v1/auth/login", json={"email": "zaman@ornek.com", "password": "DogruSifre123!"}
    )
    db.refresh(user)
    assert user.last_login_at is not None
