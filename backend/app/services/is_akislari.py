"""Dort is akisinin Agency Cortex tarafindaki mantigi.

MIMARI (DECISIONS.md K-032): n8n bu fonksiyonlari CAGIRIR, iclerine
karismaz. Zamanlama, tekrar deneme ve sira n8n'in; musteri izolasyonu,
butce, onay ve is kurallari buranin isidir.

ORTAK KURAL - SESSIZ BASARI YOK:
Bir akis yapacak is bulamazsa bunu ACIKCA bildirir ("bagli hesap yok",
"marka tanimli degil"). Hicbir akis, veri yokken sahte sonuc uretmez.
Her fonksiyon ne yaptigini sayilarla ozetler; bu ozet panelde gorunur.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.base import AIProviderError
from app.ai.schemas import TrendResearchBatch
from app.core.logging_config import get_logger
from app.models.brand import Brand
from app.models.enums import Platform, ReportPeriod
from app.models.identity import Workspace
from app.models.research import TrendObservation
from app.models.social import SocialAccount
from app.platforms.base import PlatformError
from app.platforms.registry import get_adapter
from app.services.ai_runner import run_ai_task
from app.services.content import build_context, generate_scripts
from app.services.reports import generate_report
from app.services.sync import sync_social_account
from app.services.token_store import load_tokens, save_tokens

log = get_logger("is_akislari")

TREND_ISTEM_SURUMU = "trend-v1"

TREND_SISTEM_ISTEMI = """Sen bir sosyal medya arastirmacisisin.

GOREVIN: verilen markanin sektorunde SON DONEMDE one cikan konulari,
bicimleri ve rakip hareketlerini arastirmak.

KESIN KURALLAR:
1. Kanit olmadan "kesin" konusma. Yeterli kanitin yoksa claim_type'i
   'hypothesis' yaz ve neyi bilmedigini uncertainties'e koy.
2. Kaynak adresi uydurma. Gercekten baktigin adresleri yaz; bakmadiysan
   listeyi bos birak.
3. Markanin yasakli ifadelerini kullanma.
4. Bulgu bulamadiysan bos liste don. Liste doldurmak icin zayif bulgu
   yazma.
