"""Icerik senaryosu uretimi.

AKIS:
1. Marka hafizasi, aktif kampanya, hedef KPI ve gecmis performans okunur
2. Bu baglam KISA bir ozete donusturulur (ham API yaniti AI'ya GONDERILMEZ)
3. Claude'dan yapilandirilmis senaryo istenir
4. Cikti semayla dogrulanir
5. Yasakli ifadeler kontrol edilir
6. Senaryolar INSAN ONAYI bekler durumda kaydedilir

ONEMLI: Claude'a ham sosyal medya API yanitlari gonderilmez. Once burada
deterministik ve kisa bir ozet cikarilir; Claude yalnizca gerekli baglami alir.
Bu hem maliyeti dusurur hem de musteri verisinin gereksiz yayilmasini onler.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.base import canonical_hash
from app.ai.schemas import ContentScriptBatch
from app.core.logging_config import get_logger
from app.models.brand import Brand, BrandGuideline, Campaign
from app.models.content import ContentIdea, ContentScript
from app.models.enums import ContentStatus, MediaType, Platform
from app.models.identity import Workspace
from app.services.ai_runner import RunResult, run_ai_task
from app.services.reports import collect_performance

log = get_logger("content")

PROMPT_VERSION = "content_script.v1"

SYSTEM_PROMPT = """Sen bir sosyal medya ajansinin kidemli icerik stratejistisin.

GOREVIN: Verilen marka baglamina uygun, platforma ozel icerik senaryolari uretmek.

KESIN KURALLAR:
1. Ayni fikri tum platformlara KOPYALAMA. Her platform icin ayri uyarlama uret.
2. Yasakli ifadeleri ASLA kullanma.
3. Dogrulanmasi gereken her iddiayi `claims_to_verify` alanina yaz. Emin
   olmadigin bir sey soyluyorsan bunu belirt.
4. Marka acisindan riskli bir sey oneriyorsan `brand_risks` alanina yaz.
5. `reason_for_recommendation` alaninda VERIYE DAYALI gerekce yaz. Veri yoksa
   "yeterli veri yok" de; uydurma.
6. Abartili vaat, saglik iddiasi veya kanitlanmamis ustunluk iddiasi kurma.
7. Her senaryo tek basina uretilebilir olmali; belirsiz birakma."""


@dataclass
class BrandContext:
    """AI'ya gonderilecek kisa marka ozeti."""

    brand_name: str
    sector: str | None = None
    tone_of_voice: str | None = None
    target_audience: str | None = None
    forbidden_phrases: list[str] = field(default_factory=list)
    preferred_phrases: list[str] = field(default_factory=list)
    kpi_targets: dict = field(default_factory=dict)
    active_campaign: str | None = None
    campaign_objective: str | None = None
    top_performers: list[str] = field(default_factory=list)
    weak_performers: list[str] = field(default_factory=list)
    data_note: str | None = None

    def to_prompt(self) -> str:
        """Baglami sade metne cevirir."""
        satirlar = [f"MARKA: {self.brand_name}"]
        if self.sector:
            satirlar.append(f"SEKTOR: {self.sector}")
        if self.tone_of_voice:
            satirlar.append(f"MARKA DILI: {self.tone_of_voice}")
        if self.target_audience:
            satirlar.append(f"HEDEF KITLE: {self.target_audience}")
        if self.forbidden_phrases:
            satirlar.append(
                "YASAKLI IFADELER (asla kullanma): " + ", ".join(self.forbidden_phrases)
            )
        if self.preferred_phrases:
            satirlar.append("TERCIH EDILEN IFADELER: " + ", ".join(self.preferred_phrases))
        if self.kpi_targets:
            satirlar.append(f"HEDEF KPI: {self.kpi_targets}")
        if self.active_campaign:
            satirlar.append(f"AKTIF KAMPANYA: {self.active_campaign}")
            if self.campaign_objective:
                satirlar.append(f"KAMPANYA AMACI: {self.campaign_objective}")

        if self.top_performers:
            satirlar.append("SON DONEMDE IYI CALISAN ICERIKLER:")
            satirlar += [f"  - {b}" for b in self.top_performers]
        if self.weak_performers:
            satirlar.append("SON DONEMDE ZAYIF KALAN ICERIKLER:")
            satirlar += [f"  - {b}" for b in self.weak_performers]

        # Veri yoksa bu ACIKCA soylenir; model veri varmis gibi davranmasin.
        if self.data_note:
            satirlar.append(f"VERI DURUMU: {self.data_note}")

        return "\n".join(satirlar)


