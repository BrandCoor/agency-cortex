"""Baglanti sinamasi.

EN ONEMLI KURAL: sinama sonucu anahtarin KENDISINI icermemeli.
Sonuc ekrana basiliyor; anahtar oraya dusurse ekran goruntusu alan
herkes anahtari ele gecirir.
"""

from __future__ import annotations

import httpx
import pytest

from app.services.baglanti_sinama import manus_sina, meta_sina, sina
from app.services.sistem_ayarlari import deger_yaz

GIZLI_ANAHTAR = "sk-COK-GIZLI-MANUS-ANAHTARI-12345"
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
    _giris(client, kullanici)
    return kullanici


# --- Manus -------------------------------------------------------------------

def test_anahtar_yoksa_acikca_soyluyor(db):
    basarili, mesaj = manus_sina(db)
    assert basarili is False
    assert "girilmemiş" in mesaj


def test_calisan_anahtar_kredi_bilgisi_donuyor(db, yonetici, monkeypatch):
    deger_yaz(db, "MANUS_API_KEY", GIZLI_ANAHTAR, user_id=yonetici.id)
    db.flush()

    def sahte(self, metod, url, **kwargs):
        assert url.endswith("/v2/usage.availableCredits")
        # Sinama GOREV OLUSTURMAMALI: gorev kredi harcar.
        assert "task.create" not in url
        return httpx.Response(
            200, json={"ok": True, "total_credits": 1000, "free_credits": 300}
        )

    monkeypatch.setattr(httpx.Client, "request", sahte)
    basarili, mesaj = manus_sina(db)

    assert basarili is True
    assert "1000" in mesaj and "300" in mesaj


def test_gecersiz_anahtar_ne_yapilacagini_soyluyor(db, yonetici, monkeypatch):
    deger_yaz(db, "MANUS_API_KEY", GIZLI_ANAHTAR, user_id=yonetici.id)
    db.flush()

    def sahte(self, metod, url, **kwargs):
        return httpx.Response(
            401,
            json={"ok": False, "error": {"code": "unauthenticated",
                                          "message": "key invalid"}},
        )

    monkeypatch.setattr(httpx.Client, "request", sahte)
    basarili, mesaj = manus_sina(db)

    assert basarili is False
    # Kullaniciya NE YAPACAGINI soylemeli.
    assert "yeni bir" in mesaj.lower() or "tekrar girin" in mesaj.lower()


def test_baglanti_yoksa_aciklaniyor(db, yonetici, monkeypatch):
    deger_yaz(db, "MANUS_API_KEY", GIZLI_ANAHTAR, user_id=yonetici.id)
    db.flush()

    def sahte(self, metod, url, **kwargs):
        raise httpx.ConnectError("ag yok")

    monkeypatch.setattr(httpx.Client, "request", sahte)
    basarili, mesaj = manus_sina(db)
    assert basarili is False
    assert "bağlanılamadı" in mesaj


@pytest.mark.parametrize("http_kod,hata_kodu", [(200, None), (401, "unauthenticated"),
                                                 (429, "rate_limited")])
def test_sinama_sonucu_anahtari_icermiyor(
    db, yonetici, monkeypatch, http_kod, hata_kodu
):
    """Her sonuc yolunda anahtar sizmamali."""
    deger_yaz(db, "MANUS_API_KEY", GIZLI_ANAHTAR, user_id=yonetici.id)
    db.flush()

    def sahte(self, metod, url, **kwargs):
        if hata_kodu is None:
            return httpx.Response(200, json={"ok": True, "total_credits": 5})
        return httpx.Response(
            http_kod,
            json={"ok": False, "error": {"code": hata_kodu, "message": GIZLI_ANAHTAR}},
        )

    monkeypatch.setattr(httpx.Client, "request", sahte)
    _, mesaj = manus_sina(db)
    assert GIZLI_ANAHTAR not in mesaj


# --- Meta --------------------------------------------------------------------

def test_meta_eksik_deger_bildiriyor(db):
    basarili, mesaj = meta_sina(db)
    assert basarili is False
    assert "Eksik" in mesaj


def test_meta_sinamasi_canli_olmadigini_soyluyor(db, yonetici, monkeypatch):
    """Bicim denetimini canli sinama gibi gostermek yaniltici olurdu."""
    monkeypatch.setenv("META_REDIRECT_URI", "https://ornek.test/callback")
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "meta_redirect_uri",
                        "https://ornek.test/callback", raising=False)
    deger_yaz(db, "META_APP_ID", "1067247846198432", user_id=yonetici.id)
    deger_yaz(db, "META_APP_SECRET", "gizli-secret-degeri", user_id=yonetici.id)
    db.flush()

    basarili, mesaj = meta_sina(db)

    assert basarili is True
    assert "canlı bir sınama değildir" in mesaj


def test_meta_rakam_olmayan_app_id_reddediliyor(db, yonetici, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "meta_redirect_uri",
                        "https://ornek.test/callback", raising=False)
    deger_yaz(db, "META_APP_ID", "harf-iceriyor", user_id=yonetici.id)
    deger_yaz(db, "META_APP_SECRET", "x", user_id=yonetici.id)
    db.flush()

    basarili, mesaj = meta_sina(db)
    assert basarili is False
    assert "rakam" in mesaj


# --- Claude ------------------------------------------------------------------

def test_claude_sinamasi_ucret_dogurmuyor(db, yonetici):
    deger_yaz(db, "ANTHROPIC_API_KEY", "sk-ant-deneme", user_id=yonetici.id)
    db.flush()

    basarili, mesaj = sina(db, "ANTHROPIC_API_KEY")

    assert basarili is True
    # Kullanicinin haberi olmadan harcama yapilmadigi acikca soylenmeli.
    assert "harcama yapmıyoruz" in mesaj


# --- Panel ucu ---------------------------------------------------------------

def test_panelden_sinama_calisiyor(client, db, yonetici, monkeypatch):
    deger_yaz(db, "MANUS_API_KEY", GIZLI_ANAHTAR, user_id=yonetici.id)
    db.commit()

    # DIKKAT: TestClient de httpx kullanir. Yama daraltilmazsa testin
    # panele yaptigi istek de yakalanir ve test kendi kendini vurur.
    gercek = httpx.Client.request

    def sahte(self, metod, url, **kwargs):
        if "api.manus.ai" in str(url):
            return httpx.Response(200, json={"ok": True, "total_credits": 777})
        return gercek(self, metod, url, **kwargs)

    monkeypatch.setattr(httpx.Client, "request", sahte)
    yanit = client.post("/panel/ayarlar/sina", data={"anahtar": "MANUS_API_KEY"})

    assert yanit.status_code == 200
    assert "Sınama başarılı" in yanit.text
    assert "777" in yanit.text
    assert GIZLI_ANAHTAR not in yanit.text


def test_sivil_kullanici_sinayamiyor(client, db, make_user):
    kullanici = make_user(password=SIFRE)
    _giris(client, kullanici)
    yanit = client.post("/panel/ayarlar/sina", data={"anahtar": "MANUS_API_KEY"})
    assert yanit.status_code == 404


def test_bilinmeyen_ayar_sinanamiyor(client, yonetici):
    yanit = client.post("/panel/ayarlar/sina", data={"anahtar": "UYDURMA"})
    assert yanit.status_code == 400
