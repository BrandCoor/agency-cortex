"""Meta kurulum sayfasi.

NEDEN ONEMLI: Meta ayarlari yanlisken hata SESSIZ ve GEC gelir. Izin
ekrani acilir, kullanici izni verir, sonra anahtar degisimi basarisiz
olur ve sebebi hic belli olmaz. Bu sayfa bilinen tutarsizliklari ONCEDEN
bildirmek zorundadir; bildirmezse hicbir ise yaramaz.
"""

from __future__ import annotations

import pytest

from app.platforms import meta_ayar
from app.services.sistem_ayarlari import deger_yaz

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
    # Ayarlar ayni oturumdan okunmali; ayri bir baglanti henuz
    # islenmemis test verisini goremez.
    onceki = meta_ayar.oturum_ureticiyi_ayarla(lambda: _Oturum(db))
    yield kullanici
    meta_ayar.oturum_ureticiyi_ayarla(onceki)


class _Oturum:
    """Var olan test oturumunu kapatmadan odunc verir."""

    def __init__(self, db):
        self._db = db

    def __enter__(self):
        return self._db

    def __exit__(self, *_):
        return False


def test_sayfa_aciliyor(client, yonetici):
    _giris(client, yonetici)
    yanit = client.get("/panel/meta-kurulum")
    assert yanit.status_code == 200
    assert "Meta kurulumu" in yanit.text


def test_normal_kullanici_giremiyor(client, db, make_user):
    kisi = make_user(password=SIFRE)
    db.flush()
    _giris(client, kisi)
    yanit = client.get("/panel/meta-kurulum", follow_redirects=False)
    assert yanit.status_code == 303


def test_eksik_degerler_yaziliyor(client, yonetici):
    _giris(client, yonetici)
    metin = client.get("/panel/meta-kurulum").text
    assert "Eksik değerler var" in metin
    assert "META_APP_ID" in metin


def test_olmayan_uclar_yapistirilacaklar_listesinde_yok(client, yonetici):
    """Var olmayan adresi Meta'ya girmek sessiz basarisizlik demektir."""
    _giris(client, yonetici)
    metin = client.get("/panel/meta-kurulum").text
    assert "/api/v1/oauth/meta/callback" in metin
    assert "/api/v1/oauth/meta/deauthorize" not in metin
    assert "/api/v1/oauth/meta/data-deletion" not in metin
    # Ama neden olmadiklari SOYLENIYOR; sessizce atlanmiyorlar.
    assert "Deauthorize Callback URL" in metin
    assert "henüz yazılmadı" in metin


def test_karisik_yapilandirma_uyariliyor(client, db, yonetici):
    """Izin ekrani facebook, anahtar degisimi instagram olursa akis kirilir."""
    _giris(client, yonetici)
    deger_yaz(db, "META_AUTHORIZE_URL",
              "https://www.facebook.com/v26.0/dialog/oauth", user_id=None)
    deger_yaz(db, "META_TOKEN_URL",
              "https://api.instagram.com/oauth/access_token", user_id=None)
    db.flush()

    metin = client.get("/panel/meta-kurulum").text
    assert "tutarsız" in metin


def test_yayinlama_izni_istenirse_uyariliyor(client, db, yonetici):
    """Bu surumde sistem hicbir sey paylasmaz; gereksiz izin reddedilme sebebi."""
    _giris(client, yonetici)
    # Ayar dogrulamasi yayin kapsamini reddettigi icin dogrudan yaziyoruz.
    from app.core.security import encrypt_secret
    from app.models.ops import SystemSetting

    db.add(SystemSetting(
        anahtar="META_SCOPES",
        sifreli_deger=encrypt_secret("instagram_business_basic,instagram_business_content_publish"),
    ))
    db.flush()

    metin = client.get("/panel/meta-kurulum").text
    assert "Yayınlama izni istenmiş" in metin


def test_menude_bagi_var(client, yonetici):
    _giris(client, yonetici)
    assert "/panel/meta-kurulum" in client.get("/panel").text
