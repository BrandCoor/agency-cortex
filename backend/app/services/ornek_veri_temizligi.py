"""Ornek veri saglayicisinin GECMISTE yazdigi kayitlari bulur ve siler.

NEDEN BU DOSYA VAR
Sistem bir donem ornek veri modunda calisti ve is akislari, uretilen
ornek metinleri GERCEK bulgu kayitlari olarak veritabanina yazdi. Panelde
bu satirlar gercek bulgularla ayni listede, ayni bicimde duruyor:

    "Ornek veri saglayicisi uretti - gercek gozlem DEGIL."

Metnin uzerinde "ornek veridir" yazmasi yetmiyor; kayit listede kaliyor,
birikiyor ve kullanici "rakip analizi sacmaliyor" diyor - hakli olarak.

Is akislari artik uretimde bu kayitlari YAZMIYOR (is_akislari._ornek_veri_mi).
Bu dosya, DAHA ONCE yazilmis olanlari temizler.

NASIL TANINIYOR
Ornek veri saglayicisinin urettigi metinler sabittir ve asagida birebir
listelenmistir. Tahmine dayali bir esleme YAPILMIYOR: "ornek" kelimesi
gecen her kaydi silmek, kullanicinin kendi yazdigi gercek bir notu da
silebilirdi.
"""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models.research import CompetitorObservation, TrendObservation

log = get_logger("ornek_veri_temizligi")

#: Ornek veri saglayicisinin urettigi metinlerin BASLANGICLARI.
#:
#: Hem yeni (Turkce karakterli) hem eski (ASCII) hali listede: sunucuda
#: her iki donemden de kayit kalmis olabilir.
IMZALAR: tuple[str, ...] = (
    "Örnek veri sağlayıcısı üretti",
    "Sahte saglayici tarafindan uretildi",
    "Örnek veri yorumu",
    "Sahte saglayici yorumu",
)


def _kosul(sutun):
    """Metin bu imzalardan biriyle basliyor mu?"""
    return or_(*[sutun.like(f"{imza}%") for imza in IMZALAR])


def say(db: Session, workspace_id: uuid.UUID) -> dict[str, int]:
    """Kac ornek veri kaydi var? Silmeden once gosterilir."""
    rakip = db.execute(
        select(CompetitorObservation).where(
            CompetitorObservation.workspace_id == workspace_id,
            _kosul(CompetitorObservation.summary),
        )
    ).scalars().all()
    trend = db.execute(
        select(TrendObservation).where(
            TrendObservation.workspace_id == workspace_id,
            _kosul(TrendObservation.summary),
        )
    ).scalars().all()
    return {"rakip": len(rakip), "trend": len(trend)}


def temizle(db: Session, workspace_id: uuid.UUID) -> dict[str, int]:
    """Ornek veri kayitlarini siler. Yalnizca BU musterinin kayitlari.

    Silme geri alinamaz; bu yuzden panelde onay soruluyor. Silinen sey
    gercek bir bulgu degil, ornek metindir - ama yine de kullanicinin
    karari olmali.
    """
    silinen = {"rakip": 0, "trend": 0}

    for kayit in db.execute(
        select(CompetitorObservation).where(
            CompetitorObservation.workspace_id == workspace_id,
            _kosul(CompetitorObservation.summary),
        )
    ).scalars().all():
        db.delete(kayit)
        silinen["rakip"] += 1

    for kayit in db.execute(
        select(TrendObservation).where(
            TrendObservation.workspace_id == workspace_id,
            _kosul(TrendObservation.summary),
        )
    ).scalars().all():
        db.delete(kayit)
        silinen["trend"] += 1

    db.flush()
    log.info(
        "ornek_veri_temizlendi",
        workspace_id=str(workspace_id),
        rakip=silinen["rakip"],
        trend=silinen["trend"],
    )
    return silinen
