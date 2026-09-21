"""Ortam degiskenlerinden ayarlari okur ve dogrular.

Ayarlar tek bir yerden okunur; kod icinde `os.environ` kullanilmaz.
Eksik veya hatali bir ayar varsa uygulama sessizce yanlis calismak yerine
baslangicta acik bir hata ile durur.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Uretimde kullanilmasi yasak olan sablon degerleri.
PLACEHOLDER_VALUES = {
    "degistir-bu-degeri-uretimde",
    "degistir@example.com",
    "",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Genel ---
    app_env: Literal["development", "staging", "production"] = "development"
    app_name: str = "Agency Cortex"
    log_level: str = "INFO"
    tz: str = "Europe/Istanbul"

    # --- Guvenlik ---
    secret_key: str = "degistir-bu-degeri-uretimde"
    encryption_key: str = "degistir-bu-degeri-uretimde"
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 14

    # --- PostgreSQL ---
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "agency_cortex"
    postgres_user: str = "agency"
    postgres_password: str = "degistir-bu-degeri-uretimde"

    # --- Redis ---
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    # --- Web ---
    public_domain: str = "localhost"
    acme_email: str = "degistir@example.com"
    cors_origins: str = "http://localhost:5173"

    # --- Otomasyon motoru (n8n) ---
    # n8n'in onunde bir kilit (HTTP basic auth) vardir. Kullanicinin bu
    # bilgiyi arayacagi tek yer panel olsun diye buraya okunur; panelde
    # YALNIZCA sistem yoneticisine gosterilir.
    n8n_domain: str = ""
    n8n_basic_user: str = ""
    n8n_basic_password: str = ""

    # --- AI ---
    ai_provider_mode: Literal["fake", "live"] = "fake"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5"
    manus_api_key: str = ""
    manus_webhook_secret: str = ""
    gemini_api_key: str = ""
    ai_monthly_budget_usd: float = 50.0
    ai_max_retries: int = 2
    ai_timeout_seconds: int = 120

    # --- Platform adaptorleri ---
    # "fake": gercek hesap olmadan gelistirme. "live": gercek API.
    platform_mode: Literal["fake", "live"] = "fake"

    # --- Meta / Instagram ---
    # Giris modeli: "instagram_login" veya "facebook_login".
    # Meta App Review dokumani bir uygulamanin bu ikisinden BIRINI secmesini
    # belirtir; ikisi ayni uygulamada birlikte kullanilmaz.
    meta_login_mode: Literal["instagram_login", "facebook_login"] = "instagram_login"
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_redirect_uri: str = ""
    meta_deauthorize_callback_url: str = ""
    meta_data_deletion_request_url: str = ""
    meta_webhook_callback_url: str = ""
    meta_webhook_verify_token: str = ""
    meta_webhook_app_secret: str = ""

    # ASAGIDAKI DEGERLER RESMI META DOKUMANINDAN DOGRULANDI (21 Eylul 2026).
    # Kaynaklar her satirin yaninda; varsayilanlar ortam degiskeni veya panel
    # ayariyla ezilebilir.
    #
    # Graph API surumu v26.0; tanitim tarihi 29 Temmuz 2026. Her surumun en az
    # iki yil calismasi garanti ediliyor.
    # Kaynak: developers.facebook.com/docs/graph-api/changelog/
    meta_api_version: str = "v26.0"

    # Izin ekrani. Guncel "Business Login for Instagram" rehberi (13 Mart 2026)
    # bu adresi gosteriyor.
    #
    # DIKKAT - BELGELENMIS BELIRSIZLIK: Meta'nin daha eski OAuth referansi
    # (17 Temmuz 2025) api.instagram.com/oauth/authorize adresini veriyor.
    # Iki resmi sayfa arasindaki bu farki aciklayan ortak bir kural yok.
    # Daha guncel olan sayfa esas alindi. Izin ekrani acilmazsa once bu
    # adres denenmelidir.
    # Kaynak: developers.facebook.com/documentation/instagram-platform/
    #         instagram-api-with-instagram-login/business-login
    meta_authorize_url: str = "https://www.instagram.com/oauth/authorize"

    # Kodu anahtara ceviren uc. Ayni rehberden.
    meta_token_url: str = "https://api.instagram.com/oauth/access_token"

    # Instagram Login icin veri koku. Facebook Login secilseydi
    # graph.facebook.com/v26.0/ olurdu.
    meta_graph_base_url: str = "https://graph.instagram.com/v26.0/"

    # ILK SURUM BILEREK SALT OKUMA.
    # instagram_business_basic       : profil ve medya metadata'si
    # instagram_business_manage_insights : hesap ve medya icgoruleri
    #
    # Yayinlama, yorum ve mesaj izinleri BILEREK ISTENMIYOR:
    # - Urun karari: v1'de yayinlama kapali.
    # - Meta kurali: yalnizca gercekten kullanilan izinler istenmeli;
    #   kullanilmayan izin istemek App Review'da reddedilme sebebi.
    # Kaynak: developers.facebook.com/documentation/development/permissions
    meta_scopes: str = "instagram_business_basic,instagram_business_manage_insights"

    # Facebook Login secilirse gerekli ek alanlar
    meta_facebook_app_id: str = ""
    meta_facebook_app_secret: str = ""
    meta_facebook_redirect_uri: str = ""
    meta_business_id: str = ""
    meta_page_id: str = ""

    # OAuth state degerinin gecerlilik suresi (CSRF korumasi)
    oauth_state_ttl_seconds: int = 600

    # --- Yayin kilitleri (ilk surumde kapali) ---
    feature_publishing_enabled: bool = False
    feature_comment_reply_enabled: bool = False
    feature_dm_enabled: bool = False

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"LOG_LEVEL su degerlerden biri olmali: {sorted(allowed)}")
        return upper

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def meta_scope_list(self) -> list[str]:
        return [s.strip() for s in self.meta_scopes.split(",") if s.strip()]

    def meta_live_config_errors(self) -> list[str]:
        """Canli Meta baglantisi icin eksik olan ayarlari listeler.

        Bos liste donerse yapilandirma tamamdir. Bu kontrol, dogrulanmamis
        varsayilan degerlerle canli moda gecilmesini engeller.
        """
        eksikler: list[str] = []
        gerekli = {
            "META_APP_ID": self.meta_app_id,
            "META_APP_SECRET": self.meta_app_secret,
            "META_REDIRECT_URI": self.meta_redirect_uri,
            "META_API_VERSION": self.meta_api_version,
            "META_AUTHORIZE_URL": self.meta_authorize_url,
            "META_TOKEN_URL": self.meta_token_url,
            "META_GRAPH_BASE_URL": self.meta_graph_base_url,
            "META_SCOPES": self.meta_scopes,
        }
        for ad, deger in gerekli.items():
            if not deger:
                eksikler.append(ad)
        return eksikler

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def production_safety_errors(self) -> list[str]:
        """Uretimde kabul edilemez ayarlari listeler.

        Bos liste donerse ayarlar uretim icin guvenlidir.
        """
        errors: list[str] = []
        if not self.is_production:
            return errors

        for field in ("secret_key", "encryption_key", "postgres_password"):
            if getattr(self, field) in PLACEHOLDER_VALUES:
                errors.append(
                    f"{field.upper()} hala sablon degerinde. Uretimde gercek bir deger sart."
                )
        if self.acme_email in PLACEHOLDER_VALUES:
            errors.append("ACME_EMAIL ayarlanmamis. HTTPS sertifikasi icin gerekli.")
        if self.ai_provider_mode == "live" and not self.anthropic_api_key:
            errors.append("AI_PROVIDER_MODE=live ama ANTHROPIC_API_KEY bos.")
        if self.platform_mode == "live":
            eksikler = self.meta_live_config_errors()
            if eksikler:
                errors.append(
                    "PLATFORM_MODE=live ama su Meta ayarlari eksik: " + ", ".join(eksikler)
                )
        return errors


@lru_cache
def get_settings() -> Settings:
    return Settings()
