"""Ayarlarin uretim guvenligi testleri."""

from __future__ import annotations

import pytest

from app.core.config import Settings


def _prod(**overrides) -> Settings:
    base = {
        "app_env": "production",
        "secret_key": "gercek-secret",
        "encryption_key": "gercek-encryption",
        "postgres_password": "gercek-parola",
        "acme_email": "admin@agencycortex.tech",
    }
    base.update(overrides)
    return Settings(**base)


def test_uretimde_sablon_sifre_hata_verir():
    s = _prod(secret_key="degistir-bu-degeri-uretimde")
    errors = s.production_safety_errors()
    assert any("SECRET_KEY" in e for e in errors)


def test_uretimde_bos_veritabani_parolasi_hata_verir():
    s = _prod(postgres_password="")
    assert any("POSTGRES_PASSWORD" in e for e in s.production_safety_errors())


def test_gecerli_uretim_ayarlari_hatasizdir():
    assert _prod().production_safety_errors() == []


def test_gelistirme_ortaminda_sablon_degerler_engellenmez():
    s = Settings(app_env="development")
    assert s.production_safety_errors() == []


def test_live_modda_anahtar_yoksa_hata_verir():
    s = _prod(ai_provider_mode="live", anthropic_api_key="")
    assert any("ANTHROPIC_API_KEY" in e for e in s.production_safety_errors())


def test_gecersiz_log_seviyesi_reddedilir():
    with pytest.raises(ValueError):
        Settings(log_level="SACMALIK")


def test_veritabani_adresi_dogru_kurulur():
    s = Settings(
        postgres_user="u", postgres_password="p",
        postgres_host="h", postgres_port=1234, postgres_db="d",
    )
    assert s.database_url == "postgresql+psycopg://u:p@h:1234/d"
