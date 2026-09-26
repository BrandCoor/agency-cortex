"""\"OpenAI uyumlu\" sohbet ucunu kullanan genel saglayici.

BU DOSYA NEDEN VAR
Piyasadaki bircok saglayici (kendi dokumanlarinda "OpenAI uyumlu" diye
gecer) ayni istek bicimini kabul eder. Her biri icin ayri bir dosya
yazmak yerine TEK bir saglayici yazilir; adresi, modeli ve anahtari
KULLANICI girer.

ADRES UYDURULMAZ
Taban adresi (base URL) ve model adi bu dosyada YAZILI DEGILDIR.
Kullanici kendi saglayicisinin dokumanindan kopyalar. Boylece yanlis
bir adresi biz tahmin etmis olmayiz.

DOGRULANAMAYAN KISIM - ACIKCA YAZIYORUM
Istek govdesinin bicimi (/chat/completions, messages[], response_format)
bu gelistirme ortamindan DOGRULANAMADI: disariya cikis kapali, hicbir
saglayicinin resmi dokumanina erisilemiyor. Bu yuzden sistem, sinanmamis
bir saglayiciyi HICBIR goreve atamaz: panelde "Baglantiyi sina"
dugmesiyle GERCEK bir cagri yapilir ve yalnizca basarili olursa
saglayici kullanilabilir hale gelir. Yani dogrulamayi tahmin yerine
gercek cagri yapar.
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
from app.core.logging_config import get_logger

log = get_logger("openai_uyumlu")

ZAMAN_ASIMI = 120.0


class OpenAIUyumluProvider(AIProvider):
    """Sohbet ucunu OpenAI bicimiyle konusan saglayici."""

    def __init__(
        self,
        *,
        anahtar_adi: str,
        taban_url: str,
        model: str,
        api_key: str | None = None,
    ) -> None:
        self.name = anahtar_adi
        # Sondaki egik cizgi adresi bozar: ".../v1/" + "chat/completions"
        # ile ".../v1" + "/chat/completions" ayni sonucu vermeli.
        self.taban_url = (taban_url or "").strip().rstrip("/")
        self.model = (model or "").strip()
        self._api_key = (api_key or "").strip()

    @property
    def missing_config(self) -> list[str]:
        eksik = []
        if not self.taban_url:
            eksik.append("taban adres")
        if not self.model:
            eksik.append("model adı")
        if not self._api_key:
            eksik.append("API anahtarı")
        return eksik

    def _govde(self, request: AIRequest) -> dict[str, Any]:
        mesajlar: list[dict[str, str]] = []
        if request.system:
            mesajlar.append({"role": "system", "content": request.system})
        mesajlar.append({"role": "user", "content": request.user_content})
        return {
            "model": self.model,
            "messages": mesajlar,
            "max_tokens": request.max_tokens,
            # JSON isteriz; cikti ayrica sema ile dogrulanir.
            "response_format": {"type": "json_object"},
        }

    def _istek(self, yol: str, govde: dict | None) -> dict[str, Any]:
        if self.missing_config:
            raise ProviderNotConfigured(self.name, self.missing_config)

        adres = f"{self.taban_url}/{yol.lstrip('/')}"
        basliklar = {"Authorization": f"Bearer {self._api_key}"}
        try:
            with httpx.Client(timeout=ZAMAN_ASIMI) as istemci:
                if govde is None:
                    yanit = istemci.get(adres, headers=basliklar)
                else:
                    yanit = istemci.post(adres, headers=basliklar, json=govde)
        except httpx.TimeoutException as hata:
            raise AIProviderError(
                f"{self.name} {ZAMAN_ASIMI:.0f} saniyede yanıt vermedi."
            ) from hata
        except httpx.HTTPError as hata:
            # Ag hatasi ile "anahtar yanlis" ayri seylerdir.
            raise AIProviderError(f"{self.name} adresine bağlanılamadı: {hata}") from hata

        if yanit.status_code in (401, 403):
            raise AIProviderError(
                f"{self.name}: API anahtarı kabul edilmedi (yetki hatası)."
            )
        if yanit.status_code == 404:
            raise AIProviderError(
                f"{self.name}: adres bulunamadı (404). Taban adresin doğru "
                f"olduğundan emin olun. Denenen: {adres}"
            )
        if yanit.status_code == 429:
            raise AIProviderError(f"{self.name}: çok fazla istek (429).")
        if yanit.status_code >= 500:
            raise AIProviderError(f"{self.name}: sunucu hatası ({yanit.status_code}).")
        if yanit.status_code != 200:
            # Saglayicinin KENDI mesaji en degerli bilgidir; gizlenmez.
            ayrinti = yanit.text[:300].replace("\n", " ")
            raise AIProviderError(
                f"{self.name}: beklenmeyen yanıt ({yanit.status_code}). {ayrinti}"
            )

        try:
            return yanit.json()
        except ValueError as hata:
            raise AIProviderError(f"{self.name}: yanıt JSON değil.") from hata

    def complete(self, request: AIRequest) -> AIResponse:
        veri = self._istek("chat/completions", self._govde(request))

        secenekler = veri.get("choices") or []
        if not secenekler:
            raise AIProviderError(f"{self.name}: yanıtta hiçbir sonuç yok.")

        ilk = secenekler[0]
        bitis = ilk.get("finish_reason")
        metin = ((ilk.get("message") or {}).get("content")) or ""

        if bitis == "length":
            # Kirpilmis JSON'u ayristirmak eksik veriyi tam saymak olurdu.
            raise AIProviderError(
                f"{self.name}: yanıt uzunluk sınırına takıldı; çıktı eksik."
            )
        if not metin.strip():
            raise AIProviderError(f"{self.name}: boş yanıt döndü.")

        try:
            ayrisik = json.loads(metin)
        except ValueError as hata:
            raise AIProviderError(
                f"{self.name}: çıktı JSON olarak okunamadı."
            ) from hata

        kullanim = veri.get("usage") or {}
        return AIResponse(
            text=metin,
            parsed=ayrisik,
            provider=self.name,
            model=veri.get("model") or self.model,
            prompt_version=request.prompt_version,
            input_tokens=kullanim.get("prompt_tokens"),
            output_tokens=kullanim.get("completion_tokens"),
            # Fiyati BILINMIYOR: her saglayicinin kendi tarifesi var ve
            # biz onu goremiyoruz. 0 donmek butceyi sessizce etkisiz
            # kilardi; None "olculemiyor" demektir.
            estimated_cost_usd=None,
            latency_ms=0,
            status=AIStatus.SUCCEEDED,
            confidence="medium",
        )

    def health_check(self) -> tuple[bool, str | None]:
        """GERCEK bir uretim cagrisi yapar.

        Model listesini okumak yetmez: bazi saglayicilarda liste ucu acik
        olup uretim ucu kapali olabilir, ya da model adi yanlis olabilir.
        Bu yuzden en kucuk gercek istegi gonderiyoruz. Maliyeti birkac
        jetondur ve yalnizca dugmeye basildiginda olusur.
        """
        if self.missing_config:
            return False, "Eksik: " + ", ".join(self.missing_config)
        try:
            veri = self._istek(
                "chat/completions",
                {
                    "model": self.model,
                    "messages": [
                        {"role": "user", "content": 'Yalnizca {"ok":true} yaz.'}
                    ],
                    "max_tokens": 16,
                    "response_format": {"type": "json_object"},
                },
            )
        except AIProviderError as hata:
            return False, str(hata)

        secenekler = veri.get("choices") or []
        if not secenekler:
            return False, "Bağlantı kuruldu ama yanıtta sonuç yok."
        model = veri.get("model") or self.model
        return True, f"Bağlantı çalışıyor. Yanıtlayan model: {model}"

    def tahmini_ust_maliyet(self, request: AIRequest) -> Decimal | None:
        """Fiyat tarifesi bilinmedigi icin tahmin YAPILMAZ.

        None, "bedava" demek degildir; "USD olarak olculemiyor" demektir.
        Boyle bir saglayicinin harcamasini USD butcesi koruyamaz;
        saglayicinin kendi siniri gecerlidir. Panel bunu yaziyor.
        """
        return None