5. Rakibin erisim, kaydetme veya demografi gibi OZEL verilerini tahmin
   etme; bunlar yalnizca hesap sahibine aciktir."""


class IsAkisiHatasi(Exception):
    """Is akisinin tamamlanamadigi durum. Mesaji kullaniciya gosterilir."""


@dataclass
class AkisSonucu:
    """Bir akisin ne yaptiginin ozeti.

    `yapilacak_is_yoktu`: akis calisti ama ortada is yoktu. Bu bir HATA
    DEGILDIR; panelde basarili gorunur, ozette nedeni yazar.
    """

    ozet: dict = field(default_factory=dict)
    notlar: list[str] = field(default_factory=list)
    yapilacak_is_yoktu: bool = False


def _tek_marka(db: Session, workspace_id: uuid.UUID) -> Brand | None:
    return db.execute(
        select(Brand).where(Brand.workspace_id == workspace_id)
        .order_by(Brand.created_at).limit(1)
    ).scalar_one_or_none()


# --- WF-01: Gunluk sosyal zeka ----------------------------------------------

def wf01_gunluk_zeka(db: Session, workspace: Workspace) -> AkisSonucu:
    """Bagli hesaplarin icerik ve metriklerini ceker.

    Hesap basina ayri ayri denenir: birinin hatasi digerlerini durdurmaz.
    Hicbiri calismazsa akis HATA verir - sessizce "basarili" donmez.
    """
    hesaplar = db.execute(
        select(SocialAccount).where(
            SocialAccount.workspace_id == workspace.id,
            SocialAccount.is_active.is_(True),
        )
    ).scalars().all()

    if not hesaplar:
        return AkisSonucu(
            ozet={"hesap": 0},
            notlar=["Bu müşteride bağlı sosyal medya hesabı yok."],
            yapilacak_is_yoktu=True,
        )

    toplam = {"hesap": len(hesaplar), "icerik": 0, "metrik": 0, "hatali_hesap": 0}
    notlar: list[str] = []

    for hesap in hesaplar:
        try:
            adaptor = get_adapter(hesap.platform)
            sonuc = sync_social_account(db, account=hesap, adapter=adaptor)
        except (PlatformError, ValueError) as hata:
            toplam["hatali_hesap"] += 1
            mesaj = f"{hesap.platform.value}/{hesap.username or hesap.external_id}: {hata}"
            notlar.append(mesaj)
            hesap.sync_error = str(hata)[:500]
            log.warning(
                "wf01_hesap_hatasi",
                workspace_id=str(workspace.id),
                social_account_id=str(hesap.id),
                error=type(hata).__name__,
            )
            continue

        toplam["icerik"] += sonuc.media_seen
        toplam["metrik"] += sonuc.account_metrics_written
        if sonuc.errors:
            toplam["hatali_hesap"] += 1
            notlar.extend(
                f"{hesap.platform.value}/{hesap.username or hesap.external_id}: {e}"
                for e in sonuc.errors
            )

    if toplam["hatali_hesap"] == len(hesaplar):
        raise IsAkisiHatasi(
            "Hiçbir hesaptan veri çekilemedi. " + " | ".join(notlar[:5])
        )

    db.flush()
    return AkisSonucu(ozet=toplam, notlar=notlar)


# --- WF-02: Trend arastirmasi -----------------------------------------------

def wf02_trend_arastirmasi(db: Session, workspace: Workspace) -> AkisSonucu:
    """Markanin sektorunde trend arastirir ve bulgulari kaydeder.

    Arastirma AI uzerinden yapilir; bu da butce kilidinden gecer.
    Butce dolduysa akis calismaz ve nedeni yazilir.
    """
    marka = _tek_marka(db, workspace.id)
    if marka is None:
        return AkisSonucu(
            ozet={"bulgu": 0},
            notlar=["Marka bilgisi girilmemiş. Araştırma markaya göre yapılır."],
            yapilacak_is_yoktu=True,
        )

    baglam = build_context(db, workspace_id=workspace.id, brand=marka)
    istem = "\n\n".join([
        baglam.to_prompt(),
        "GOREV: Bu markanin sektorunde son 14 gunde one cikan konulari, "
        "icerik bicimlerini ve rakip hareketlerini arastir.",
        "En fazla 8 bulgu don. Zayif bulgu yazma; bulamazsan bos liste don.",
    ])

    try:
        sonuc = run_ai_task(
            db,
            workspace=workspace,
            task_type="trend_research",
            prompt_version=TREND_ISTEM_SURUMU,
            system=TREND_SISTEM_ISTEMI,
            user_content=istem,
            output_model=TrendResearchBatch,
            metadata={"brand": marka.name},
        )
    except AIProviderError as hata:
        # Butce, yapilandirma ve saglayici hatalari kullaniciya AYNEN
        # gosterilir; "bir sorun olustu" denmez.
        raise IsAkisiHatasi(str(hata)) from hata

    veri = TrendResearchBatch.model_validate(sonuc.parsed)
    simdi = datetime.now(UTC)
    yazilan = 0

    for bulgu in veri.findings:
        # Ayni konu bugun zaten yazildiysa tekrar yazilmaz.
        mevcut = db.execute(
            select(TrendObservation).where(
                TrendObservation.workspace_id == workspace.id,
                TrendObservation.topic == bulgu.topic[:300],
                TrendObservation.observed_at >= simdi - timedelta(days=1),
            )
        ).scalar_one_or_none()
        if mevcut is not None:
            continue

        db.add(TrendObservation(
            workspace_id=workspace.id,
            observed_at=simdi,
            platform=_platform_coz(bulgu.platform),
            topic=bulgu.topic[:300],
            summary=bulgu.summary,
            relevance_to_brand=bulgu.relevance_to_brand,
            source_urls=list(bulgu.source_urls),
            # Kanit zayifsa bulgu "kesin" diye kaydedilmez.
            confidence=("low" if bulgu.claim_type == "hypothesis" else bulgu.confidence),
            uncertainties=list(bulgu.uncertainties),
            ai_task_id=sonuc.task_id,
        ))
        yazilan += 1

    db.flush()
    return AkisSonucu(
        ozet={
            "bulgu": len(veri.findings),
            "yeni_kayit": yazilan,
            "maliyet_usd": str(sonuc.total_cost_usd),
        },
        notlar=[veri.research_note] if veri.research_note else [],
    )


def _platform_coz(deger: str) -> Platform | None:
    """AI'nin yazdigi platform adini sisteme cevirir.

    Tanimadigimiz bir deger geldiyse None yazilir; uydurma bir platform
    kaydedilmez.
    """
    try:
        return Platform((deger or "").strip().lower())
    except ValueError:
        return None


# --- WF-03: Icerik zekasi ---------------------------------------------------

def wf03_icerik_zekasi(
    db: Session, workspace: Workspace, *, platformlar: list[Platform] | None = None
) -> AkisSonucu:
    """Son trendlerden yola cikarak icerik senaryosu onerir.

    Uretilen her sey TASLAKTIR. Hicbir sey yayinlanmaz, onaya duser.
    """
    marka = _tek_marka(db, workspace.id)
    if marka is None:
        return AkisSonucu(
            ozet={"senaryo": 0},
            notlar=["Marka bilgisi girilmemiş. İçerik markaya göre üretilir."],
            yapilacak_is_yoktu=True,
        )

    simdi = datetime.now(UTC)
    trendler = db.execute(
        select(TrendObservation).where(
            TrendObservation.workspace_id == workspace.id,
            TrendObservation.observed_at >= simdi - timedelta(days=14),
        ).order_by(TrendObservation.observed_at.desc()).limit(5)
    ).scalars().all()

    if not trendler:
        return AkisSonucu(
            ozet={"senaryo": 0},
            notlar=[
                "Son 14 günde trend bulgusu yok. Önce trend araştırması "
                "çalışmalı; bulgusuz içerik üretmek tahmin olurdu."
            ],
            yapilacak_is_yoktu=True,
        )

    ozet = "\n".join(
        f"- {t.topic}: {(t.summary or '')[:200]}" for t in trendler
    )
    brief = (
        "Asagidaki guncel bulgulardan yola cikarak icerik oner. "
        "Bulguyla baglantisi olmayan fikir uretme.\n" + ozet
    )

    hedefler = platformlar or [Platform.INSTAGRAM]
    try:
        sonuc = generate_scripts(
            db, workspace=workspace, brand=marka, platforms=hedefler, brief=brief,
        )
    except AIProviderError as hata:
        raise IsAkisiHatasi(str(hata)) from hata

    return AkisSonucu(
        ozet={
            "senaryo": len(sonuc.scripts),
            "fikir_tekrari": sonuc.was_duplicate,
            "yasakli_ifade": len(sonuc.violations),
        },
        notlar=(
            [f"Yasaklı ifade bulundu: {', '.join(sonuc.violations)}"]
            if sonuc.violations else []
        ),
    )


# --- WF-05: Baglanti sagligi ------------------------------------------------

#: Anahtar bu kadar gun kaldiginda yenilenir.
#
# NEDEN BU KADAR ERKEN: Instagram'in uzun omurlu anahtari ~60 gun gecerli.
# Son gune birakmak, o gun bir aksilik (n8n kapali, Meta hata veriyor)
# oldugunda hesabin olmesi demek. 25 gunluk pay, iki haftalik bir kesintiyi
# bile tolere eder.
YENILEME_ESIGI_GUN = 25

#: Bu esigin altina dusup yenilenemeyen anahtar icin uyari uretilir.
UYARI_ESIGI_GUN = 7


def wf05_baglanti_sagligi(db: Session, workspace: Workspace) -> AkisSonucu:
    """Erisim anahtarlarini suresi dolmadan yeniler.

    BU AKIS OLMADAN sistem yaklasik 60 gun sonra sessizce durur: anahtar
    suresi dolar, veri cekilemez ve kimse nedenini bilmez.

    Yenilenemeyen anahtar GIZLENMEZ: hesap isaretlenir ve panelde gorunur.
    """
    hesaplar = db.execute(
        select(SocialAccount).where(
            SocialAccount.workspace_id == workspace.id,
            SocialAccount.is_active.is_(True),
        )
    ).scalars().all()

    if not hesaplar:
        return AkisSonucu(
            ozet={"hesap": 0},
            notlar=["Bu müşteride bağlı hesap yok."],
            yapilacak_is_yoktu=True,
        )

    simdi = datetime.now(UTC)
    toplam = {
        "hesap": len(hesaplar), "yenilendi": 0,
        "gerek_yoktu": 0, "yenilenemedi": 0, "suresi_bitiyor": 0,
    }
    notlar: list[str] = []

    for hesap in hesaplar:
        ad = hesap.username or hesap.external_id
        anahtarlar = load_tokens(
            db, workspace_id=workspace.id, social_account_id=hesap.id
        )
        if anahtarlar is None:
            toplam["yenilenemedi"] += 1
            notlar.append(f"{ad}: kayıtlı erişim anahtarı yok, yeniden bağlanmalı.")
            hesap.sync_error = "Erişim anahtarı yok. Hesabı yeniden bağlayın."
            continue

        kalan_gun = (
            (anahtarlar.expires_at - simdi).days
            if anahtarlar.expires_at is not None else None
        )

        # Bitis tarihi bilinmiyorsa TAHMIN EDILMEZ; yenileme denenir.
        # Gereksiz bir yenileme zararsizdir, kacirilmis bir yenileme degil.
        if kalan_gun is not None and kalan_gun > YENILEME_ESIGI_GUN:
            toplam["gerek_yoktu"] += 1
            continue

        if not anahtarlar.refresh_token:
            toplam["yenilenemedi"] += 1
            mesaj = (
                f"{ad}: yenileme anahtarı yok, "
                + (f"{kalan_gun} gün sonra" if kalan_gun is not None else "süresi dolunca")
                + " bağlantı kesilecek. Hesabı yeniden bağlayın."
            )
            notlar.append(mesaj)
            hesap.sync_error = mesaj
            if kalan_gun is not None and kalan_gun <= UYARI_ESIGI_GUN:
                toplam["suresi_bitiyor"] += 1
            continue

        try:
            yeni = get_adapter(hesap.platform).refresh_token(
                refresh_token=anahtarlar.refresh_token
            )
        except PlatformError as hata:
            toplam["yenilenemedi"] += 1
            mesaj = f"{ad}: anahtar yenilenemedi ({hata})."
            notlar.append(mesaj)
            hesap.sync_error = mesaj[:500]
            if kalan_gun is not None and kalan_gun <= UYARI_ESIGI_GUN:
                toplam["suresi_bitiyor"] += 1
            log.warning(
                "wf05_yenileme_basarisiz",
                workspace_id=str(workspace.id),
                social_account_id=str(hesap.id),
                error=type(hata).__name__,
            )
            continue

        save_tokens(
            db, workspace_id=workspace.id,
            social_account_id=hesap.id, tokens=yeni,
        )
        # Onceki yenileme hatasi varsa temizlenir: sorun gecti.
        if hesap.sync_error and "anahtar" in hesap.sync_error.lower():
            hesap.sync_error = None
        toplam["yenilendi"] += 1

    db.flush()

    # Yenilenemeyen anahtar VAR ise bu bir hata degil ama sessiz de gecilmez;
    # ozet ve notlar panelde gorunur.
    return AkisSonucu(ozet=toplam, notlar=notlar)


# --- WF-04: Haftalik zeka raporu --------------------------------------------

def wf04_haftalik_rapor(
    db: Session, workspace: Workspace, *, referans: date | None = None
) -> AkisSonucu:
    """Haftalik raporu uretir. Rapor TASLAKTIR ve onaya duser."""
    gun = referans or date.today()
    rapor = generate_report(
        db, workspace_id=workspace.id, period=ReportPeriod.WEEKLY, reference=gun,
    )
    db.flush()

    return AkisSonucu(
        ozet={
            "rapor_id": str(rapor.id),
            "donem": f"{rapor.period_start} - {rapor.period_end}",
            "durum": rapor.status.value,
            "veri_uyarisi": len(rapor.data_quality_notes or []),
        },
        notlar=list(rapor.data_quality_notes or [])[:5],
    )


AKISLAR = {
    "wf01_gunluk_zeka": wf01_gunluk_zeka,
    "wf02_trend": wf02_trend_arastirmasi,
    "wf03_icerik": wf03_icerik_zekasi,
    "wf04_haftalik_rapor": wf04_haftalik_rapor,
    "wf05_baglanti_sagligi": wf05_baglanti_sagligi,
}
