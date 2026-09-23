"""Google Gemini saglayicisi.

BU DOSYADAKI UC ADRESLERI VE ALAN ADLARI TAHMIN DEGILDIR.
Hepsi Google'in resmi, makine-okunur API tanimindan (discovery document)
alinmistir:
    https://generativelanguage.googleapis.com/$discovery/rest?version=v1beta
23 Eylul 2026'da okundu.

Dogrulanan noktalar:
  baseUrl     : https://generativelanguage.googleapis.com/
  uretim ucu  : POST v1beta/{model}:generateContent
  istek       : GenerateContentRequest
                  .contents[]        -> Content{parts[].text, role}
                  .systemInstruction -> Content
                  .generationConfig  -> GenerationConfig
                                          .responseMimeType
                                          .maxOutputTokens
                                          .temperature
  yanit       : GenerateContentResponse
                  .candidates[].content.parts[].text
                  .candidates[].finishReason
                  .usageMetadata.promptTokenCount / .candidatesTokenCount
  model listesi: GET v1beta/models   (salt okuma, jeton harcamaz)
  kimlik      : 'key' sorgu parametresi (tanimdaki global parametre)

NEDEN GEMINI: toplu siniflandirma gibi cok sayida kisa isin ucuz ve hizli
yapilmasi icin. Uzun akil yurutme isleri Claude'a gider (registry.py).
"""

from __future__ import annotations

import json
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
from app.ai.pricing import estimate_cost
from app.core.logging_config import get_logger

log = get_logger("gemini")

# --- Resmi API tanimindan alinan sabitler -----------------------------------

BASE_URL = "https://generativelanguage.googleapis.com"
API_SURUMU = "v1beta"

#: Varsayilan model. Fiyati pricing.py'de tanimli olmalidir.
VARSAYILAN_MODEL = "gemini-2.5-flash"

#: Istek zaman asimi (saniye). Sonsuz bekleme YOK.
ZAMAN_ASIMI = 90.0


class GeminiProvider(AIProvider):
    """Gemini ile JSON cikti ureten saglayici."""

    name = "gemini"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = (api_key or "").strip()
        self.model = model or VARSAYILAN_MODEL

    # --- Yapilandirma --------------------------------------------------------

    @property
    def missing_config(self) -> list[str]:
        return [] if self._api_key else ["GEMINI_API_KEY"]

    def _anahtar(self) -> str:
        if not self._api_key:
            raise ProviderNotConfigured(self.name, self.missing_config)
        return self._api_key

    # --- Istek gonderme ------------------------------------------------------

    def _istek(self, yol: str, govde: dict | None = None) -> dict[str, Any]:
        """Gemini'ye istek gonderir ve JSON yaniti doner.

        ANAHTAR LOGLANMAZ: adres sorgu parametresinde anahtar tasidigi
        icin tam adres hicbir log satirina yazilmaz.
        """
        adres = f"{BASE_URL}/{API_SURUMU}/{yol}"
        try:
            with httpx.Client(timeout=ZAMAN_ASIMI) as istemci:
                if govde is None:
                    yanit = istemci.get(adres, params={"key": self._anahtar()})
                else:
                    yanit = istemci.post(
                        adres, params={"key": self._anahtar()}, json=govde
                    )
        except httpx.TimeoutException as hata:
            raise AIProviderError(
                f"Gemini {ZAMAN_ASIMI:.0f} saniyede yanit vermedi."
            ) from hata
        except httpx.HTTPError as hata:
            # Ag hatasi ile "anahtar yanlis" AYRI seylerdir; karistirmak
            # kullaniciya dogru anahtarini sildirtirdi.
            raise AIProviderError(f"Gemini'ye bağlanılamadı: {hata}") from hata

        if yanit.status_code == 400:
            raise AIProviderError(
                "Gemini isteği reddetti (400). İstek biçimi veya model adı "
                f"hatalı olabilir. Model: {self.model}"
            )
        if yanit.status_code in (401, 403):
            raise AIProviderError(
                "Gemini anahtarı kabul edilmedi (yetki hatası). "
                "Anahtarı ve API erişiminin açık olduğunu kontrol edin."
            )
        if yanit.status_code == 429:
            raise AIProviderError(
                "Gemini çok fazla istek aldı (429). Bir süre sonra tekrar deneyin."
            )
        if yanit.status_code >= 500:
            raise AIProviderError(
                f"Gemini sunucu hatası ({yanit.status_code})."
            )
        if yanit.status_code != 200:
            raise AIProviderError(f"Gemini beklenmeyen yanıt: {yanit.status_code}")

        try:
            return yanit.json()
        except ValueError as hata:
            raise AIProviderError("Gemini yanıtı okunamadı (geçersiz JSON).") from hata

    # --- Uretim --------------------------------------------------------------

    def complete(self, request: AIRequest) -> AIResponse:
        self._anahtar()

        yapilandirma: dict[str, Any] = {
            # JSON isteriz: cikti semaya gore dogrulanacak.
            "responseMimeType": "application/json",
            "maxOutputTokens": request.max_tokens,
        }
        if request.json_schema:
            # Tanimda GenerationConfig.responseSchema mevcut.
            yapilandirma["responseSchema"] = _sema_sadelestir(request.json_schema)

        govde: dict[str, Any] = {
            "contents": [
                {"role": "user", "parts": [{"text": request.user_content}]}
            ],
            "generationConfig": yapilandirma,
        }
        if request.system:
            govde["systemInstruction"] = {"parts": [{"text": request.system}]}

        veri = self._istek(f"models/{self.model}:generateContent", govde)

        adaylar = veri.get("candidates") or []
        if not adaylar:
            # Bos yanit SESSIZCE gecilmez; sebebi varsa yazilir.
            sebep = (veri.get("promptFeedback") or {}).get("blockReason")
            raise AIProviderError(
                f"Gemini hiçbir yanıt üretmedi. Sebep: {sebep or 'bildirilmedi'}"
            )

        aday = adaylar[0]
        bitis = aday.get("finishReason")
        metin = "".join(
            p.get("text", "")
            for p in (aday.get("content") or {}).get("parts") or []
        )

        if bitis == "MAX_TOKENS":
            # Kirpilmis JSON'u ayristirmaya calismak, eksik veriyi tam
            # saymak demektir. Acikca hata veriyoruz.
            raise AIProviderError(
                "Gemini yanıtı uzunluk sınırına takıldı; çıktı eksik. "
                "İstem kısaltılmalı veya sınır yükseltilmelidir."
            )
        if bitis and bitis not in ("STOP", "MAX_TOKENS"):
            raise AIProviderError(f"Gemini yanıtı tamamlamadı: {bitis}")
        if not metin.strip():
            raise AIProviderError("Gemini boş yanıt döndü.")

        try:
            ayrisik = json.loads(metin)
        except ValueError as hata:
            raise AIProviderError(
                "Gemini çıktısı JSON olarak okunamadı."
            ) from hata

        kullanim = veri.get("usageMetadata") or {}
        girdi_jeton = kullanim.get("promptTokenCount")
        cikti_jeton = kullanim.get("candidatesTokenCount")

        return AIResponse(
            text=metin,
            parsed=ayrisik,
            provider=self.name,
            model=veri.get("modelVersion") or self.model,
            prompt_version=request.prompt_version,
            input_tokens=girdi_jeton,
            output_tokens=cikti_jeton,
            estimated_cost_usd=_maliyet(self.model, girdi_jeton, cikti_jeton),
            latency_ms=None,
            status=AIStatus.SUCCEEDED,
            confidence="medium",
        )

    # --- Saglik --------------------------------------------------------------

    def health_check(self) -> tuple[bool, str | None]:
        """Model listesini okur.

        Bu uc SALT OKUMADIR: jeton harcamaz, ucret dogurmaz. Bir mesaj
        gondererek sinamak her denemede para harcamak olurdu.
        """
        if not self.is_configured:
            return False, "GEMINI_API_KEY girilmedi."
        try:
            veri = self._istek("models")
        except AIProviderError as hata:
            return False, str(hata)

        modeller = veri.get("models") or []
        return True, f"Bağlantı çalışıyor. {len(modeller)} model erişilebilir."


