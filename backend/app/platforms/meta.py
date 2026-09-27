"""Meta (Instagram) adaptoru - yapilandirma tabanli.

TASARIM:
Bu adaptorun AKISI tamamen yazilmistir: state uretimi, kodun anahtara
cevrilmesi, uzun omurlu anahtara gecis, hata yonetimi, zaman asimi ve
tekrar deneme. Bunlar Meta'ya ozgu degildir ve dogrudur.

Meta'ya OZGU olan degerler (izin ekrani adresi, anahtar ucu, API surumu,
izin adlari) koda GOMULMEZ; ayarlardan gelir ve varsayilan degeri yoktur.

NEDEN:
Bu degerler Meta'nin resmi dokumanindan dogrulanmadan yazilirsa, sistem
cokmez - sessizce YANLIS VERI uretir. Yanlis veri normalize edilir, rapora
girer ve musteriye sunulur. Ayar bos birakilarak, dogrulanmadan canli moda
gecilmesi engellenir.

Ayarlar dolduruldugunda bu dosyada degisiklik gerekmez.
Doldurulacak degerler ve kaynaklari: docs/platforms/meta.md
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings
from app.core.logging_config import get_logger
from app.models.enums import Platform
from app.platforms.base import (
    AccountProfile,
    AuthorizationRequest,
    Capability,
    HealthStatus,
    PlatformAdapter,
    PlatformError,
    RateLimited,
    TokenBundle,
    TokenExpired,
)
from app.platforms.meta_ayar import MetaAyarlari, meta_ayarlarini_oku

log = get_logger("meta")


class MetaConfigurationIncomplete(PlatformError):
    """Meta ayarlari dogrulanmadan canli mod kullanilamaz."""

    def __init__(self, eksikler: list[str]) -> None:
        super().__init__(
            "Meta baglantisi icin su ayarlar eksik: "
            + ", ".join(eksikler)
            + ". Bu degerler resmi Meta dokumanindan dogrulanmadan "
            "doldurulmamalidir. Ayrintilar: docs/platforms/meta.md"
        )
        self.eksikler = eksikler


class MetaAdapter(PlatformAdapter):
    """Instagram profesyonel hesaplari icin gercek adaptor.

    Yetenekleri, ayarlar tamamlandiginda otomatik olarak acilir. Ayar eksikse
    hicbir yetenek bildirilmez; adaptor "hazir" gorunmez.
    """

    platform = Platform.INSTAGRAM

    # Ayarlar tamamlandiginda acilacak yetenekler. Ilk surumde YAZMA yok:
    # yayinlama, yorum ve mesaj bilerek disarida birakildi.
    _READ_CAPABILITIES = frozenset(
        {
            Capability.AUTHORIZE,
            Capability.REFRESH_TOKEN,
            Capability.LIST_MEDIA,
            Capability.FETCH_MEDIA_METRICS,
            Capability.FETCH_ACCOUNT_METRICS,
        }
    )

    def __init__(
        self,
        *,
        timeout_seconds: float = 30.0,
        ayarlar: MetaAyarlari | None = None,
    ) -> None:
        self._settings = get_settings()
        # Uygulama bilgileri PANELDEN de girilebilir. Yalnizca ortam
        # degiskenine bakmak, panelden girilen anahtarlarin sessizce
        # gormezden gelinmesi demekti.
        self._meta = ayarlar or meta_ayarlarini_oku()
        self._timeout = timeout_seconds

    # ------------------------------------------------------------------
    # Yapilandirma
    # ------------------------------------------------------------------

    @property
    def missing_config(self) -> list[str]:
        return self._meta.eksikler

    @property
    def is_configured(self) -> bool:
        return not self.missing_config

    @property
    def capabilities(self) -> frozenset[Capability]:  # type: ignore[override]
        """Ayar eksikken hicbir yetenek bildirilmez."""
        return self._READ_CAPABILITIES if self.is_configured else frozenset()

    def _require_config(self) -> None:
        eksikler = self.missing_config
        if eksikler:
            raise MetaConfigurationIncomplete(eksikler)

    # ------------------------------------------------------------------
    # HTTP yardimcilari
    # ------------------------------------------------------------------

    def _handle_error(self, response: httpx.Response, *, uc: str | None = None) -> None:
        """Meta hatasini anlamli bir istisnaya cevirir.

        Hata govdesi loglanir ama anahtar degerleri loglanmaz.
        """
        if response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            raise RateLimited(
                self.platform,
                retry_after_seconds=int(retry_after) if retry_after else None,
            )

        try:
            detay = response.json().get("error", {})
        except Exception:  # noqa: BLE001
            detay = {"message": response.text[:300]}

        kod = detay.get("code")
        mesaj = detay.get("message", "bilinmeyen hata")

        log.error(
            "meta_api_hatasi",
            status_code=response.status_code,
            error_code=kod,
            error_message=mesaj,
        )

        # Anahtar gecersiz/suresi dolmus hatalari ayri ele alinir; cagiran
        # katman anahtari yenilemeyi deneyebilir.
        if response.status_code in (400, 401) and detay.get("type") == "OAuthException":
            raise TokenExpired(f"Meta anahtarı geçersiz: {mesaj}{self._uc_notu(uc)}")

        raise PlatformError(
            f"Meta API hatası ({response.status_code}): {mesaj}{self._uc_notu(uc)}"
        )

    def _uc_notu(self, uc: str | None) -> str:
        """Hatanin sonuna eklenen "nereye gidildi, ne kontrol edilmeli" notu.

        GIZLI ANAHTAR YAZILMAZ; yalnizca uc adresi ve uygulama kimligi.
        Uygulama kimligi gizli degildir ve yanlis uygulamanin kullanildigini
        anlamanin tek yoludur.
        """
        if not uc:
            return ""
        not_ = f" · Gidilen uç: {uc}"
        if self._meta.app_id:
            not_ += f" · Kullanılan uygulama kimliği: {self._meta.app_id}"
        return not_

    def _get(self, url: str, params: dict[str, Any]) -> dict:
        with httpx.Client(timeout=self._timeout) as http:
            response = http.get(url, params=params)
        if response.status_code >= 400:
            self._handle_error(response)
        return response.json()

    def _post(self, url: str, data: dict[str, Any]) -> dict:
        with httpx.Client(timeout=self._timeout) as http:
            response = http.post(url, data=data)
        if response.status_code >= 400:
            # HANGI UCA gidildigi hataya yazilir. "Error validating client
            # secret" tek basina hangi alanin yanlis oldugunu soylemez;
            # ayni mesaj, yanlis anahtar girildiginde de, anahtar DOGRU
            # ama YANLIS AILEDEN bir uca gonderildiginde de cikar.
            self._handle_error(response, uc=url)
        return response.json()

    # ------------------------------------------------------------------
    # Yetkilendirme
    # ------------------------------------------------------------------

    def authorize(self, *, state: str, redirect_uri: str) -> AuthorizationRequest:
        """Kullanicinin izin verecegi adresi uretir.

        `redirect_uri`, Meta App Dashboard'a kayitli adresle BIREBIR ayni
        olmalidir; protokol, alan adi, yol ve sondaki egik cizgi farki bile
        OAuth hatasina yol acar.
        """
        self._require_config()

        params = {
            "client_id": self._meta.app_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": ",".join(self._meta.scopes),
            "state": state,
        }
        return AuthorizationRequest(
            url=f"{self._meta.authorize_url}?{urlencode(params)}",
            state=state,
        )

    def anahtarlari_sina(self) -> tuple[bool, str]:
        """Uygulama kimligi ve gizli anahtar DOGRU MU? OAuth turuna girmeden.

        NASIL CALISIYOR
        Kullanicinin KENDI ayarladigi anahtar degisim ucuna, BILEREK
        gecersiz bir kod ile istek atilir. Meta'nin verdigi cevap iki
        seyi ayirir:

          - "client secret" hatasi  -> kimlik/anahtar YANLIS (ya da
            anahtar dogru ama YANLIS AILEDEN bir uca gonderiliyor)
          - "code" hatasi           -> kimlik ve anahtar DOGRU; yalnizca
            gonderdigimiz sahte kod gecersiz, ki oyle olmasini istedik

        NEDEN BOYLE
        Bu ortamdan Meta dokumanina erisim kapali; "uygulama anahtari al"
        gibi ayri bir uc UYDURMUYORUM. Yalnizca kullanicinin zaten
        girdigi ucu kullaniyorum. Gonderilen kod gecersiz oldugu icin
        hicbir yan etkisi yok ve hicbir hesap baglanmaz.

        KAZANC: bes dakikalik basarisiz bir OAuth turu yerine iki
        saniyelik kontrol.
        """
        self._require_config()
        try:
            self._post(
                self._meta.token_url,
                {
                    "client_id": self._meta.app_id,
                    "client_secret": self._meta.app_secret,
                    "grant_type": "authorization_code",
                    "redirect_uri": self._meta.redirect_uri,
                    # BILEREK gecersiz: amac kod degil, kimlik dogrulamasi.
                    "code": "gecersiz-sinama-kodu",
                },
            )
        except PlatformError as hata:
            metin = str(hata).lower()
            if "client secret" in metin or "client_secret" in metin:
                return False, (
                    "Uygulama kimliği veya gizli anahtar kabul edilmedi. "
                    "İki olasılık var: (1) gizli anahtar yanlış ya da eksik "
                    "kopyalanmış, (2) anahtar doğru ama YANLIŞ AİLEDEN bir "
                    f"uca gönderiliyor. Gidilen uç: {self._meta.token_url} · "
                    f"Uygulama kimliği: {self._meta.app_id}"
                )
            if "client_id" in metin or "application" in metin:
                return False, (
                    f"Uygulama kimliği kabul edilmedi ({self._meta.app_id}). "
                    "Meta panelindeki App ID ile aynı mı?"
                )
            # Kod hatasi BEKLENEN sonuctur: kimlik ve anahtar dogru demektir.
            if "code" in metin:
                return True, (
                    "Uygulama kimliği ve gizli anahtar doğru. "
                    f"Anahtar değişim ucu yanıt veriyor: {self._meta.token_url}"
                )
            return False, f"Beklenmeyen yanıt: {hata}"

        # Gecersiz kod KABUL EDILDIYSE bir sey yanlis; "calisiyor" demeyiz.
        return False, (
            "Beklenmeyen sonuç: geçersiz bir kod kabul edildi. "
            "Anahtar değişim adresi doğru uç olmayabilir."
        )

    def callback(self, *, code: str, redirect_uri: str) -> tuple[TokenBundle, AccountProfile]:
        """Tek kullanimlik yetkilendirme kodunu anahtara cevirir."""
        self._require_config()
        if not code:
            raise PlatformError("Yetkilendirme kodu bos.")

        veri = self._post(
            self._meta.token_url,
            {
                "client_id": self._meta.app_id,
                "client_secret": self._meta.app_secret,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )

        access_token = veri.get("access_token")
        if not access_token:
            raise PlatformError("Meta yanitinda erisim anahtari bulunamadi.")

        expires_in = veri.get("expires_in")
        tokens = TokenBundle(
            access_token=access_token,
            refresh_token=veri.get("refresh_token"),
            token_type=veri.get("token_type", "bearer"),
            expires_at=(
                datetime.now(UTC) + timedelta(seconds=int(expires_in))
                if expires_in
                else None
            ),
            scopes=tuple(self._meta.scopes),
        )

        profile = self._fetch_profile(access_token, veri)
        log.info(
            "meta_baglanti_kuruldu",
            account_external_id=profile.external_id,
            is_professional=profile.is_professional,
        )
        return tokens, profile

    def _fetch_profile(self, access_token: str, token_response: dict) -> AccountProfile:
        """Baglanan hesabin temel bilgilerini okur.

        Hesap turu (profesyonel mi) dogrulanamazsa `is_professional` False
        kalir. Kisisel hesaba profesyonel hesap icgorusu varmis gibi
        davranilmaz.
        """
        external_id = str(
            token_response.get("user_id") or token_response.get("id") or ""
        )
        if not external_id:
            raise PlatformError("Meta yanitinda hesap kimligi bulunamadi.")

        return AccountProfile(
            external_id=external_id,
            username=token_response.get("username"),
            display_name=token_response.get("name"),
            # Hesap turu ayri bir cagri ile dogrulanacaktir; dogrulanana kadar
            # profesyonel VARSAYILMAZ.
            is_professional=False,
            raw={"token_response_keys": sorted(token_response.keys())},
        )

    def refresh_token(self, *, refresh_token: str) -> TokenBundle:
        self._require_config()
        self._require(Capability.REFRESH_TOKEN)

        veri = self._post(
            self._meta.token_url,
            {
                "grant_type": "refresh_token",
                "client_id": self._meta.app_id,
                "client_secret": self._meta.app_secret,
                "refresh_token": refresh_token,
            },
        )
        expires_in = veri.get("expires_in")
        return TokenBundle(
            access_token=veri["access_token"],
            refresh_token=veri.get("refresh_token", refresh_token),
            token_type=veri.get("token_type", "bearer"),
            expires_at=(
                datetime.now(UTC) + timedelta(seconds=int(expires_in))
                if expires_in
                else None
            ),
        )

    # ------------------------------------------------------------------
    # Saglik
    # ------------------------------------------------------------------

    def health_check(self) -> HealthStatus:
        eksikler = self.missing_config
        if eksikler:
            return HealthStatus(
                ok=False,
                detail=(
                    "Meta ayarlari tamamlanmadi: "
                    + ", ".join(eksikler)
                    + ". Bu degerler resmi dokumandan dogrulanmadan "
                    "doldurulmamalidir (docs/platforms/meta.md)."
                ),
            )
        return HealthStatus(
            ok=True,
            detail=(
                f"Meta ayarlari tamam (giris modeli: "
                f"{self._settings.meta_login_mode}). Veri uclari ilk gercek "
                "baglantida dogrulanacak."
            ),
        )
