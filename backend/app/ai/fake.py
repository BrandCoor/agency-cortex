"""Sahte AI saglayicisi.

Gercek API anahtari OLMADAN tum sistemin gelistirilip test edilmesini saglar.
Uretilen cikti semaya UYAR ve her calistirmada AYNIDIR; boylece testler
guvenilir olur.

Bu saglayici uretimde kullanilmaz.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from app.ai.base import AIProvider, AIRequest, AIResponse, AIStatus
from app.ai.pricing import FAKE_MODEL


def _stable_int(*parts: str, low: int, high: int) -> int:
    digest = hashlib.sha256("|".join(parts).encode()).digest()
    return low + (int.from_bytes(digest[:8], "big") % (high - low + 1))


class FakeProvider(AIProvider):
    """Semaya uyan, tekrarlanabilir sahte cikti uretir."""

    name = "fake"
    model = FAKE_MODEL

    def complete(self, request: AIRequest) -> AIResponse:
        veri = self._build(request)
        metin = json.dumps(veri, ensure_ascii=False)

        # Token sayilari gercege yakin olsun diye kabaca tahmin edilir.
        girdi = len(request.system) + len(request.user_content)
        return AIResponse(
            text=metin,
            parsed=veri,
            provider=self.name,
            model=self.model,
            prompt_version=request.prompt_version,
            input_tokens=max(1, girdi // 4),
            output_tokens=max(1, len(metin) // 4),
            estimated_cost_usd=Decimal("0"),
            latency_ms=_stable_int(request.task_type, low=120, high=900),
            status=AIStatus.SUCCEEDED,
            confidence="medium",
        )

    def _build(self, request: AIRequest) -> dict[str, Any]:
        tohum = request.metadata.get("seed", request.task_type)

        if request.task_type == "content_script":
            platformlar = request.metadata.get("platforms", ["instagram"])
            return {
                "idea_title": f"Test fikri ({tohum})",
                "idea_rationale": (
                    "Sahte saglayici tarafindan uretildi - gercek analiz DEGIL."
                ),
                "scripts": [self._script(tohum, p) for p in platformlar],
            }

        if request.task_type == "strategic_commentary":
            return {
                "overall_assessment": (
                    "Sahte saglayici yorumu - gercek stratejik degerlendirme DEGIL."
                ),
                "insights": [
                    {
                        "heading": "Ornek bulgu",
                        "summary": "Bu bir yer tutucudur.",
                        # Sahte veri her zaman hipotezdir; olgu gibi sunulmaz.
                        "claim_type": "hypothesis",
                        "evidence": ["sahte veri"],
                        "uncertainties": ["Gercek veri kullanilmadi."],
                    }
                ],
                "next_period_tests": ["Gercek AI saglayicisini baglayin."],
                "confidence": "low",
            }

        if request.task_type == "trend_research":
            return {
                "findings": [
                    {
                        "topic": f"Ornek trend ({tohum})",
                        "summary": (
                            "Sahte saglayici tarafindan uretildi - gercek "
                            "arastirma DEGIL."
                        ),
                        "relevance_to_brand": (
                            "Ornek veridir; bu markayla ilgisi yoktur."
                        ),
                        "platform": "genel",
                        # Sahte veri ASLA 'fact' degildir.
                        "claim_type": "hypothesis",
                        "confidence": "low",
                        "source_urls": [],
                        "uncertainties": [
                            "Gercek kaynak taranmadi; ornek veridir.",
                        ],
                    }
                ],
                "research_note": (
                    "Ornek veri modu: hicbir kaynak taranmadi. Gercek "
                    "arastirma icin AI saglayicisini baglayin."
                ),
            }

        # BURAYA DUSMEK BIR HATADIR.
        #
        # Onceden burasi {"result": "sahte-cikti-..."} donuyordu. Bu deger
        # HICBIR semaya uymaz; is akisi "AI ciktisi beklenen yapiya uymadi"
        # diye iki kez deneyip HATA veriyordu. Yani ornek veri modunda o is
        # akisi HIC calismiyordu ve sebebi anlasilmiyordu.
        #
        # Sessizce uydurma bir sozluk dondurmek daha da kotu olurdu: hata
        # gecikir ve baska yerde ortaya cikardi. Bu yuzden ACIKCA hata.
        raise NotImplementedError(
            f"Ornek veri saglayicisi '{request.task_type}' gorev turu icin "
            "cikti uretmiyor. Bu gorev turu eklendiginde fake.py de "
            "guncellenmelidir."
        )

    def _script(self, tohum: str, platform: str) -> dict[str, Any]:
        sure = _stable_int(tohum, platform, low=15, high=45)
        return {
            "title": f"{platform} icin test senaryosu",
            "objective": "Marka bilinirligi",
            "target_metric": "reach",
            "platform": platform,
            "format": "reel" if platform in ("instagram", "tiktok") else "image",
            "audience_problem": "Ornek bir kitle sorunu",
            "hook": "Ilk uc saniyede dikkat ceken ornek acilis",
            "duration_seconds": sure,
            "scene_plan": [
                {"second_from": 0, "second_to": 3, "visual": "Yakin plan",
                 "action": "Acilis repligi"},
                {"second_from": 3, "second_to": sure, "visual": "Genel plan",
                 "action": "Anlatim ve kapanis"},
            ],
            "spoken_script": "Ornek konusma metni.",
            "on_screen_text": ["Ornek ekran yazisi"],
            "visual_production_brief": "Dogal isik, sabit kamera.",
            "caption": "Ornek aciklama metni",
            "cta": "Profildeki baglantiya goz atin",
            "alternative_hooks": ["Ikinci acilis onerisi"],
            "required_assets": ["Urun gorseli"],
            "production_difficulty": "kolay",
            "brand_risks": [],
            # Sahte cikti oldugu HER ZAMAN belirtilir.
            "claims_to_verify": ["Bu icerik sahte saglayici tarafindan uretildi."],
            "reason_for_recommendation": "Sahte saglayici - veriye dayali gerekce yok.",
        }

    def health_check(self) -> tuple[bool, str | None]:
        return True, "Sahte saglayici calisiyor (gercek AI DEGIL)."