def _maliyet(model: str, girdi: int | None, cikti: int | None) -> Decimal | None:
    """Maliyeti hesaplar; fiyat bilinmiyorsa None doner.

    Bilinmeyen fiyat icin 0 donmek, butce kilidini sessizce etkisiz
    kilardi. Bu yuzden hata YUTULMAZ, None donulur ve cagiran taraf
    bunu "bilinmiyor" olarak isler.
    """
    from app.ai.pricing import UnknownModelPricing

    try:
        return estimate_cost(model, input_tokens=girdi, output_tokens=cikti)
    except UnknownModelPricing:
        log.warning("gemini_fiyat_bilinmiyor", model=model)
        return None


def _sema_sadelestir(sema: dict[str, Any]) -> dict[str, Any]:
    """Pydantic semasini Gemini'nin kabul ettigi alanlara indirger.

    Gemini'nin Schema tipi JSON Schema'nin TAMAMINI kabul etmez
    (ornegin $defs/$ref cozumlenmis olmali, title gibi alanlar gereksiz).
    Desteklenmeyen alani gondermek 400 hatasi verir.
    """
    izinli = {
        "type", "format", "description", "nullable", "enum",
        "items", "properties", "required",
    }

    def _temizle(dugum: Any) -> Any:
        if isinstance(dugum, list):
            return [_temizle(d) for d in dugum]
        if not isinstance(dugum, dict):
            return dugum
        sonuc = {}
        for anahtar, deger in dugum.items():
            if anahtar not in izinli:
                continue
            if anahtar == "properties" and isinstance(deger, dict):
                # DIKKAT: burada anahtarlar ALAN ADLARIDIR, sema kelimesi
                # degil. Suzgeci burada da uygulamak, "a" adli bir alani
                # sema kelimesi sanip SILERDI ve cikti bos gelirdi.
                sonuc[anahtar] = {ad: _temizle(alt) for ad, alt in deger.items()}
            elif anahtar == "required":
                # Alan adlari listesi; icerigi sema degildir.
                sonuc[anahtar] = list(deger)
            else:
                sonuc[anahtar] = _temizle(deger)
        return sonuc

    return _temizle(sema)
