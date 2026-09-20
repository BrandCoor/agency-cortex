"""Claude API saglayicisi.

Anthropic resmi Python SDK'si kullanilir (ham HTTP DEGIL).

DOGRULANMIS PARAMETRELER (Anthropic resmi dokumani, onbellek 2026-06-24):
- Model kimligi: "claude-opus-5" (tarih son eki EKLENMEZ)
- Dusunme: thinking={"type": "adaptive"} - budget_tokens KALDIRILDI,
  gonderilirse 400 doner
- Caba: output_config={"effort": ...} - ust seviyede DEGIL, output_config icinde
- Yapilandirilmis cikti: output_config={"format": {"type": "json_schema", ...}}
  (eski "output_format" parametresi kullanimdan kaldirildi)
- Assistant prefill Opus 5'te 400 doner - KULLANILMAZ
- max_tokens akissiz istekler icin ~16000 (zaman asimi sinirinin altinda kalir)
"""

from __future__ import annotations

import json
import time
from typing import Any

from app.ai.base import (
    AIProvider,
    AIProviderError,
    AIRateLimited,
    AIRequest,
    AIResponse,
    AIStatus,
    AITimeout,
    ProviderNotConfigured,
)
from app.ai.pricing import estimate_cost
from app.core.config import get_settings
from app.core.logging_config import get_logger

log = get_logger("ai.claude")

# Resmi dokumandan dogrulanmis model kimligi. Tarih son eki EKLENMEZ.
DEFAULT_MODEL = "claude-opus-5"


class ClaudeProvider(AIProvider):
    """Marka dili, icerik senaryosu ve stratejik yorum icin kullanilir."""

    name = "claude"

    def __init__(self, *, model: str | None = None, timeout_seconds: float | None = None):
        settings = get_settings()
        self._settings = settings
        self.model = model or settings.anthropic_model or DEFAULT_MODEL
        self._timeout = timeout_seconds or float(settings.ai_timeout_seconds)

    @property
    def missing_config(self) -> list[str]:
        eksik: list[str] = []
        if not self._settings.anthropic_api_key:
            eksik.append("ANTHROPIC_API_KEY")
        return eksik

    def _client(self):
        """SDK istemcisini olusturur.

        Import burada yapilir; boylece anahtar olmadan calisan gelistirme
        ortaminda paket yuklu olmasa bile sistem acilir.
        """
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - paket her zaman kurulu
            raise AIProviderError(
                "anthropic paketi kurulu degil. `pip install anthropic` gerekir."
            ) from exc

        # SDK kendi icinde yeniden deneme yapar (408/409/429/5xx ve baglanti
        # hatalari). Ustune bizim katmanimizda tekrar denenmesi, ayni cagrinin
        # kat kat fazla maliyetlenmesine yol acardi.
        return anthropic.Anthropic(
            api_key=self._settings.anthropic_api_key,
            timeout=self._timeout,
            max_retries=self._settings.ai_max_retries,
        )

    def complete(self, request: AIRequest) -> AIResponse:
        eksik = self.missing_config
        if eksik:
            raise ProviderNotConfigured(self.name, eksik)

        import anthropic

        client = self._client()

        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": request.max_tokens,
            "system": request.system,
            "messages": [{"role": "user", "content": request.user_content}],
            # Adaptif dusunme: model ne kadar dusunecegine kendi karar verir.
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": request.effort},
        }

        if request.json_schema is not None:
            # Yapilandirilmis cikti: yanit dogrudan bu semaya uyar.
            params["output_config"]["format"] = {
                "type": "json_schema",
                "schema": request.json_schema,
            }

        baslangic = time.perf_counter()
        try:
            response = client.messages.create(**params)
        except anthropic.RateLimitError as exc:
            log.warning("claude_istek_siniri", task_type=request.task_type)
            raise AIRateLimited(self.name) from exc
        except anthropic.APITimeoutError as exc:
            log.warning("claude_zaman_asimi", task_type=request.task_type)
            raise AITimeout(f"Claude zaman asimina ugradi ({self._timeout}s).") from exc
        except anthropic.AuthenticationError as exc:
            raise ProviderNotConfigured(self.name, ["ANTHROPIC_API_KEY (gecersiz)"]) from exc
        except anthropic.APIStatusError as exc:
            log.error("claude_api_hatasi", status_code=exc.status_code)
            raise AIProviderError(f"Claude API hatasi ({exc.status_code}).") from exc
        except anthropic.APIConnectionError as exc:
            raise AIProviderError("Claude API'ye baglanilamadi.") from exc

        gecen_ms = int((time.perf_counter() - baslangic) * 1000)

        # Guvenlik nedeniyle reddedilen istek HTTP 200 doner; icerige
        # bakmadan ONCE stop_reason kontrol edilmelidir.
        if getattr(response, "stop_reason", None) == "refusal":
            ayrinti = getattr(response, "stop_details", None)
            kategori = getattr(ayrinti, "category", None) if ayrinti else None
            log.warning("claude_reddetti", category=kategori, task_type=request.task_type)
            raise AIProviderError(
                f"Claude bu istegi guvenlik nedeniyle reddetti (kategori: {kategori})."
            )

        metin = next(
            (b.text for b in response.content if getattr(b, "type", None) == "text"),
            "",
        )
        if not metin:
            raise AIProviderError("Claude yanitinda metin bulunamadi.")

        cozulmus: dict[str, Any] | None = None
        if request.json_schema is not None:
            try:
                cozulmus = json.loads(metin)
            except json.JSONDecodeError as exc:
                raise AIProviderError(
                    "Claude yaniti gecerli JSON degil."
                ) from exc

        kullanim = response.usage
        girdi = getattr(kullanim, "input_tokens", None)
        cikti = getattr(kullanim, "output_tokens", None)
        maliyet = estimate_cost(self.model, input_tokens=girdi, output_tokens=cikti)

        log.info(
            "claude_cagrisi",
            task_type=request.task_type,
            model=self.model,
            prompt_version=request.prompt_version,
            input_tokens=girdi,
            output_tokens=cikti,
            estimated_cost_usd=str(maliyet) if maliyet is not None else None,
            latency_ms=gecen_ms,
        )

        return AIResponse(
            text=metin,
            parsed=cozulmus,
            provider=self.name,
            model=self.model,
            prompt_version=request.prompt_version,
            input_tokens=girdi,
            output_tokens=cikti,
            estimated_cost_usd=maliyet,
            latency_ms=gecen_ms,
            status=AIStatus.SUCCEEDED,
        )

    def count_tokens(self, request: AIRequest) -> int | None:
        """Cagri yapmadan once girdi token sayisini olcer.

        Butce kontrolu icin kullanilir: pahali bir cagri baslamadan once
        maliyetin ust siniri kestirilebilir.
        """
        if self.missing_config:
            return None
        try:
            client = self._client()
            sonuc = client.messages.count_tokens(
                model=self.model,
                system=request.system,
                messages=[{"role": "user", "content": request.user_content}],
            )
            return sonuc.input_tokens
        except Exception:  # noqa: BLE001 - olcum basarisizsa cagri engellenmez
            log.warning("token_sayimi_basarisiz", task_type=request.task_type)
            return None

    def health_check(self) -> tuple[bool, str | None]:
        eksik = self.missing_config
        if eksik:
            return False, f"Claude ayarlari eksik: {', '.join(eksik)}"
        return True, f"Claude hazir (model: {self.model})."


