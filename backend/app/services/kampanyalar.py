"""Kampanya ve platform dagilimi.

DURUSTLUK KURALI: buradaki rakamlar KULLANICININ GIRDIGI planlama
verisidir. Reklam platformlarindan cekilen gercek harcama DEGILDIR.
Panel bunu acikca yazar; yoksa kullanici "Meta'dan geliyor" sanabilir.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.brand import Campaign
from app.models.enums import ReklamPlatformu
from app.models.kampanya import CampaignPlatform

PLATFORM_ADLARI: dict[ReklamPlatformu, str] = {
    ReklamPlatformu.META: "Meta (Facebook + Instagram)",
    ReklamPlatformu.GOOGLE_ADS: "Google Ads",
    ReklamPlatformu.TIKTOK_ADS: "TikTok Ads",
    ReklamPlatformu.LINKEDIN_ADS: "LinkedIn Ads",
    ReklamPlatformu.X_ADS: "X Ads",
    ReklamPlatformu.YOUTUBE_ADS: "YouTube Ads",
    ReklamPlatformu.ORGANIK: "Organik (reklam harcaması yok)",
}

#: Butce alaninin ust siniri. Sinirsiz birakmak, yanlislikla girilen
#: bir rakamin toplamlari anlamsizlastirmasina yol acardi.
AZAMI_BUTCE = Decimal("99999999.99")


class KampanyaHatasi(Exception):
    """Kampanya isleminde kurala takilan durum."""


@dataclass
class PlatformSatiri:
    id: str
    platform: str
    platform_adi: str
    butce: Decimal
    hedef: str | None
    notlar: str | None
    harici_kimlik: str | None


def butce_coz(ham: str) -> Decimal:
    """Kullanicinin yazdigi tutari sayiya cevirir.

    '1.500,50' ve '1500.50' gibi iki yazim da kabul edilir: kullaniciya
    tek bir bicim dayatmak, "neden kabul etmedi?" sorusunu dogururdu.
    """
    metin = (ham or "").strip().replace(" ", "").replace("₺", "").replace("$", "")
    if not metin:
        return Decimal("0")

    # Turkce yazim: nokta binlik, virgul ondalik.
    if "," in metin and "." in metin:
        metin = metin.replace(".", "").replace(",", ".")
    elif "," in metin:
        metin = metin.replace(",", ".")

    try:
        deger = Decimal(metin)
    except (InvalidOperation, ValueError) as hata:
        raise KampanyaHatasi(f"Bütçe anlaşılamadı: {ham}") from hata

    if deger < 0:
        raise KampanyaHatasi("Bütçe eksi olamaz.")
    if deger > AZAMI_BUTCE:
        raise KampanyaHatasi("Bütçe çok büyük; bir yazım hatası olabilir.")
    return deger.quantize(Decimal("0.01"))


def platform_ekle(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    platform: ReklamPlatformu,
    butce: Decimal,
    hedef: str | None = None,
    notlar: str | None = None,
    harici_kimlik: str | None = None,
) -> CampaignPlatform:
    kampanya = db.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            # Baska musterinin kampanyasi, kimligi bilinse bile
            # degistirilemez.
            Campaign.workspace_id == workspace_id,
        )
    ).scalar_one_or_none()
    if kampanya is None:
        raise KampanyaHatasi("Kampanya bulunamadı.")

    mevcut = db.execute(
        select(CampaignPlatform).where(
            CampaignPlatform.campaign_id == campaign_id,
            CampaignPlatform.platform == platform,
        )
    ).scalar_one_or_none()
    if mevcut is not None:
        # Ayni platform iki kez eklenirse toplam butce SESSIZCE iki kez
        # sayilirdi. Guncelleme yapiyoruz, kopya olusturmuyoruz.
        mevcut.butce = butce
        mevcut.hedef = (hedef or "").strip() or None
        mevcut.notlar = (notlar or "").strip() or None
        mevcut.harici_kimlik = (harici_kimlik or "").strip() or None
        db.flush()
        return mevcut

    satir = CampaignPlatform(
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        platform=platform,
        butce=butce,
        hedef=(hedef or "").strip() or None,
        notlar=(notlar or "").strip() or None,
        harici_kimlik=(harici_kimlik or "").strip() or None,
    )
    db.add(satir)
    db.flush()
    return satir


def platform_kaldir(
    db: Session, *, workspace_id: uuid.UUID, satir_id: uuid.UUID
) -> None:
    satir = db.execute(
        select(CampaignPlatform).where(
            CampaignPlatform.id == satir_id,
            CampaignPlatform.workspace_id == workspace_id,
        )
    ).scalar_one_or_none()
    if satir is None:
        raise KampanyaHatasi("Kayıt bulunamadı.")
    db.delete(satir)
    db.flush()


def platformlari_getir(
    db: Session, campaign_id: uuid.UUID
) -> list[PlatformSatiri]:
    satirlar = db.execute(
        select(CampaignPlatform)
        .where(CampaignPlatform.campaign_id == campaign_id)
        .order_by(CampaignPlatform.platform)
    ).scalars().all()
    return [
        PlatformSatiri(
            id=str(s.id),
            platform=s.platform.value,
            platform_adi=PLATFORM_ADLARI.get(s.platform, s.platform.value),
            butce=s.butce,
            hedef=s.hedef,
            notlar=s.notlar,
            harici_kimlik=s.harici_kimlik,
        )
        for s in satirlar
    ]


def toplam_butce(db: Session, campaign_id: uuid.UUID) -> Decimal:
    return sum(
        (s.butce for s in platformlari_getir(db, campaign_id)), Decimal("0")
    )


def gun_durumu(bugun: date, baslangic: date | None, bitis: date | None) -> str:
    """Kampanya su an hangi asamada?

    Tarih girilmemisse TAHMIN EDILMEZ; "tarih girilmedi" denir.
    """
    if baslangic is None and bitis is None:
        return "tarih girilmedi"
    if baslangic and bugun < baslangic:
        return "başlamadı"
    if bitis and bugun > bitis:
        return "bitti"
    return "devam ediyor"
