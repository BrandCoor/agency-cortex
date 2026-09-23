"""Izlenen hesap yonetimi.

DURUSTLUK KURALI: bu sistem su anda izlenen bir hesaptan VERI CEKEMEZ.
Kullanici adi kaydedilir, hangi amacla izlendigi kaydedilir; ama veri
kaynagi henuz dogrulanmadi (bkz. docs/platforms/meta.md).

Bu yuzden her izlenen hesap, panelde neyin calistigi ve neyin
CALISMADIGI acikca yazili olarak gosterilir. "Yakinda" denmez; ne
oldugu yazilir.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import Platform
from app.models.izlenen import IzlemeTuru, TrackedAccount
from app.models.social import SocialAccount

#: Kullanici adinda izin verilen karakterler (Instagram/Facebook ortak).
_KULLANICI_ADI = re.compile(r"^[A-Za-z0-9._]{1,200}$")

#: Veri cekilemedigi surece her izlenen hesapta gosterilen aciklama.
VERI_KAYNAGI_YOK = (
    "Kaydedildi. Bu hesaptan otomatik veri çekilmiyor: Meta'nın rakip "
    "hesap verisi için gerekli uç adresleri ve izin adları henüz resmî "
    "dokümandan doğrulanmadı. Doğrulanmadan tahminle yazmak, yanlış "
    "veriyi rapora sokardı."
)


class IzlemeHatasi(Exception):
    """Izlenen hesap isleminde kurala takilan durum."""


def kullanici_adi_ayikla(ham: str) -> str:
    """Yazilan metinden kullanici adini cikarir.

    Kullanici bazen '@ad', bazen tam baglanti yapistirir. Ikisini de
    kabul etmek, "neden calismadi?" sorusunu bastan onler.
    """
    metin = (ham or "").strip()
    if not metin:
        raise IzlemeHatasi("Kullanıcı adı veya bağlantı yazın.")

    # Tam baglanti: son yol parcasini al.
    if "/" in metin:
        metin = metin.rstrip("/")
        parcalar = [p for p in metin.split("/") if p]
        if parcalar:
            metin = parcalar[-1]
        # Sorgu parametrelerini at.
        metin = metin.split("?")[0]

    metin = metin.lstrip("@").strip().lower()

    if not _KULLANICI_ADI.match(metin):
        raise IzlemeHatasi(
            "Kullanıcı adı anlaşılamadı. Örnek: @markaadi veya "
            "https://instagram.com/markaadi"
        )
    return metin


def ekle(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    platform: Platform,
    ham_ad: str,
    tur: IzlemeTuru,
    notlar: str | None = None,
) -> TrackedAccount:
    """Bir hesabi izleme listesine alir."""
    ad = kullanici_adi_ayikla(ham_ad)

    # Zaten BAGLI olan bir hesabi ayrica izlemek anlamsizdir: bagli
    # hesabin verisi zaten tam gelir, izleme ise sinirlidir. Ayni hesap
    # iki listede gorunseydi hangi verinin gecerli oldugu belirsizlesirdi.
    bagli = db.execute(
        select(SocialAccount).where(
            SocialAccount.workspace_id == workspace_id,
            SocialAccount.platform == platform,
            SocialAccount.username == ad,
        )
    ).scalar_one_or_none()
    if bagli is not None:
        raise IzlemeHatasi(
            f"@{ad} bu müşteride zaten BAĞLI hesap. Bağlı hesabın verisi "
            "zaten tam geliyor; ayrıca izlemeye gerek yok."
        )

    mevcut = db.execute(
        select(TrackedAccount).where(
            TrackedAccount.workspace_id == workspace_id,
            TrackedAccount.platform == platform,
            TrackedAccount.username == ad,
        )
    ).scalar_one_or_none()
    if mevcut is not None:
        raise IzlemeHatasi(f"@{ad} zaten izleme listesinde.")

    kayit = TrackedAccount(
        workspace_id=workspace_id,
        platform=platform,
        username=ad,
        tur=tur,
        notlar=(notlar or "").strip() or None,
        veri_durumu=VERI_KAYNAGI_YOK,
    )
    db.add(kayit)
    db.flush()
    return kayit


def kaldir(db: Session, *, workspace_id: uuid.UUID, kayit_id: uuid.UUID) -> None:
    kayit = db.execute(
        select(TrackedAccount).where(
            TrackedAccount.id == kayit_id,
            # Baska musterinin kaydi, kimligi bilinse bile silinemez.
            TrackedAccount.workspace_id == workspace_id,
        )
    ).scalar_one_or_none()
    if kayit is None:
        raise IzlemeHatasi("Kayıt bulunamadı.")
    db.delete(kayit)
    db.flush()


def listele(db: Session, workspace_id: uuid.UUID) -> list[TrackedAccount]:
    return list(db.execute(
        select(TrackedAccount)
        .where(TrackedAccount.workspace_id == workspace_id)
        .order_by(TrackedAccount.tur, TrackedAccount.username)
    ).scalars().all())