class ManusProviderStub(AIProvider):
    """Manus arastirma saglayicisi - HENUZ TAMAMLANMADI.

    Manus API v2 dokumantasyonuna gelistirme ortamindan erisilemedi
    (docs.manus.ai -> 403). Endpoint, kimlik dogrulama, gorev yasam dongusu
    ve webhook ayrintilari tahminle yazilmayacak.

    Durum: hicbir yetenek bildirmiyor; cagrildiginda acik hata verir.
    """

    name = "manus"
    model = "manus-v2"

    @property
    def missing_config(self) -> list[str]:
        return ["MANUS_API_DOKUMANTASYONU_DOGRULANMADI"]

    def complete(self, request: AIRequest) -> AIResponse:
        from app.ai.base import ProviderNotImplemented

        raise ProviderNotImplemented(self.name)

    def health_check(self) -> tuple[bool, str | None]:
        return False, (
            "Manus entegrasyonu tamamlanmadi. Resmi API v2 dokumantasyonuna "
            "erisim engelli; endpoint ve akis tahminle yazilmayacak."
        )


class GeminiProviderStub(AIProvider):
    """Gemini saglayicisi - ilk surumde BILEREK yok.

    Urun karari: ilk surumde Gemini zorunlu bagimlilik degildir. Arayuz
    hazirdir; ileride toplu siniflandirma ve ozetleme icin doldurulacaktir.
    """

    name = "gemini"
    model = "gemini-stub"

    @property
    def missing_config(self) -> list[str]:
        return ["GEMINI_ILK_SURUMDE_KAPSAM_DISI"]

    def complete(self, request: AIRequest) -> AIResponse:
        from app.ai.base import ProviderNotImplemented

        raise ProviderNotImplemented(self.name)

    def health_check(self) -> tuple[bool, str | None]:
        return False, "Gemini ilk surumde kapsam disi; arayuz hazir."