def build_context(
    db: Session, *, workspace_id: uuid.UUID, brand: Brand, lookback_days: int = 30
) -> BrandContext:
    """Marka hafizasi ve gecmis performanstan kisa bir ozet cikarir."""
    baglam = BrandContext(brand_name=brand.name, sector=brand.sector)

    kilavuz = db.execute(
        select(BrandGuideline).where(
            BrandGuideline.workspace_id == workspace_id,
            BrandGuideline.brand_id == brand.id,
        )
    ).scalars().first()

    if kilavuz is not None:
        baglam.tone_of_voice = kilavuz.tone_of_voice
        baglam.target_audience = kilavuz.target_audience
        baglam.forbidden_phrases = list(kilavuz.forbidden_phrases or [])
        baglam.preferred_phrases = list(kilavuz.preferred_phrases or [])
        baglam.kpi_targets = dict(kilavuz.kpi_targets or {})

    kampanya = db.execute(
        select(Campaign).where(
            Campaign.workspace_id == workspace_id,
            Campaign.brand_id == brand.id,
            Campaign.status == ContentStatus.APPROVED,
        ).order_by(Campaign.starts_on.desc())
    ).scalars().first()

    if kampanya is not None:
        baglam.active_campaign = kampanya.name
        baglam.campaign_objective = kampanya.objective

    # Gecmis performans: ham veri DEGIL, yalnizca kisa ozet.
    bitis = datetime.now(UTC)
    basla = bitis - timedelta(days=lookback_days)
    icerikler = collect_performance(
        db, workspace_id=workspace_id, start=basla, end=bitis
    )
    olculebilir = [i for i in icerikler if i.engagement is not None]

    if not icerikler:
        baglam.data_note = (
            f"Son {lookback_days} gunde yayinlanmis icerik yok. "
            "Onerileri gecmis performansa dayandirma."
        )
    elif not olculebilir:
        baglam.data_note = (
            "Icerikler var ancak olcum verisi alinamadi. "
            "Performans yorumu yapma."
        )
    else:
        sirali = sorted(olculebilir, key=lambda i: i.engagement or 0, reverse=True)
        baglam.top_performers = [
            f"{i.media_type} - {i.short_label} ({i.engagement:,.0f} etkilesim)"
            for i in sirali[:3]
        ]
        if len(sirali) > 3:
            baglam.weak_performers = [
                f"{i.media_type} - {i.short_label} ({i.engagement:,.0f} etkilesim)"
                for i in sirali[-2:]
            ]
        if len(olculebilir) < 5:
            baglam.data_note = (
                f"Yalnizca {len(olculebilir)} icerikte olcum var. "
                "Kesin sonuc cikarma; onerileri hipotez olarak sun."
            )

    return baglam


def check_forbidden(text: str, forbidden: list[str]) -> list[str]:
    """Metinde yasakli ifade var mi? Bulunanlari doner."""
    kucuk = text.lower()
    return [f for f in forbidden if f.lower() in kucuk]


@dataclass
class GenerationResult:
    idea: ContentIdea
    scripts: list[ContentScript]
    ai_task_id: uuid.UUID
    violations: list[str]
    was_duplicate: bool = False


