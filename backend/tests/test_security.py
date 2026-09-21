"""Sifre ozeti ve token sifreleme testleri."""

from __future__ import annotations

import unicodedata
from datetime import timedelta

import pytest

from app.core.security import (
    TokenError,
    create_token,
    decode_token,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    verify_password,
)


def test_sifre_duz_metin_olarak_saklanmaz():
    ozet = hash_password("GizliSifre123!")
    assert "GizliSifre123!" not in ozet
    assert ozet.startswith("$argon2")


def test_ayni_sifre_her_seferinde_farkli_ozet_uretir():
    """Ayni ozet uretilseydi, ayni sifreyi kullanan hesaplar tespit edilebilirdi."""
    assert hash_password("AyniSifre1!") != hash_password("AyniSifre1!")


def test_dogru_sifre_dogrulanir():
    assert verify_password("DogruSifre1!", hash_password("DogruSifre1!"))


def test_yanlis_sifre_reddedilir():
    assert not verify_password("YanlisSifre", hash_password("DogruSifre1!"))


def test_bozuk_ozet_istisna_firlatmaz():
    """Veritabaninda bozuk bir kayit olsa bile giris ucu cokmemeli."""
    assert verify_password("herhangi", "bu-gecerli-bir-ozet-degil") is False


def test_bos_sifre_kabul_edilmez():
    with pytest.raises(ValueError):
        hash_password("")


# --- Token sifreleme ---

def test_sifrelenmis_deger_geri_cozulur():
    sir = "EAAGm0PX4ZCpsBA-ornek-erisim-anahtari"
    assert decrypt_secret(encrypt_secret(sir)) == sir


def test_sifreli_metin_icinde_orijinal_deger_gorunmez():
    sir = "cok-gizli-erisim-anahtari"
    assert sir not in encrypt_secret(sir)


def test_ayni_deger_her_seferinde_farkli_sifrelenir():
    sir = "ayni-deger"
    assert encrypt_secret(sir) != encrypt_secret(sir)


def test_bozuk_sifreli_veri_acik_hata_verir():
    with pytest.raises(ValueError):
        decrypt_secret("bu-gecerli-bir-sifreli-metin-degil")


# --- Oturum anahtarlari ---

def test_anahtar_uretilip_cozulur():
    token = create_token("abc-123", "access")
    assert decode_token(token, "access")["sub"] == "abc-123"


def test_suresi_dolmus_anahtar_reddedilir():
    token = create_token("abc-123", "access", expires_delta=timedelta(seconds=-10))
    with pytest.raises(TokenError):
        decode_token(token, "access")


def test_kurcalanmis_anahtar_reddedilir():
    token = create_token("abc-123", "access")
    bozuk = token[:-4] + "XXXX"
    with pytest.raises(TokenError):
        decode_token(bozuk, "access")


def test_yanlis_turdeki_anahtar_reddedilir():
    with pytest.raises(TokenError):
        decode_token(create_token("abc", "refresh"), "access")


def test_her_anahtar_benzersizdir():
    """Ayni kullanici icin uretilen anahtarlar birbirinden ayirt edilebilmeli."""
    a = decode_token(create_token("abc", "access"), "access")
    b = decode_token(create_token("abc", "access"), "access")
    assert a["jti"] != b["jti"]


# --- Unicode gosterim birligi ------------------------------------------------
# Turkce harfler iki farkli sekilde kodlanabilir; ekranda ayni gorunurler.
# Kullanici sifresini bir cihazda olusturup baskasinda yazdiginda bu iki
# gosterim karisabilir. Sifre her iki halde de calismali.

def test_turkce_harfin_iki_gosterimi_de_ayni_sifre_sayiliyor():
    nfc = unicodedata.normalize("NFC", "Eroğlu4103+X")
    nfd = unicodedata.normalize("NFD", "Eroğlu4103+X")

    # Onculde: ikisi ekranda ayni, bayt duzeyinde farkli
    assert nfc != nfd
    assert len(nfd) == len(nfc) + 1

    ozet = hash_password(nfc)
    assert verify_password(nfc, ozet)
    assert verify_password(nfd, ozet)


def test_ters_yonde_de_calisiyor():
    """Sifre birlesik isaretli halde olusturulsa bile duz hali kabul edilmeli."""
    nfc = unicodedata.normalize("NFC", "Güçlüşifre123")
    nfd = unicodedata.normalize("NFD", "Güçlüşifre123")

    ozet = hash_password(nfd)
    assert verify_password(nfc, ozet)
    assert verify_password(nfd, ozet)


def test_normalizasyon_yanlis_sifreyi_kabul_etmiyor():
    """Gosterim birlestirme, farkli sifrelerin gecmesine yol acmamali."""
    ozet = hash_password("Eroğlu4103+X")

    assert not verify_password("Eroglu4103+X", ozet)   # g yerine duz g
    assert not verify_password("Eroğlu4103+Y", ozet)
    assert not verify_password("Eroğlu4103+", ozet)


def test_panel_girisi_iki_gosterimde_de_calisiyor(client, db, make_user):
    """Uctan uca: hesap bir gosterimle acilsa bile digeriyle giris yapilabilmeli."""
    nfc = unicodedata.normalize("NFC", "Eroğlu4103+X")
    nfd = unicodedata.normalize("NFD", "Eroğlu4103+X")
    kullanici = make_user(email="sahip@ornek.com", password=nfc)

    for ad, sifre in [("NFC", nfc), ("NFD", nfd)]:
        yanit = client.post(
            "/panel/giris",
            data={"email": kullanici.email, "password": sifre},
            follow_redirects=False,
        )
        assert yanit.status_code == 303, f"{ad} gosterimiyle giris basarisiz"
