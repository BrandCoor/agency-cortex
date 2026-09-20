"""AI saglayicilarinin ortak arayuzu.

TASARIM: Platform adaptorleriyle ayni mantik. Bir saglayici yapamadigi isi
"yapiyormus gibi" gostermez; ayarlari eksikse hicbir yetenek bildirmez.

GOREV DAGILIMI (urun karari):
- Claude  : marka dili, icerik senaryosu, stratejik yorum
- Manus   : cok adimli arastirma, rakip ve trend
- Gemini  : ileride toplu siniflandirma (simdilik yok)
- Kod     : metrik, oran, tarih, KPI hesaplari (AI KULLANILMAZ)
"""

from __future__ import annotations

import enum
import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


class AIProviderError(Exception):
    """AI katmanindaki tum hatalarin atasi."""


class ProviderNotConfigured(AIProviderError):
    """Saglayici ayarlari eksik; canli cagri yapilamaz."""

    def __init__(self, provider: str, missing: list[str]) -> None:
        super().__init__(
            f"'{provider}' saglayicisi icin su ayarlar eksik: {', '.join(missing)}"
        )
        self.provider = provider
        self.missing = missing


class ProviderNotImplemented(AIProviderError):
    """Saglayici henuz gelistirilmedi."""

    def __init__(self, provider: str) -> None:
        super().__init__(
            f"'{provider}' saglayicisi henuz gelistirilmedi. Bu saglayiciyla "
            "istek gonderilemez."
        )
        self.provider = provider


class SchemaValidationFailed(AIProviderError):
    """AI ciktisi beklenen yapiya uymadi.

    AI ciktisi DOGRUDAN DOGRU KABUL EDILMEZ. Yapilandirilmis sema ile
    dogrulanir; uymuyorsa sinirli sayida tekrar istenir, sonra hata verilir.
    """

    def __init__(self, detail: str, *, attempts: int) -> None:
        super().__init__(
            f"AI ciktisi {attempts} denemede de beklenen yapiya uymadi: {detail}"
        )
        self.detail = detail
        self.attempts = attempts


class AIRateLimited(AIProviderError):
    def __init__(self, provider: str, retry_after_seconds: int | None = None) -> None:
        super().__init__(f"'{provider}' istek sinirina takildi.")
        self.provider = provider
        self.retry_after_seconds = retry_after_seconds


class AITimeout(AIProviderError):
    pass


class AIStatus(str, enum.Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class AIRequest:
    """Bir AI cagrisinin girdisi.

    `prompt_version`: istemin surumu. Cikti kalitesi degistiginde hangi istem
    surumunun kullanildigini bilmek sart; bu alan zorunludur.
    """

    task_type: str
    prompt_version: str
    system: str
    user_content: str
    json_schema: dict[str, Any] | None = None
    max_tokens: int = 16000
    effort: str = "high"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AIResponse:
    """Bir AI cagrisinin sonucu ve muhasebesi."""

    text: str
    parsed: dict[str, Any] | None
    provider: str
    model: str
    prompt_version: str
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: Decimal | None
    latency_ms: int
    status: AIStatus
    error_code: str | None = None
    confidence: str | None = None

    @property
    def output_hash(self) -> str:
        """Ciktinin parmak izi.

        Ayni ciktinin tekrar uretildigini anlamak ve icerik tekrarini
        engellemek icin kullanilir.
        """
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def canonical_hash(data: Any) -> str:
    """Yapilandirilmis veri icin kararli parmak izi."""
    metin = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(metin.encode("utf-8")).hexdigest()


class AIProvider(ABC):
    """Tum AI saglayicilarinin uymasi gereken arayuz."""

    name: str
    #: Bu saglayicinin kullandigi model kimligi
    model: str

    @property
    def is_configured(self) -> bool:
        """Canli cagri yapilabilir mi?"""
        return not self.missing_config

    @property
    def missing_config(self) -> list[str]:
        """Eksik ayarlarin listesi. Bos ise saglayici hazirdir."""
        return []

    @abstractmethod
    def complete(self, request: AIRequest) -> AIResponse:
        """Istegi gonderir ve sonucu doner.

        Hata durumunda AIProviderError turevi firlatir; sessizce bos
        sonuc DONMEZ.
        """

    @abstractmethod
    def health_check(self) -> tuple[bool, str | None]:
        """(calisir_mi, aciklama)"""
