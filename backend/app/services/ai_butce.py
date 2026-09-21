"""AI butcesinin ATOMIK kontrolu.

SORUN: "once topla, sonra karsilastir" yontemi ayni anda calisan iki is
icin YANLIS sonuc verir. Ikisi de ayni toplami okur, ikisi de "butce var"
der ve butce asilir. Tek kullanici tek is yaparken gorunmez; n8n gibi
zamanlanmis is akislari ayni anda calistigi icin gorunur hale gelir.

COZUM - rezerve et, sonra kesinlestir:
1. workspace satiri SELECT ... FOR UPDATE ile kilitlenir
2. Ayin toplami (acik rezervasyonlar dahil) kilit altinda okunur
3. Sinir asilacaksa hata verilir
4. Tahmini ust maliyet "acik rezervasyon" olarak yazilir, islem KAPANIR
5. AI cagrisi yapilir (kilit ARTIK YOK)
6. Rezervasyon gercek maliyete cekilir veya silinir

KILIT NEDEN KISA TUTULUYOR: rezervasyon, AI cagrisini yapan islemden AYRI
ve kisa bir veritabani isleminde yapilir. Kilit milisaniyeler surer. Aksi
halde 15 dakika suren bir arastirma cagrisi, ayni musterinin panelden
yaptigi isi de 15 dakika bekletirdi.

SURELI OLMASININ SEBEBI: sureci cokerse acik rezervasyon sonsuza kadar
butceyi tutmasin. Suresi gecen rezervasyon toplama katilmaz.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.ai.base import AIProviderError
from app.core.db import SessionLocal
from app.core.logging_config import get_logger
from app.models.ai import AICostEvent
from app.models.enums import AIProviderName
from app.models.identity import Workspace

log = get_logger("ai_butce")

#: Bir rezervasyonun en fazla ne kadar acik kalabilecegi. En uzun AI
#: cagrisindan (Manus arastirmasi ~15 dk) belirgin sekilde uzun secildi.
REZERVASYON_OMRU_SANIYE = 45 * 60


class BudgetExceeded(AIProviderError):
    """Aylik AI butcesi asildi; yeni cagri baslatilamaz.

    Beklenmedik fatura gelmemesi icin bu kontrol cagriDAN ONCE yapilir.
    """

    def __init__(
        self,
        workspace_id: uuid.UUID,
        spent: Decimal,
        limit: Decimal,
        *,
        reserved: Decimal | None = None,
    ) -> None:
        if reserved is not None:
            mesaj = (
                f"Aylik AI butcesi yetmiyor: harcanan {spent:.2f} + bu isin "
                f"tahmini {reserved:.2f} > sinir {limit:.2f} USD. "
                "Yeni AI isi baslatilmadi."
            )
        else:
            mesaj = (
                f"Aylik AI butcesi asildi: {spent:.2f} / {limit:.2f} USD. "
                "Yeni AI isi baslatilmadi."
            )
        super().__init__(mesaj)
        self.workspace_id = workspace_id
        self.spent = spent
        self.limit = limit
        self.reserved = reserved


# ---------------------------------------------------------------------------
# Toplam okuma
# ---------------------------------------------------------------------------

def ay_basi(now: datetime | None = None) -> datetime:
    simdi = now or datetime.now(UTC)
    return simdi.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def month_spend(db: Session, workspace_id: uuid.UUID, *, now: datetime | None = None) -> Decimal:
    """Bu ay icinde harcanan + o an rezerve edilmis toplam tutar (USD).

    Suresi gecmis rezervasyonlar sayilmaz: onlari yazan surec cokmustur,
    o para harcanmamistir.
    """
    simdi = now or datetime.now(UTC)
    toplam = db.execute(
        select(func.coalesce(func.sum(AICostEvent.amount_usd), 0)).where(
            AICostEvent.workspace_id == workspace_id,
            AICostEvent.occurred_at >= ay_basi(simdi),
            or_(
                AICostEvent.reserved_until.is_(None),
                AICostEvent.reserved_until > simdi,
            ),
        )
    ).scalar_one()
    return Decimal(str(toplam))


def check_budget(db: Session, workspace: Workspace, *, now: datetime | None = None) -> None:
    """Butce zaten dolmussa hata firlatir.

    Bu ON KONTROLDUR; is olusturmadan once bos yere kayit acilmasin diye
    vardir. Esszamanlilik guvencesini `rezerve_et` verir.
    """
    harcanan = month_spend(db, workspace.id, now=now)
    sinir = Decimal(str(workspace.ai_monthly_budget_usd))
    if harcanan >= sinir:
        log.warning(
            "butce_asildi",
            workspace_id=str(workspace.id),
            spent=str(harcanan),
            limit=str(sinir),
        )
        raise BudgetExceeded(workspace.id, harcanan, sinir)


# ---------------------------------------------------------------------------
# Rezervasyon islemi (ayri ve kisa)
# ---------------------------------------------------------------------------

_oturum_uretici: Callable[[], Session] = SessionLocal


def oturum_ureticiyi_ayarla(uretici: Callable[[], Session]) -> Callable[[], Session]:
    """Rezervasyon isleminin hangi oturumda calisacagini degistirir.

    Yalnizca testler icindir: test verisi henuz islenmemis (commit
    edilmemis) oldugu icin ayri bir baglanti onu goremez.
    """
    global _oturum_uretici
    onceki = _oturum_uretici
    _oturum_uretici = uretici
    return onceki


def rezerve_et(
    *,
    workspace_id: uuid.UUID,
    provider: AIProviderName,
    tutar: Decimal | None,
    aciklama: str,
    now: datetime | None = None,
) -> uuid.UUID | None:
    """Butceden yer ayirir. Yer yoksa BudgetExceeded firlatir.

    `tutar` None veya 0 ise rezervasyon YAPILMAZ ve None doner: maliyeti
    USD olarak olculemeyen (Manus) veya bedava (test saglayicisi) cagrilar
    USD butcesini etkilemez.

    Doner: rezervasyon kaydinin kimligi.
    """
    if tutar is None or tutar <= 0:
        return None

    simdi = now or datetime.now(UTC)

    with _oturum_uretici() as oturum:
        # Kilit: ayni musteri icin gelen ikinci istek burada bekler.
        # Beklemesi gereken sure milisaniyedir; kilit bu islem bitince birakilir.
        workspace = oturum.execute(
            select(Workspace).where(Workspace.id == workspace_id).with_for_update()
        ).scalar_one_or_none()

        if workspace is None:
            raise ValueError(f"Musteri bulunamadi: {workspace_id}")

        sinir = Decimal(str(workspace.ai_monthly_budget_usd))
        harcanan = month_spend(oturum, workspace_id, now=simdi)

        if harcanan >= sinir:
            log.warning(
                "butce_asildi",
                workspace_id=str(workspace_id),
                spent=str(harcanan),
                limit=str(sinir),
            )
            raise BudgetExceeded(workspace_id, harcanan, sinir)

        if harcanan + tutar > sinir:
            log.warning(
                "butce_yetmiyor",
                workspace_id=str(workspace_id),
                spent=str(harcanan),
                reserved=str(tutar),
                limit=str(sinir),
            )
            raise BudgetExceeded(workspace_id, harcanan, sinir, reserved=tutar)

        kayit = AICostEvent(
            workspace_id=workspace_id,
            provider=provider,
            occurred_at=simdi,
            amount_usd=tutar,
            description=f"{aciklama} (rezerve)",
            reserved_until=simdi + timedelta(seconds=REZERVASYON_OMRU_SANIYE),
        )
        oturum.add(kayit)
        oturum.commit()
        return kayit.id


def kesinlestir(
    rezervasyon_id: uuid.UUID,
    *,
    gercek_tutar: Decimal | None,
    aciklama: str,
) -> None:
    """Rezervasyonu gercek maliyete ceker.

    `gercek_tutar` None ise (saglayici maliyet bildirmedi) rezervasyon
    SILINMEZ, tahmini tutarla kesinlesir: bilinmeyen maliyeti sifir saymak
    butce sinirini sessizce bozardi.
    """
    with _oturum_uretici() as oturum:
        kayit = oturum.get(AICostEvent, rezervasyon_id)
        if kayit is None:
            return
        if gercek_tutar is not None:
            kayit.amount_usd = gercek_tutar
            kayit.description = aciklama
        else:
            kayit.description = f"{aciklama} (tahmini - saglayici maliyet bildirmedi)"
        kayit.reserved_until = None
        oturum.commit()


def serbest_birak(rezervasyon_id: uuid.UUID) -> None:
    """Rezervasyonu siler: cagri hic yapilamadi, para harcanmadi."""
    with _oturum_uretici() as oturum:
        oturum.execute(delete(AICostEvent).where(AICostEvent.id == rezervasyon_id))
        oturum.commit()
