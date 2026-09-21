"""Manus API v2 saglayicisi.

BU DOSYADAKI HICBIR DEGER TAHMIN DEGILDIR.
Her sabit, resmi Manus v2 dokumanindan alinmistir; kaynak satiri yaninda
yazilidir (21 Eylul 2026 tarihli dogrulanmis referans).

NEDEN v2:
v1 dokumani resmidir ama DEPRECATED olarak isaretlenmistir ve v2'ye gecis
belirtilir. v1 ile v2 farkli header adlari ve farkli durum kumeleri kullanir;
karistirilmasi sessiz hatalara yol acar.
  v1 header: API_KEY          v2 header: x-manus-api-key
  v1 durumlar: pending/running/completed/failed
  v2 durumlar: running/stopped/waiting/error
Kaynak: open.manus.ai/docs/v2/introduction , /docs/v1/overview

CALISMA BICIMI:
Gorev ASENKRONDUR. task.create bir task_id doner; sonuc icin ya webhook
beklenir ya da task.listMessages ile yoklanir (polling). Bu saglayici
polling kullanir; webhook dogrulamasi ayri bir modulde.
Kaynak: open.manus.ai/docs/v2/task-lifecycle
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

import httpx

from app.ai.base import (
    AIProvider,
    AIProviderError,
    AIRequest,
    AIResponse,
    AIStatus,
    ProviderNotConfigured,
)
from app.core.logging_config import get_logger

log = get_logger("manus")

# --- Dokumandan alinan sabitler ---------------------------------------------

# Kaynak: open.manus.ai/docs/v2/introduction (OpenAPI servers[0].url)
BASE_URL = "https://api.manus.ai"

# Kaynak: open.manus.ai/docs/v2/authentication
API_KEY_HEADER = "x-manus-api-key"

# Kaynak: open.manus.ai/docs/v2/task.create , /task.detail , /task.listMessages
UC_GOREV_OLUSTUR = "/v2/task.create"
UC_GOREV_DETAY = "/v2/task.detail"
UC_MESAJ_LISTESI = "/v2/task.listMessages"
UC_GOREV_DURDUR = "/v2/task.stop"
# Salt okuma; kredi harcamaz. Baglanti sinamasi icin kullanilir.
# Kaynak: open.manus.ai/docs/v2/usage.availableCredits
UC_KREDI_DURUMU = "/v2/usage.availableCredits"

# v2 durum kumesi. Kaynak: open.manus.ai/docs/v2/task.detail
DURUM_CALISIYOR = "running"
DURUM_DURDU = "stopped"
DURUM_BEKLIYOR = "waiting"
DURUM_HATA = "error"

# Kullanici metni yaklasik 5.000 estimated token ile sinirli.
# Kaynak: open.manus.ai/docs/v2/task.create
YAKLASIK_TOKEN_SINIRI = 5000

# listMessages limit araligi 1-200, varsayilan 50.
# Kaynak: open.manus.ai/docs/v2/task.listMessages
MESAJ_LIMITI = 200

# Rate limit: task.create 10/dakika, task.listMessages 100/dakika.
# Kaynak: open.manus.ai/docs/v2/rate-limits
LIMIT_GOREV_OLUSTUR_DAKIKA = 10
LIMIT_MESAJ_LISTESI_DAKIKA = 100

# v2 hata kodlari. Kaynak: open.manus.ai/docs/v2/introduction
YENIDEN_DENENEBILIR_HATALAR = frozenset({"rate_limited", "internal"})


class ManusError(AIProviderError):
    """Manus API hatasi. Dokumandaki error.code degerini tasir."""

    def __init__(self, kod: str, mesaj: str, *, http_durum: int | None = None):
        super().__init__(f"Manus hatasi [{kod}]: {mesaj}")
        self.kod = kod
        self.mesaj = mesaj
        self.http_durum = http_durum

    @property
    def yeniden_denenebilir(self) -> bool:
        return self.kod in YENIDEN_DENENEBILIR_HATALAR


class ManusGorevBasarisiz(AIProviderError):
    """Gorev error durumunda bitti."""


class ManusKrediYetersiz(AIProviderError):
    """Manus kredisi bitmis; yeni gorev baslatilamaz.

    Butce kontrolunun Manus tarafindaki karsiligidir: USD butcesi krediyi
    olcemedigi icin (K-031) sinir burada uygulanir.
    """


class ManusZamanAsimi(AIProviderError):
    """Gorev, bizim belirledigimiz bekleme suresinde bitmedi.

    NOT: Bu sinir DOKUMANDAN DEGIL, bizim urun kararimizdir. Manus dokumani
    maksimum gorev suresi vermez (acikca "DOKUMANDA BULUNAMADI" der).
    """


class ManusProvider(AIProvider):
    """Manus v2 ile cok adimli arastirma gorevi calistirir."""

    name = "manus"
    # Manus'ta model secimi yoktur; gorev tabanli calisir.
    model = "manus-v2"

    # Polling ayarlari. DOKUMANDA POLLING ARALIGI VERILMEZ; asagidaki
    # degerler bizim kararimizdir ve rate limit'e gore secilmistir:
    # task.listMessages 100/dakika sinirina sahip, 5 saniyelik aralik
    # dakikada 12 istek yapar - sinirin cok altinda.
    POLLING_ARALIGI_SANIYE = 5
    VARSAYILAN_BEKLEME_SANIYE = 15 * 60

    def __init__(self, api_key: str | None = None, *, base_url: str = BASE_URL):
        self._api_key = (api_key or "").strip()
        self._base_url = base_url.rstrip("/")

    # --- Yapilandirma --------------------------------------------------------

    @property
    def missing_config(self) -> list[str]:
        return [] if self._api_key else ["MANUS_API_KEY"]

    def _basliklar(self) -> dict[str, str]:
        return {
            API_KEY_HEADER: self._api_key,
            "Content-Type": "application/json",
        }

    # --- Alt seviye istek ----------------------------------------------------

    def _istek(self, metod: str, yol: str, **kwargs: Any) -> dict:
        """Tek bir HTTP istegi yapar ve dokumandaki hata govdesini cozer.

        v2 ortak hata govdesi: {"ok": false, "request_id": ..., "error":
        {"code": ..., "message": ...}}
        Kaynak: open.manus.ai/docs/v2/introduction
        """
        if not self.is_configured:
            raise ProviderNotConfigured(self.name, self.missing_config)

        try:
            with httpx.Client(timeout=30) as istemci:
                yanit = istemci.request(
                    metod, f"{self._base_url}{yol}", headers=self._basliklar(), **kwargs
                )
        except httpx.HTTPError as hata:
            raise ManusError("network", f"Baglanti kurulamadi: {hata}") from hata

        try:
            govde = yanit.json()
        except ValueError as hata:
            raise ManusError(
                "invalid_response",
                f"Yanit JSON degil (HTTP {yanit.status_code})",
                http_durum=yanit.status_code,
            ) from hata

        if not govde.get("ok", False):
            hata_bilgisi = govde.get("error") or {}
            raise ManusError(
                hata_bilgisi.get("code") or f"http_{yanit.status_code}",
                hata_bilgisi.get("message") or "Ayrinti bildirilmedi.",
                http_durum=yanit.status_code,
            )
        return govde

    # --- Gorev islemleri -----------------------------------------------------

    def gorev_olustur(self, metin: str) -> dict:
        """POST /v2/task.create

        Zorunlu govde alani: ust duzey `message`; `message.content` duz string
        veya content-part dizisi olabilir.
        Kaynak: open.manus.ai/docs/v2/task.create
        """
        if not metin.strip():
            raise ManusError("invalid_argument", "Gorev metni bos olamaz.")

        govde = self._istek(
            "POST", UC_GOREV_OLUSTUR, json={"message": {"content": metin}}
        )
        # Yanit alanlari: ok, request_id, task_id, task_title, task_url
        log.info(
            "manus_gorev_olusturuldu",
            task_id=govde.get("task_id"),
            request_id=govde.get("request_id"),
        )
        return govde

    def gorev_detay(self, task_id: str) -> dict:
        """GET /v2/task.detail?task_id=... — Kaynak: docs/v2/task.detail"""
        return self._istek("GET", UC_GOREV_DETAY, params={"task_id": task_id})

    def mesajlari_listele(self, task_id: str, *, order: str = "desc") -> dict:
        """GET /v2/task.listMessages — Kaynak: docs/v2/task.listMessages

        limit varsayilan 50, izin verilen aralik 1-200. order asc/desc.
        """
        return self._istek(
            "GET",
            UC_MESAJ_LISTESI,
            params={"task_id": task_id, "order": order, "limit": MESAJ_LIMITI},
        )

    def gorev_durdur(self, task_id: str) -> dict:
        """POST /v2/task.stop — Kaynak: docs/v2/task.stop"""
        return self._istek("POST", UC_GOREV_DURDUR, json={"task_id": task_id})

    # --- Sonucu bekleme ------------------------------------------------------

    def _durum(self, task_id: str) -> str:
        detay = self.gorev_detay(task_id)
        # Durum alani task nesnesinin icinde veya ust duzeyde olabilir;
        # ikisine de bakiyoruz ki bir bicim degisikliginde sessizce
        # "durum yok" sanmayalim.
        gorev = detay.get("task") or detay
        durum = gorev.get("status") or gorev.get("agent_status")
        if durum is None:
            raise ManusError(
                "invalid_response",
                "Gorev durumu yanitta bulunamadi. API bicimi degismis olabilir.",
            )
        return str(durum)

    def sonucu_bekle(self, task_id: str, *, azami_saniye: int | None = None) -> dict:
        """Gorev bitene kadar yoklar ve son mesaj listesini doner.

        Durum anlamlari (Kaynak: docs/v2/task-lifecycle):
          running  -> yoklamaya devam
          stopped  -> sonuc olaylari okunur
          waiting  -> kullanici girdisi/onayi bekleniyor
          error    -> error_message okunur
        """
        azami = azami_saniye or self.VARSAYILAN_BEKLEME_SANIYE
        baslangic = time.monotonic()

        while True:
            durum = self._durum(task_id)

            if durum == DURUM_DURDU:
                return self.mesajlari_listele(task_id)

            if durum == DURUM_HATA:
                detay = self.gorev_detay(task_id)
                gorev = detay.get("task") or detay
                raise ManusGorevBasarisiz(
                    gorev.get("error_message") or "Gorev hata ile bitti."
                )

            if durum == DURUM_BEKLIYOR:
                # Gorev bizden girdi veya onay bekliyor. OTOMATIK ONAY
                # VERMIYORUZ: sistemin insan onayi olmadan is yapmamasi
                # temel kuraldir. Gorev durdurulup durum bildiriliyor.
                self.gorev_durdur(task_id)
                raise ManusGorevBasarisiz(
                    "Görev kullanıcı girdisi bekliyor. Otomatik onay verilmedi; "
                    "görev durduruldu."
                )

            if time.monotonic() - baslangic > azami:
                self.gorev_durdur(task_id)
                raise ManusZamanAsimi(
                    f"Görev {azami} saniyede bitmedi ve durduruldu. "
                    "(Bu sınır bizim kararımız; Manus dokümanı azami süre vermez.)"
                )

            time.sleep(self.POLLING_ARALIGI_SANIYE)

    @staticmethod
    def metni_topla(mesaj_yaniti: dict) -> str:
        """assistant_message olaylarindan metni birlestirir.

        Kaynak: open.manus.ai/docs/v2/task-lifecycle (V2 metin sonucu)
        """
        mesajlar = mesaj_yaniti.get("messages") or []
        parcalar: list[str] = []
        for mesaj in mesajlar:
            if mesaj.get("type") != "assistant_message":
                continue
            icerik = mesaj.get("content")
            if isinstance(icerik, str):
                parcalar.append(icerik)
            elif isinstance(icerik, list):
                for parca in icerik:
                    if isinstance(parca, dict) and parca.get("type") == "text":
                        parcalar.append(parca.get("text", ""))
        # listMessages varsayilani desc (yeniden eskiye); okunabilir sira icin
        # ters cevriliyor.
        return "\n\n".join(reversed([p for p in parcalar if p])).strip()

    # --- AIProvider arayuzu --------------------------------------------------

    def complete(self, request: AIRequest) -> AIResponse:
        baslangic = time.monotonic()
        metin = f"{request.system}\n\n{request.user_content}".strip()

        # KREDI KONTROLU - cagriDAN ONCE.
        #
        # Manus USD ile degil KREDI ile calisir ve dokumanda kredinin para
        # karsiligi YOKTUR (bkz. DECISIONS.md K-031). Bu yuzden aylik USD
        # butcesi Manus harcamasini kapsayamaz. Kapsayamadigi icin en
        # azindan "kredi bitmisken bos yere cagri yapma" korumasi konur:
        # kredi sifirsa gorev olusturulmaz, sebebi acikca soylenir.
        #
        # usage.availableCredits SALT OKUMADIR ve kredi harcamaz.
        self._krediyi_dogrula()

        olusturma = self.gorev_olustur(metin)
        task_id = olusturma.get("task_id")
        if not task_id:
            raise ManusError("invalid_response", "Yanitta task_id yok.")

        mesajlar = self.sonucu_bekle(task_id)
        cikti = self.metni_topla(mesajlar)

        return AIResponse(
            text=cikti,
            parsed=None,
            provider=self.name,
            model=self.model,
            prompt_version=request.prompt_version,
            # Manus token degil KREDI ile calisir; token alanlari
            # uydurulmaz, bos birakilir.
            input_tokens=None,
            output_tokens=None,
            # Manus dokumaninda para cinsinden API fiyati YOKTUR
            # ("DOKUMANDA BULUNAMADI"). Maliyet uydurmak yerine None.
            estimated_cost_usd=None,
            latency_ms=int((time.monotonic() - baslangic) * 1000),
            status=AIStatus.SUCCEEDED,
        )

    def _krediyi_dogrula(self) -> None:
        """Kredi kalmadiysa cagri BASLATMAZ.

        Kredi durumu okunamazsa cagri ENGELLENMEZ: okunamayan bir degere
        bakip isi durdurmak, calisabilecek bir isi bos yere iptal ederdi.
        Kredi sifir oldugu KESIN oldugunda durulur.
        """
        try:
            govde = self._istek("GET", UC_KREDI_DURUMU)
        except ManusError as hata:
            log.warning("manus_kredi_okunamadi", kod=hata.kod)
            return

        toplam = govde.get("total_credits")
        if toplam is None:
            return

        try:
            kalan = Decimal(str(toplam))
        except (ArithmeticError, ValueError):
            return

        if kalan <= 0:
            raise ManusKrediYetersiz(
                "Manus krediniz bitmiş. Araştırma başlatılmadı. "
                "Manus hesabınızdan kredi ekledikten sonra tekrar çalışacak."
            )

    def health_check(self) -> tuple[bool, str | None]:
        if not self.is_configured:
            return False, f"Eksik ayar: {', '.join(self.missing_config)}"
        return True, f"Manus v2 hazir ({self._base_url})"

    def baglantiyi_sina(self) -> tuple[bool, str]:
        """Anahtarin GERCEKTEN calistigini sunucudan dogrular.

        usage.availableCredits salt okuma bir uctur ve kredi harcamaz;
        bu yuzden sinama icin secildi. Gorev olusturmak sinama amaciyla
        yapilmaz: kredi harcar.
        Kaynak: open.manus.ai/docs/v2/usage.availableCredits

        Anahtarin KENDISI hicbir mesajda yer almaz.
        """
        if not self.is_configured:
            return False, "Manus API anahtarı girilmemiş."

        try:
            govde = self._istek("GET", UC_KREDI_DURUMU)
        except ManusError as hata:
            if hata.kod == "unauthenticated":
                return False, (
                    "Anahtar kabul edilmedi. Manus hesabınızdan yeni bir "
                    "anahtar üretip tekrar girin."
                )
            if hata.kod == "rate_limited":
                return False, "Manus şu an çok fazla istek aldı; biraz sonra tekrar deneyin."
            if hata.kod == "network":
                return False, f"Manus'a bağlanılamadı: {hata.mesaj}"
            return False, f"Manus hatası [{hata.kod}]: {hata.mesaj}"

        toplam = govde.get("total_credits")
        ucretsiz = govde.get("free_credits")
        parcalar = ["Bağlantı çalışıyor."]
        if toplam is not None:
            parcalar.append(f"Toplam kredi: {toplam}")
        if ucretsiz is not None:
            parcalar.append(f"Ücretsiz kredi: {ucretsiz}")
        return True, " ".join(parcalar)


def kredi_maliyeti(yanit: dict) -> Decimal | None:
    """task.detail yanitindaki credit_usage degerini okur.

    Manus KREDI ile calisir; dokumanda kredi basina para karsiligi VERILMEZ.
    Bu yuzden kredi sayisi doner, para birimi donmez.
    Kaynak: open.manus.ai/docs/v2/task.detail , /docs/v2/usage.list
    """
    gorev = yanit.get("task") or yanit
    kullanim = gorev.get("credit_usage")
    return Decimal(str(kullanim)) if kullanim is not None else None
