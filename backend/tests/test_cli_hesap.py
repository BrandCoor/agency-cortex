"""Sunucuda ilk yonetici hesabini acan komutun testleri."""

from __future__ import annotations

import io

import pytest
from sqlalchemy import select

from app.cli import hesap
from app.core.security import verify_password
from app.models.identity import User


@pytest.fixture
def komut(db, monkeypatch):
    """Komutun kendi oturumu yerine testin geri alinabilir oturumunu kullanir."""

    class _Sahte:
        def __enter__(self):
            return db

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(hesap, "SessionLocal", lambda: _Sahte())
    return hesap


def _ortam(monkeypatch, **degerler):
    for ad in ["ILK_YONETICI_EMAIL", "ILK_YONETICI_AD", "ILK_YONETICI_SIFRE",
               "HESAP_EMAIL", "HESAP_YENI_SIFRE"]:
        monkeypatch.delenv(ad, raising=False)
    for ad, deger in degerler.items():
        monkeypatch.setenv(ad, deger)


def test_ilk_yonetici_olusturuluyor(komut, db, monkeypatch):
    _ortam(
        monkeypatch,
        ILK_YONETICI_EMAIL="Sahip@Ornek.com",
        ILK_YONETICI_AD="Ajans Sahibi",
        ILK_YONETICI_SIFRE="CokGucluSifre123!",
    )

    assert komut.ilk_yonetici() == 0

    kullanici = db.execute(select(User)).scalar_one()
    # E-posta kucuk harfe cevrilmeli; aksi halde giriste eslesmez.
    assert kullanici.email == "sahip@ornek.com"
    assert kullanici.is_superuser is True
    assert verify_password("CokGucluSifre123!", kullanici.password_hash)
    # Sifrenin kendisi saklanmamali.
    assert "CokGucluSifre123!" not in kullanici.password_hash


def test_kullanici_varsa_hicbir_sey_yapmiyor(komut, db, make_user, monkeypatch):
    mevcut = make_user()
    _ortam(
        monkeypatch,
        ILK_YONETICI_EMAIL="yeni@ornek.com",
        ILK_YONETICI_AD="Yeni Kisi",
        ILK_YONETICI_SIFRE="CokGucluSifre123!",
    )

    assert komut.ilk_yonetici() == 0

    kullanicilar = db.execute(select(User)).scalars().all()
    assert len(kullanicilar) == 1
    assert kullanicilar[0].id == mevcut.id


def test_kisa_sifre_reddediliyor(komut, db, monkeypatch):
    _ortam(
        monkeypatch,
        ILK_YONETICI_EMAIL="sahip@ornek.com",
        ILK_YONETICI_AD="Ajans Sahibi",
        ILK_YONETICI_SIFRE="kisa1!",
    )

    with pytest.raises(hesap.KurulumHatasi):
        komut.ilk_yonetici()

    assert db.execute(select(User)).scalars().all() == []


def test_eksik_bilgi_hata_veriyor(komut, monkeypatch):
    _ortam(monkeypatch, ILK_YONETICI_EMAIL="sahip@ornek.com")

    with pytest.raises(hesap.KurulumHatasi):
        komut.ilk_yonetici()


def test_hata_mesaji_sifreyi_icermiyor(komut, monkeypatch):
    _ortam(
        monkeypatch,
        ILK_YONETICI_EMAIL="sahip@ornek.com",
        ILK_YONETICI_AD="Ajans Sahibi",
        ILK_YONETICI_SIFRE="kisa1!",
    )

    with pytest.raises(hesap.KurulumHatasi) as bilgi:
        komut.ilk_yonetici()

    assert "kisa1!" not in str(bilgi.value)


def test_sifre_degistir_calisiyor(komut, db, make_user, monkeypatch):
    kullanici = make_user(email="sahip@ornek.com")
    _ortam(monkeypatch, HESAP_EMAIL="Sahip@Ornek.com",
           HESAP_YENI_SIFRE="YepyeniSifre456!")

    assert komut.sifre_degistir() == 0

    db.refresh(kullanici)
    assert verify_password("YepyeniSifre456!", kullanici.password_hash)


