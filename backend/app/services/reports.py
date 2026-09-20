"""Gunluk ve haftalik rapor uretimi.

KURALLAR:
1. Yeterli kanit yoksa KESIN NEDEN yazilmaz. Nedensel yorumlar "hipotez"
   olarak isaretlenir (`claim_type="hypothesis"`).
2. Eksik veya guvenilmez veriler raporda ACIKCA belirtilir; gizlenmez.
3. Ayni donemin raporu iki kez uretilmez (veritabani kisiti + kontrol).
4. Rapor uretimi yapay zeka KULLANMAZ. Burasi deterministik hesaptir;
   AI yorumu Asama 5'te ayri bir katman olarak eklenecektir.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models.enums import ContentStatus, ReportPeriod
from app.models.reporting import Report, ReportSection
from app.models.social import MediaMetricsNormalized, PlatformMedia
from app.services import anomalies as anom
from app.services.kpi import (
    ENGAGEMENT_COMPONENTS,
    Comparison,
    DataQuality,
    Direction,
    MetricSet,
    RankedItem,
    compare,
    engagement_rate,
    engagement_total,
    rank,
    to_float,
    total,
)

log = get_logger("reports")

# Bir donem hakkinda nedensel yorum yapabilmek icin gereken en az icerik sayisi.
# Bunun altinda bulgular yalnizca hipotez olarak sunulur.
MIN_ITEMS_FOR_CAUSAL_CLAIM = 5


@dataclass
class PeriodWindow:
    """Bir rapor donemi ve onunla karsilastirilacak onceki donem."""

    start: date
    end: date
    previous_start: date
    previous_end: date

    @property
    def start_dt(self) -> datetime:
        return datetime.combine(self.start, time.min)

    @property
    def end_dt(self) -> datetime:
        return datetime.combine(self.end, time.max)

    @property
    def previous_start_dt(self) -> datetime:
        return datetime.combine(self.previous_start, time.min)

    @property
    def previous_end_dt(self) -> datetime:
        return datetime.combine(self.previous_end, time.max)


def build_window(period: ReportPeriod, reference: date) -> PeriodWindow:
    """Donem araligini ve karsilastirma araligini hesaplar.

    `reference`: raporun uretildigi gun. Gunluk raporda BIR ONCEKI gun
    raporlanir; bugun henuz tamamlanmadigi icin yarim veri raporlanmaz.
    """
    if period is ReportPeriod.DAILY:
        bitis = reference - timedelta(days=1)
        return PeriodWindow(
            start=bitis, end=bitis,
            previous_start=bitis - timedelta(days=1),
            previous_end=bitis - timedelta(days=1),
        )
    if period is ReportPeriod.WEEKLY:
        bitis = reference - timedelta(days=1)
        baslangic = bitis - timedelta(days=6)
        return PeriodWindow(
            start=baslangic, end=bitis,
            previous_start=baslangic - timedelta(days=7),
            previous_end=baslangic - timedelta(days=1),
        )
    # Aylik
    bitis = reference - timedelta(days=1)
    baslangic = bitis - timedelta(days=29)
    return PeriodWindow(
        start=baslangic, end=bitis,
        previous_start=baslangic - timedelta(days=30),
        previous_end=baslangic - timedelta(days=1),
    )


@dataclass
class ContentPerformance:
    """Tek bir icerigin donem icindeki performansi."""

    media_id: uuid.UUID
    external_id: str
    media_type: str
    caption: str | None
    published_at: datetime | None
    metrics: MetricSet = field(default_factory=MetricSet)

    @property
    def engagement(self) -> float | None:
        return engagement_total(self.metrics)

    @property
    def rate(self) -> float | None:
        return engagement_rate(self.metrics)

    @property
    def short_label(self) -> str:
        if self.caption:
            return self.caption[:60] + ("..." if len(self.caption) > 60 else "")
        return self.external_id


def collect_performance(
    db: Session, *, workspace_id: uuid.UUID, start: datetime, end: datetime
) -> list[ContentPerformance]:
    """Donemde yayinlanmis iceriklerin olculerini toplar."""
    medyalar = db.execute(
        select(PlatformMedia).where(
            PlatformMedia.workspace_id == workspace_id,
            PlatformMedia.published_at >= start,
            PlatformMedia.published_at <= end,
        )
    ).scalars().all()

    if not medyalar:
        return []

    kimlikler = [m.id for m in medyalar]
    olcumler = db.execute(
        select(MediaMetricsNormalized).where(
            MediaMetricsNormalized.workspace_id == workspace_id,
            MediaMetricsNormalized.media_id.in_(kimlikler),
        )
    ).scalars().all()

    havuz: dict[uuid.UUID, MetricSet] = {}
    for o in olcumler:
        havuz.setdefault(o.media_id, MetricSet()).values[o.metric_name] = (
            to_float(o.metric_value) or 0.0
        )

    return [
        ContentPerformance(
            media_id=m.id,
            external_id=m.external_id,
            media_type=m.media_type.value,
            caption=m.caption,
            published_at=m.published_at,
            metrics=havuz.get(m.id, MetricSet()),
        )
        for m in medyalar
    ]


# Her icerikte bulunmasi beklenen metrikler.
EXPECTED_METRICS = (*ENGAGEMENT_COMPONENTS, "reach")


def assess_quality(items: Sequence[ContentPerformance]) -> DataQuality:
    """Raporun dayandigi verinin saglamligini olcer.

    Beklenen metrikler BURADA acikca istenir. Daha once bu liste baska bir
    fonksiyonun yan etkisiyle doluyordu; cagri sirasi degistiginde eksikler
    sessizce bos gorunuyordu. Artik bu fonksiyon kendi kendine yeterlidir.
    """
    kalite = DataQuality(expected_items=len(items))
    for i in items:
        if i.metrics.values:
            kalite.items_with_data += 1
        i.metrics.require(*EXPECTED_METRICS)
        kalite.record_missing(i.metrics.missing)

    if kalite.expected_items == 0:
        kalite.notes.append("Bu donemde yayinlanmis icerik bulunamadi.")
    elif kalite.items_with_data == 0:
        kalite.notes.append(
            "Icerikler var ancak hicbirinin olcum verisi alinamadi. "
            "Hesap baglantisini kontrol edin."
        )
    elif not kalite.is_sufficient:
        kalite.notes.append(
            f"Iceriklerin yalnizca {kalite.items_with_data}/{kalite.expected_items} "
            "tanesinde olcum verisi var. Yorumlar hipotez olarak sunuldu."
        )

    for ad, sayi in sorted(kalite.missing_metrics.items()):
        kalite.notes.append(f"'{ad}' metrigi {sayi} icerikte eksik.")

    return kalite


@dataclass
class SectionDraft:
    heading: str
    body: str | None
    data: dict
    claim_type: str = "fact"


def _summary_section(
    items: Sequence[ContentPerformance],
    onceki: Sequence[ContentPerformance],
    period: ReportPeriod,
) -> SectionDraft:
    simdi_etkilesim = total([i.engagement for i in items])
    onceki_etkilesim = total([i.engagement for i in onceki])
    simdi_erisim = total([i.metrics.get("reach") for i in items])
    onceki_erisim = total([i.metrics.get("reach") for i in onceki])

    k_etkilesim = compare(simdi_etkilesim, onceki_etkilesim)
    k_erisim = compare(simdi_erisim, onceki_erisim)

    donem_adi = {"daily": "gun", "weekly": "hafta", "monthly": "ay"}[period.value]

    satirlar = [
        f"Bu {donem_adi} {len(items)} icerik yayinlandi "
        f"(onceki {donem_adi}: {len(onceki)}).",
        _describe("Toplam etkilesim", k_etkilesim),
        _describe("Toplam erisim", k_erisim),
    ]

    return SectionDraft(
        heading="Donem ozeti",
        body="\n".join(satirlar),
        data={
            "icerik_sayisi": len(items),
            "onceki_icerik_sayisi": len(onceki),
            "toplam_etkilesim": simdi_etkilesim,
            "toplam_erisim": simdi_erisim,
            "etkilesim_degisimi": _comparison_dict(k_etkilesim),
            "erisim_degisimi": _comparison_dict(k_erisim),
        },
    )


def _describe(ad: str, k: Comparison) -> str:
    """Karsilastirmayi sade Turkce ile anlatir."""
    if not k.is_reliable:
        if k.current is None:
            return f"{ad}: veri yok."
        return f"{ad}: {k.current:,.0f} (karsilastirma icin onceki donem verisi yok)."

    if k.change_percent is None:
        return f"{ad}: {k.current:,.0f} (onceki donem 0 oldugu icin yuzde hesaplanamadi)."

    yuzde = abs(k.change_percent) * 100
    if k.direction is Direction.FLAT:
        return f"{ad}: {k.current:,.0f} - onceki donemle aynı seviyede."
    yon = "artti" if k.direction is Direction.UP else "azaldi"
    return f"{ad}: {k.current:,.0f} - onceki doneme gore %{yuzde:.1f} {yon}."


def _comparison_dict(k: Comparison) -> dict:
    return {
        "simdi": k.current,
        "onceki": k.previous,
        "fark": k.change_absolute,
        "yuzde": k.change_percent,
        "yon": k.direction.value,
        "guvenilir": k.is_reliable,
    }


def _best_worst_section(items: Sequence[ContentPerformance], kalite: DataQuality) -> SectionDraft:
    olculebilir = [i for i in items if i.engagement is not None]

    if not olculebilir:
        return SectionDraft(
            heading="En iyi ve en zayif icerikler",
            body="Siralama yapilamadi: iceriklerin olcum verisi yok.",
            data={"en_iyi": [], "en_zayif": []},
        )

    siralanabilir = [
        RankedItem(key=str(i.media_id), score=i.engagement or 0.0, label=i.short_label)
        for i in olculebilir
    ]
    en_iyi = rank(siralanabilir, top=3)
    en_zayif = rank(siralanabilir, top=3, ascending=True)

    satirlar = ["En iyi 3:"]
    satirlar += [f"  {n+1}. {r.label} - {r.score:,.0f} etkilesim"
                 for n, r in enumerate(en_iyi)]
    if len(olculebilir) > 3:
        satirlar.append("En zayif 3:")
        satirlar += [f"  {n+1}. {r.label} - {r.score:,.0f} etkilesim"
                     for n, r in enumerate(en_zayif)]

    # Kanit yetersizse bu bir SIRALAMA'dir, "neden" degildir.
    tur = "fact" if kalite.is_sufficient and len(olculebilir) >= MIN_ITEMS_FOR_CAUSAL_CLAIM else "hypothesis"
    if tur == "hypothesis":
        satirlar.append(
            "\nNot: Icerik sayisi az oldugu icin bu siralama bir egilim gostergesi "
            "olarak degerlendirilmelidir, kesin bir sonuc degildir."
        )

    return SectionDraft(
        heading="En iyi ve en zayif icerikler",
        body="\n".join(satirlar),
        data={
            "en_iyi": [{"id": r.key, "etiket": r.label, "skor": r.score} for r in en_iyi],
            "en_zayif": [{"id": r.key, "etiket": r.label, "skor": r.score} for r in en_zayif],
        },
        claim_type=tur,
    )


def _format_section(items: Sequence[ContentPerformance], kalite: DataQuality) -> SectionDraft:
    """Format bazinda performans (Reel, carousel, gorsel...)."""
    gruplar: dict[str, list[float]] = {}
    for i in items:
        if i.engagement is not None:
            gruplar.setdefault(i.media_type, []).append(i.engagement)

    if not gruplar:
        return SectionDraft(
            heading="Format analizi",
            body="Format karsilastirmasi icin yeterli olcum verisi yok.",
            data={},
        )

    ozet = {
        ad: {"adet": len(v), "ortalama_etkilesim": sum(v) / len(v)}
        for ad, v in gruplar.items()
    }
    sirali = sorted(ozet.items(), key=lambda kv: kv[1]["ortalama_etkilesim"], reverse=True)

    satirlar = [
        f"{ad}: {d['adet']} icerik, ortalama {d['ortalama_etkilesim']:,.0f} etkilesim"
        for ad, d in sirali
    ]

    # Her formatta en az 3 ornek yoksa karsilastirma kesin sayilmaz.
    yeterli = all(d["adet"] >= 3 for _, d in sirali) and len(sirali) > 1
    tur = "fact" if (yeterli and kalite.is_sufficient) else "hypothesis"
    if tur == "hypothesis":
        satirlar.append(
            "\nNot: Ornek sayisi az. Formatlar arasi fark tesadufi olabilir; "
            "kesin sonuc icin daha fazla veri gerekir."
        )

    return SectionDraft(
        heading="Format analizi",
        body="\n".join(satirlar),
        data={"formatlar": ozet},
        claim_type=tur,
    )


def _anomaly_section(
    items: Sequence[ContentPerformance], gecmis: Sequence[Sequence[ContentPerformance]]
) -> SectionDraft:
    """Onceki donemlere gore anormal degisimleri bulur."""
    simdi_erisim = total([i.metrics.get("reach") for i in items])
    gecmis_erisim = [
        d for d in (total([i.metrics.get("reach") for i in donem]) for donem in gecmis)
        if d is not None
    ]

    bulunanlar = anom.detect_many({"Erisim": (gecmis_erisim, simdi_erisim)})

    if not bulunanlar:
        return SectionDraft(
            heading="Anormal degisimler",
            body="Dikkat gerektiren anormal bir degisim tespit edilmedi.",
            data={"anomaliler": []},
        )

    return SectionDraft(
        heading="Anormal degisimler",
        body="\n".join(a.explanation for a in bulunanlar),
        data={
            "anomaliler": [
                {
                    "metrik": a.metric_name,
                    "deger": a.value,
                    "beklenen": a.expected_median,
                    "yon": a.direction,
                    "onem": a.severity.value,
                }
                for a in bulunanlar
            ]
        },
        # Anomali TESPITI bir olgudur; SEBEBI hipotezdir.
        claim_type="fact",
    )


def _quality_section(kalite: DataQuality) -> SectionDraft:
    kapsam = kalite.coverage
    if not kalite.notes:
        govde = "Veri eksigi tespit edilmedi."
    else:
        govde = "\n".join(f"- {n}" for n in kalite.notes)

    return SectionDraft(
        heading="Veri kalitesi ve eksikler",
        body=govde,
        data={
            "beklenen_icerik": kalite.expected_items,
            "verisi_olan_icerik": kalite.items_with_data,
            "kapsam": kapsam,
            "yeterli_mi": kalite.is_sufficient,
            "eksik_metrikler": kalite.missing_metrics,
        },
    )


def _actions_section(
    items: Sequence[ContentPerformance], kalite: DataQuality
) -> SectionDraft:
    """En fazla UC aksiyon onerir.

    Uzun listeler uygulanmaz. Uc madde, uzerinde durulabilir bir sayidir.
    """
    oneriler: list[str] = []

    if kalite.expected_items == 0:
        oneriler.append("Bu donemde icerik yayinlanmamis. Yayin takvimini gozden gecirin.")
    if kalite.items_with_data == 0 and kalite.expected_items > 0:
        oneriler.append(
            "Olcum verisi alinamiyor. Hesap baglantisini ve hesabin "
            "profesyonel oldugunu kontrol edin."
        )
    if kalite.missing_metrics:
        eksik = ", ".join(sorted(kalite.missing_metrics)[:3])
        oneriler.append(f"Su metrikler eksik geliyor: {eksik}. Izinleri kontrol edin.")

    olculebilir = [i for i in items if i.engagement is not None]
    if olculebilir and len(olculebilir) >= 2:
        en_iyi = max(olculebilir, key=lambda i: i.engagement or 0)
        oneriler.append(
            f"'{en_iyi.short_label}' bu donemin one cikan icerigi. "
            f"Benzer bir format denenebilir."
        )

    return SectionDraft(
        heading="Bu donemin onerileri",
        body="\n".join(f"{n+1}. {o}" for n, o in enumerate(oneriler[:3]))
             or "Oneri uretmek icin yeterli veri yok.",
        data={"oneriler": oneriler[:3]},
        # Oneriler kanit degil, degerlendirmedir.
        claim_type="hypothesis",
    )


# --- Ana giris noktasi -------------------------------------------------------

def generate_report(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    period: ReportPeriod,
    reference: date,
    force: bool = False,
) -> Report:
    """Donem raporunu uretir ve kaydeder.

    Ayni donem icin rapor zaten varsa yenisi URETILMEZ; mevcut olan doner.
    (`force=True` ile mevcut rapor yenilenir.)
    """
    pencere = build_window(period, reference)

    mevcut = db.execute(
        select(Report).where(
            Report.workspace_id == workspace_id,
            Report.period == period,
            Report.period_start == pencere.start,
        )
    ).scalar_one_or_none()

    if mevcut is not None and not force:
        log.info(
            "rapor_zaten_var",
            workspace_id=str(workspace_id),
            period=period.value,
            period_start=pencere.start.isoformat(),
        )
        return mevcut

    simdi = collect_performance(
        db, workspace_id=workspace_id, start=pencere.start_dt, end=pencere.end_dt
    )
    onceki = collect_performance(
        db, workspace_id=workspace_id,
        start=pencere.previous_start_dt, end=pencere.previous_end_dt,
    )

    # Anomali icin daha uzun gecmis gerekir.
    gecmis_donemler: list[list[ContentPerformance]] = []
    gun_sayisi = (pencere.end - pencere.start).days + 1
    for k in range(1, 8):
        bit = pencere.start - timedelta(days=gun_sayisi * (k - 1) + 1)
        bas = bit - timedelta(days=gun_sayisi - 1)
        gecmis_donemler.append(
            collect_performance(
                db, workspace_id=workspace_id,
                start=datetime.combine(bas, time.min),
                end=datetime.combine(bit, time.max),
            )
        )

    kalite = assess_quality(simdi)

    bolumler = [
        _summary_section(simdi, onceki, period),
        _best_worst_section(simdi, kalite),
        _format_section(simdi, kalite),
        _anomaly_section(simdi, gecmis_donemler),
        _actions_section(simdi, kalite),
        _quality_section(kalite),
    ]

    baslik = {
        ReportPeriod.DAILY: f"Gunluk rapor - {pencere.start.isoformat()}",
        ReportPeriod.WEEKLY: f"Haftalik rapor - {pencere.start.isoformat()} / {pencere.end.isoformat()}",
        ReportPeriod.MONTHLY: f"Aylik rapor - {pencere.start.isoformat()} / {pencere.end.isoformat()}",
    }[period]

    varsayimlar = [
        "Veriler platformun bildirdigi degerlerdir; platform sonradan duzeltme yapabilir.",
        "Karsilastirmalar bir onceki esit uzunluktaki donemle yapilmistir.",
    ]
    if not kalite.is_sufficient:
        varsayimlar.append(
            "Veri kapsami dusuk oldugu icin nedensel yorum yapilmamistir."
        )

    if mevcut is not None:
        rapor = mevcut
        rapor.title = baslik
        rapor.data_quality_notes = kalite.notes
        rapor.assumptions = varsayimlar
        for eski in list(rapor.__dict__.get("_sections_cache", [])):
            db.delete(eski)
        for eski in db.execute(
            select(ReportSection).where(ReportSection.report_id == rapor.id)
        ).scalars().all():
            db.delete(eski)
        db.flush()
    else:
        rapor = Report(
            workspace_id=workspace_id,
            period=period,
            period_start=pencere.start,
            period_end=pencere.end,
            title=baslik,
            status=ContentStatus.DRAFT,
            data_quality_notes=kalite.notes,
            assumptions=varsayimlar,
        )
        db.add(rapor)
        db.flush()

    for sira, b in enumerate(bolumler):
        db.add(
            ReportSection(
                workspace_id=workspace_id,
                report_id=rapor.id,
                order_index=sira,
                heading=b.heading,
                body=b.body,
                data=b.data,
                claim_type=b.claim_type,
            )
        )
    db.flush()

    log.info(
        "rapor_uretildi",
        workspace_id=str(workspace_id),
        period=period.value,
        period_start=pencere.start.isoformat(),
        icerik_sayisi=len(simdi),
        kapsam=kalite.coverage,
        bolum_sayisi=len(bolumler),
    )
    return rapor