def generate_scripts(
    db: Session,
    *,
    workspace: Workspace,
    brand: Brand,
    platforms: list[Platform],
    brief: str,
    provider=None,
) -> GenerationResult:
    """Bir fikir icin platforma ozel senaryolar uretir.

    Ayni fikir daha once uretilmisse yenisi URETILMEZ.
    """
    baglam = build_context(db, workspace_id=workspace.id, brand=brand)

    kullanici_istemi = "\n\n".join([
        baglam.to_prompt(),
        f"ISTENEN: {brief}",
        "HEDEF PLATFORMLAR: " + ", ".join(p.value for p in platforms),
        f"Her platform icin AYRI uyarlama uret. Toplam {len(platforms)} senaryo bekleniyor.",
    ])

    sonuc: RunResult = run_ai_task(
        db,
        workspace=workspace,
        task_type="content_script",
        prompt_version=PROMPT_VERSION,
        system=SYSTEM_PROMPT,
        user_content=kullanici_istemi,
        output_model=ContentScriptBatch,
        metadata={"platforms": [p.value for p in platforms], "brand": brand.name},
        provider=provider,
    )

    veri = ContentScriptBatch.model_validate(sonuc.parsed)

    # Ayni fikrin tekrar uretilmesini engelle.
    imza = canonical_hash({"brand": str(brand.id), "title": veri.idea_title})
    mevcut = db.execute(
        select(ContentIdea).where(
            ContentIdea.workspace_id == workspace.id,
            ContentIdea.idea_fingerprint == imza,
        )
    ).scalar_one_or_none()

    if mevcut is not None:
        log.info("icerik_fikri_zaten_var", workspace_id=str(workspace.id), idea_id=str(mevcut.id))
        var_olan = db.execute(
            select(ContentScript).where(ContentScript.idea_id == mevcut.id)
        ).scalars().all()
        return GenerationResult(
            idea=mevcut, scripts=list(var_olan), ai_task_id=sonuc.task_id,
            violations=[], was_duplicate=True,
        )

    fikir = ContentIdea(
        workspace_id=workspace.id,
        brand_id=brand.id,
        title=veri.idea_title,
        reason_for_recommendation=veri.idea_rationale,
        status=ContentStatus.DRAFT,
        idea_fingerprint=imza,
    )
    db.add(fikir)
    db.flush()

    ihlaller: list[str] = []
    kayitlar: list[ContentScript] = []

    for s in veri.scripts:
        # Yasakli ifade kontrolu - AI kurala uymamis olabilir.
        metin = " ".join([s.hook, s.spoken_script, s.caption, s.cta])
        bulunanlar = check_forbidden(metin, baglam.forbidden_phrases)
        if bulunanlar:
            ihlaller.extend(bulunanlar)

        riskler = list(s.brand_risks)
        if bulunanlar:
            riskler.append(
                "Yasakli ifade tespit edildi: " + ", ".join(bulunanlar)
            )

        kayit = ContentScript(
            workspace_id=workspace.id,
            idea_id=fikir.id,
            platform=Platform(s.platform) if s.platform in Platform._value2member_map_
            else Platform.INSTAGRAM,
            format=MediaType(s.format) if s.format in MediaType._value2member_map_
            else MediaType.OTHER,
            hook=s.hook,
            duration_seconds=s.duration_seconds,
            scene_plan=[sc.model_dump() for sc in s.scene_plan],
            spoken_script=s.spoken_script,
            on_screen_text=list(s.on_screen_text),
            visual_production_brief=s.visual_production_brief,
            caption=s.caption,
            cta=s.cta,
            alternative_hooks=list(s.alternative_hooks),
            required_assets=list(s.required_assets),
            production_difficulty=s.production_difficulty,
            brand_risks=riskler,
            claims_to_verify=list(s.claims_to_verify),
            status=ContentStatus.DRAFT,
            # Ilk surumde HER ZAMAN True. Insan onayi olmadan yayin yok.
            human_approval_required=True,
            ai_run_id=sonuc.task_id,
        )
        db.add(kayit)
        kayitlar.append(kayit)

    db.flush()

    log.info(
        "senaryolar_uretildi",
        workspace_id=str(workspace.id),
        idea_id=str(fikir.id),
        script_count=len(kayitlar),
        violations=len(ihlaller),
        cost_usd=str(sonuc.total_cost_usd),
    )

    return GenerationResult(
        idea=fikir, scripts=kayitlar, ai_task_id=sonuc.task_id, violations=ihlaller
    )
