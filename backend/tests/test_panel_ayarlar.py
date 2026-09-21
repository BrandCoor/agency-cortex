"""Sistem ayarlari sayfasi (API anahtarlari).

EN ONEMLI KURAL: girilen deger ekrana GERI YAZILMAZ ve LOGLANMAZ.
Bir anahtarin ekranda durmasi, omuz ustunden okunmasina ve tarayici
gecmisinde kalmasina yol acar.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.security import decrypt_secret
from app.models.ops import SystemSetting
from app.services.sistem_ayarlari import deger_oku, deger_yaz

SIFRE = "GucluSifre123!"
ORNEK_ANAHTAR = "sk-ant-api03-COKGIZLIDEGER-1234"


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


@pytest.fixture
def sivil(client, db, make_user):
    """Sistem yoneticisi OLMAYAN kullanici."""
    kullanici = make_user(password=SIFRE)
    _giris(client, kullanici)
    return kullanici


# --- Erisim ------------------------------------------------------------------

def test_yonetici_sayfayi_aciyor(client, yonetici):
    yanit = client.get("/panel/ayarlar")
    assert yanit.status_code == 200
    assert "Sistem ayarları" in yanit.text
    assert "ANTHROPIC_API_KEY" in yanit.text


def test_sivil_kullanici_404_aliyor(client, sivil):
    """403 degil 404: sayfanin varligini bile bildirmiyoruz."""
    assert client.get("/panel/ayarlar").status_code == 404
    assert client.post(
        "/panel/ayarlar", data={"anahtar": "ANTHROPIC_API_KEY", "deger": "x"}
    ).status_code == 404
    assert client.post(
        "/panel/ayarlar/sil", data={"anahtar": "ANTHROPIC_API_KEY"}
    ).status_code == 404


def test_oturumsuz_girise_yonlendiriyor(client):
    yanit = client.get("/panel/ayarlar", follow_redirects=False)
    assert yanit.status_code == 303
    assert yanit.headers["location"] == "/panel/giris"


# --- Kaydetme ----------------------------------------------------------------

def test_anahtar_sifrelenerek_kaydediliyor(client, db, yonetici):
    yanit = client.post(
        "/panel/ayarlar",
        data={"anahtar": "ANTHROPIC_API_KEY", "deger": ORNEK_ANAHTAR},
    )

    assert yanit.status_code == 200
    kayit = db.execute(select(SystemSetting)).scalars().one()
    # Veritabaninda DUZ METIN olmamali.
    assert ORNEK_ANAHTAR not in kayit.sifreli_deger
    # Ama cozuldugunde aynen geri gelmeli.
    assert decrypt_secret(kayit.sifreli_deger) == ORNEK_ANAHTAR
    assert kayit.son_dort == "1234"
    assert kayit.degistiren_user_id == yonetici.id


def test_anahtar_ekrana_geri_yazilmiyor(client, yonetici):
    """En kritik test: deger hicbir yanitta gorunmemeli."""
    kaydet = client.post(
        "/panel/ayarlar",
        data={"anahtar": "ANTHROPIC_API_KEY", "deger": ORNEK_ANAHTAR},
    )
    assert ORNEK_ANAHTAR not in kaydet.text

    tekrar = client.get("/panel/ayarlar")
    assert ORNEK_ANAHTAR not in tekrar.text
    # Yalnizca son dort karakter gosterilmeli.
    assert "1234" in tekrar.text
    assert "tanımlı" in tekrar.text


def test_anahtar_loglanmiyor(client, yonetici, caplog):
    import logging

    with caplog.at_level(logging.INFO):
        client.post(
            "/panel/ayarlar",
            data={"anahtar": "ANTHROPIC_API_KEY", "deger": ORNEK_ANAHTAR},
        )

    tum_kayit = " ".join(k.getMessage() for k in caplog.records)
    assert ORNEK_ANAHTAR not in tum_kayit


def test_ayni_anahtar_guncelleniyor_cogalmiyor(client, db, yonetici):
    for deger in ["ilk-deger-aaaa", "ikinci-deger-bbbb"]:
        client.post("/panel/ayarlar", data={"anahtar": "GEMINI_API_KEY", "deger": deger})

    kayitlar = db.execute(select(SystemSetting)).scalars().all()
    assert len(kayitlar) == 1
    assert decrypt_secret(kayitlar[0].sifreli_deger) == "ikinci-deger-bbbb"
    assert kayitlar[0].son_dort == "bbbb"


def test_bos_deger_reddediliyor(client, db, yonetici):
    yanit = client.post(
        "/panel/ayarlar", data={"anahtar": "ANTHROPIC_API_KEY", "deger": "   "}
    )
    assert yanit.status_code == 400
    assert db.execute(select(SystemSetting)).scalars().all() == []


def test_bilinmeyen_ayar_reddediliyor(client, db, yonetici):
    yanit = client.post(
        "/panel/ayarlar", data={"anahtar": "UYDURMA_ANAHTAR", "deger": "x"}
    )
    assert yanit.status_code == 400
    assert db.execute(select(SystemSetting)).scalars().all() == []


def test_ayar_silinebiliyor(client, db, yonetici):
    client.post("/panel/ayarlar", data={"anahtar": "MANUS_API_KEY", "deger": "abcd1234"})
    assert db.execute(select(SystemSetting)).scalars().all() != []

    yanit = client.post("/panel/ayarlar/sil", data={"anahtar": "MANUS_API_KEY"})

    assert yanit.status_code == 200
    assert db.execute(select(SystemSetting)).scalars().all() == []


# --- Okuma davranisi ---------------------------------------------------------

def test_veritabani_ortam_degiskenini_geciyor(db, yonetici, monkeypatch):
    """Panelden girilen deger, sunucudaki ayardan onceliklidir."""
    monkeypatch.setenv("GEMINI_API_KEY", "sunucudaki-deger")
    assert deger_oku(db, "GEMINI_API_KEY") == "sunucudaki-deger"

    deger_yaz(db, "GEMINI_API_KEY", "panelden-girilen", user_id=yonetici.id)
    db.flush()
    assert deger_oku(db, "GEMINI_API_KEY") == "panelden-girilen"


def test_hicbir_yerde_yoksa_none_donuyor(db, monkeypatch):
    monkeypatch.delenv("MANUS_API_KEY", raising=False)
    assert deger_oku(db, "MANUS_API_KEY") is None


def test_cozulemeyen_deger_none_donuyor(db, yonetici):
    """ENCRYPTION_KEY degisirse: uydurma deger dondurmek yerine 'yok' denir."""
    deger_yaz(db, "MANUS_API_KEY", "gecerli-deger", user_id=yonetici.id)
    db.flush()
    kayit = db.execute(select(SystemSetting)).scalars().one()
    kayit.sifreli_deger = "bozuk-sifreli-metin"
    db.flush()

    assert deger_oku(db, "MANUS_API_KEY") is None
