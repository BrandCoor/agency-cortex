"""Uretim ayarlari: neyin uygulamayi DURDURMASI gerekir, neyin gerekmez.

KURAL: yalnizca .env'DEN BASKA YERDEN GELEMEYECEK degerler acilisi
engeller (sifreleme anahtari, veritabani parolasi). Panelden girilebilen
degerler engellemez.

NEDEN: once "canli modda ANTHROPIC_API_KEY bos" acilisi engelliyordu.
Anahtarlar panelden girilmeye baslayinca bu kural tuzaga dondu: canli
moda gecirilen sunucu, kullanici anahtari girebilecegi ekrana
ULASAMADAN acilmayi reddederdi.
"""

from __future__ import annotations

from app.core.config import Settings

TEMEL = {
    "app_env": "production",
    "secret_key": "gercek-bir-anahtar-0123456789",
    "encryption_key": "gercek-bir-sifreleme-0123456789",
    "postgres_password": "gercek-parola-0123456789",
    "acme_email": "ornek@agencycortex.tech",
}


def _ayar(**degisiklik) -> Settings:
    return Settings(**{**TEMEL, **degisiklik})




def test_meta_ayarlari_bos_olsa_bile_acilis_engellenmiyor():
    ayarlar = _ayar(platform_mode="live")
    assert ayarlar.production_safety_errors() == []


def test_sablon_sifreleme_anahtari_acilisi_engelliyor():
    """Bu deger panelden girilemez; sablon kalirsa veri korunmamis olur."""
    ayarlar = _ayar(encryption_key="degistir-bu-degeri-uretimde")
    hatalar = ayarlar.production_safety_errors()
    assert any("ENCRYPTION_KEY" in h for h in hatalar)


def test_sablon_gizli_anahtar_acilisi_engelliyor():
    ayarlar = _ayar(secret_key="degistir-bu-degeri-uretimde")
    assert any("SECRET_KEY" in h for h in ayarlar.production_safety_errors())


def test_gelistirmede_hicbir_ayar_acilisi_engellemiyor():
    ayarlar = Settings(app_env="development", secret_key="degistir-bu-degeri-uretimde")
    assert ayarlar.production_safety_errors() == []