def test_sifre_degistir_olmayan_hesapta_hata_veriyor(komut, monkeypatch):
    _ortam(monkeypatch, HESAP_EMAIL="yok@ornek.com",
           HESAP_YENI_SIFRE="YepyeniSifre456!")

    with pytest.raises(hesap.KurulumHatasi):
        komut.sifre_degistir()


def test_bilinmeyen_komut_hata_kodu_donuyor(komut):
    assert komut.main(["olmayan-komut"]) == 2
    assert komut.main([]) == 2


def test_bosluklu_sifre_reddediliyor(komut, db, monkeypatch):
    """Kopyala-yapistirda sona kacan bosluk hesabi acar ama girisi bozar."""
    _ortam(
        monkeypatch,
        ILK_YONETICI_EMAIL="sahip@ornek.com",
        ILK_YONETICI_AD="Ajans Sahibi",
        ILK_YONETICI_SIFRE="CokGucluSifre123! ",
    )

    with pytest.raises(hesap.KurulumHatasi) as bilgi:
        komut.ilk_yonetici()

    assert "bosluk" in str(bilgi.value).lower()
    assert db.execute(select(User)).scalars().all() == []


def test_bostan_sifre_degistirilemiyor(komut, make_user, monkeypatch):
    make_user(email="sahip@ornek.com")
    _ortam(monkeypatch, HESAP_EMAIL="sahip@ornek.com",
           HESAP_YENI_SIFRE=" YepyeniSifre456!")

    with pytest.raises(hesap.KurulumHatasi):
        komut.sifre_degistir()


# --- Tanilama ---------------------------------------------------------------

def _tanilama_ciktisi(komut, capsys, monkeypatch, email, sifre):
    monkeypatch.setattr(hesap.sys, "stdin", io.StringIO(f"{email}\n{sifre}\n"))
    assert komut.tanilama() == 0
    return capsys.readouterr().out


def test_tanilama_sifreyi_yazmiyor(komut, make_user, capsys, monkeypatch):
    """En onemli kural: tani ciktisi sifrenin kendisini icermemeli."""
    make_user(email="sahip@ornek.com", password="GizliSifre1234!")

    cikti = _tanilama_ciktisi(
        komut, capsys, monkeypatch, "sahip@ornek.com", "GizliSifre1234!"
    )

    assert "GizliSifre1234!" not in cikti
    assert "uzunluk: 15 karakter" in cikti


def test_tanilama_dogru_sifreyi_taniyor(komut, make_user, capsys, monkeypatch):
    make_user(email="sahip@ornek.com", password="GizliSifre1234!")

    cikti = _tanilama_ciktisi(
        komut, capsys, monkeypatch, "sahip@ornek.com", "GizliSifre1234!"
    )

    assert "UYUSUYOR" in cikti


def test_tanilama_yanlis_sifreyi_taniyor(komut, make_user, capsys, monkeypatch):
    make_user(email="sahip@ornek.com", password="GizliSifre1234!")

    cikti = _tanilama_ciktisi(
        komut, capsys, monkeypatch, "sahip@ornek.com", "BaskaSifre1234!"
    )

    assert "UYUSMUYOR" in cikti


def test_tanilama_eksik_kullaniciyi_bildiriyor(komut, capsys, monkeypatch):
    cikti = _tanilama_ciktisi(
        komut, capsys, monkeypatch, "yok@ornek.com", "GizliSifre1234!"
    )

    assert "kayitli kullanici YOK" in cikti


def test_tanilama_bosluklu_sifreyi_isaret_ediyor(komut, make_user, capsys, monkeypatch):
    make_user(email="sahip@ornek.com", password="GizliSifre1234! ")

    cikti = _tanilama_ciktisi(
        komut, capsys, monkeypatch, "sahip@ornek.com", "GizliSifre1234! "
    )

    assert "basta/sonda bosluk var mi: EVET" in cikti
