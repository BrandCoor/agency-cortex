"""AI ciktilarinin yapilandirilmis semalari.

AI ciktisi serbest metin olarak kabul EDILMEZ. Her cikti burada tanimli
semaya uymak zorundadir; uymayan cikti reddedilir.

`extra="forbid"` ayari semada `additionalProperties: false` uretir; boylece
model semada olmayan alan ekleyemez.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Scene(BaseModel):
    """Senaryonun tek bir sahnesi."""

    model_config = ConfigDict(extra="forbid")

    second_from: int = Field(description="Sahnenin basladigi saniye")
    second_to: int = Field(description="Sahnenin bittigi saniye")
    visual: str = Field(description="Ekranda ne gorunuyor")
    action: str = Field(description="Ne oluyor, kim ne yapiyor")


class ContentScript(BaseModel):
    """Tek bir platform icin icerik senaryosu.

    Alanlar urun tanimindan birebir alinmistir. Hicbiri istege bagli degildir;
    model her alani doldurmak zorundadir.
    """

    model_config = ConfigDict(extra="forbid")

    title: str
    objective: str = Field(description="Bu icerik hangi amaca hizmet ediyor")
    target_metric: str = Field(description="Basari hangi metrikle olculecek")
    platform: str
    format: str = Field(description="reel, carousel, story, short, image, text")
    audience_problem: str = Field(description="Hedef kitlenin hangi sorununa dokunuyor")
    hook: str = Field(description="Ilk 3 saniyedeki dikkat cekici acilis")
    duration_seconds: int
    scene_plan: list[Scene]
    spoken_script: str = Field(description="Konusulan metin")
    on_screen_text: list[str] = Field(description="Ekranda yazacak metinler")
    visual_production_brief: str = Field(description="Cekim icin uretim notu")
    caption: str
    cta: str = Field(description="Izleyiciden istenen eylem")
    alternative_hooks: list[str] = Field(description="Denenebilecek baska acilislar")
    required_assets: list[str] = Field(description="Gereken gorsel/ses/mekan")
    production_difficulty: str = Field(description="kolay, orta, zor")
    brand_risks: list[str] = Field(description="Marka acisindan riskli noktalar")
    claims_to_verify: list[str] = Field(
        description="Dogrulanmasi gereken iddialar. Bos degilse insan kontrolu sart."
    )
    reason_for_recommendation: str = Field(
        description="Bu icerik neden oneriliyor - veriye dayali gerekce"
    )


class ContentScriptBatch(BaseModel):
    """Bir fikrin farkli platformlara uyarlanmis senaryolari.

    Ayni fikir tum platformlara KOPYALANMAZ; her platform icin ayri uyarlama
    uretilir.
    """

    model_config = ConfigDict(extra="forbid")

    idea_title: str
    idea_rationale: str = Field(description="Bu fikir neden secildi")
    scripts: list[ContentScript]


class StrategicInsight(BaseModel):
    """Rapor icin stratejik yorum.

    `claim_type` alani zorunludur: yeterli kanit yoksa model "hipotez"
    demek zorundadir, "kesin neden" yazamaz.
    """

    model_config = ConfigDict(extra="forbid")

    heading: str
    summary: str
    claim_type: str = Field(description="'fact' veya 'hypothesis'")
    evidence: list[str] = Field(description="Hangi verilere dayaniyor")
    uncertainties: list[str] = Field(description="Neleri bilmiyoruz")


class StrategicCommentary(BaseModel):
    """Bir donem raporuna eklenecek AI yorumu."""

    model_config = ConfigDict(extra="forbid")

    overall_assessment: str
    insights: list[StrategicInsight]
    next_period_tests: list[str] = Field(
        description="Gelecek donem denenecek en fazla 3 test"
    )
    confidence: str = Field(description="'low', 'medium' veya 'high'")


def json_schema_for(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic modelinden API'nin bekledigi JSON semasini uretir."""
    return model.model_json_schema()


class TrendFinding(BaseModel):
    """Tek bir trend bulgusu.

    `claim_type` ve `uncertainties` ZORUNLUDUR: yeterli kanit yoksa bulgu
    "kesin" diye yazilmaz, hipotez olarak isaretlenir.
    """

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(description="Trendin kisa adi")
    summary: str = Field(description="Ne oluyor, kim yapiyor, neden yayiliyor")
    relevance_to_brand: str = Field(
        description="Bu marka icin neden onemli veya neden onemli degil"
    )
    platform: str = Field(description="instagram, tiktok, youtube, facebook veya 'genel'")
    claim_type: str = Field(description="'fact' veya 'hypothesis'")
    confidence: str = Field(description="'low', 'medium' veya 'high'")
    source_urls: list[str] = Field(description="Bulgunun dayandigi kaynak adresleri")
    uncertainties: list[str] = Field(description="Neleri bilmiyoruz, neresi belirsiz")


class TrendResearchBatch(BaseModel):
    """Bir arastirma turunun sonucu."""

    model_config = ConfigDict(extra="forbid")

    findings: list[TrendFinding]
    research_note: str = Field(
        description="Arastirmanin kapsami ve sinirlari; neye bakilmadi"
    )
