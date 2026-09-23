"""Gosterge paneli ozeti.

KURAL: burada gosterilen HER sayi gercek bir kayittan gelir. Ornek veri,
tahmin veya yer tutucu YOKTUR. Bir sayi uretilemiyorsa sayfa onu
gostermez ve NEDEN gosteremedigini yazar.

Neden bu kadar kati: gosterge paneli "her sey yolunda" hissi veren bir
ekrandir. Uydurma bir sayi burada, baska hicbir yerde olmadigi kadar
zarar verir - cunku kimse sorgulamaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.content import ContentCalendar, ContentScript
from app.models.enums import AutomationStatus, ContentStatus
from app.models.identity import Workspace, WorkspaceMember
from app.models.otomasyon import AutomationRun
from app.models.reporting import Report
from app.models.social import SocialAccount
from app.services.ai_butce import month_spend

#: "Yaklasan" sayilan gun sayisi.
YAKLASAN_GUN = 7
#: Son calismalar listesinde kac satir gosterilir.
SON_CALISMA = 8


@dataclass
class MusteriOzeti:
    id: str
    ad: str
    bekleyen_onay: int
    yaklasan_plan: int
    bagli_hesap: int
    butce_sinir: Decimal
    butce_harcanan: Decimal

    @property
    def butce_yuzde(self) -> int:
        if not self.butce_sinir:
            return 0
        return min(100, int(self.butce_harcanan / self.butce_sinir * 100))

    @property
    def butce_kritik(self) -> bool:
        return self.butce_yuzde >= 80


@dataclass
class Ozet:
    musteri_sayisi: int = 0
    bekleyen_onay: int = 0
    yaklasan_plan: int = 0
    gecikmis_plan: int = 0
    bagli_hesap: int = 0
    basarisiz_calisma: int = 0
    musteriler: list[MusteriOzeti] = field(default_factory=list)
    son_calismalar: list[dict] = field(default_factory=list)
    #: Hicbir musteride bagli hesap yoksa bunun sebebi yazilir.
    notlar: list[str] = field(default_factory=list)


def _erisilen_musteriler(db: Session, user) -> list[Workspace]:
    """Kullanicinin UYE OLDUGU musteriler.

    Sistem yoneticisi olmak otomatik erisim VERMEZ: gosterge paneli de
    musteri izolasyonuna uyar.
    """
    return list(db.execute(
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id)
        .order_by(Workspace.name)
    ).scalars().all())


def _sayi(db: Session, sorgu) -> int:
    return int(db.execute(sorgu).scalar_one() or 0)


def ozet_getir(db: Session, user, *, simdi: datetime | None = None) -> Ozet:
    """Kullanicinin gorebildigi musteriler icin ozet."""
    an = simdi or datetime.now(UTC)
    sinir = an + timedelta(days=YAKLASAN_GUN)

    musteriler = _erisilen_musteriler(db, user)
    ozet = Ozet(musteri_sayisi=len(musteriler))
    if not musteriler:
        ozet.notlar.append(
            "Henüz hiçbir müşteriye atanmadınız. Müşteri ekleyin veya bir "
            "sistem yöneticisinden sizi bir müşterinin ekibine atamasını isteyin."
        )
        return ozet

    kimlikler = [w.id for w in musteriler]

    # Onay bekleyen: hem icerik hem rapor.
    bekleyen_durumlar = (ContentStatus.INTERNAL_REVIEW, ContentStatus.CLIENT_REVIEW)
    for w in musteriler:
        bekleyen = _sayi(db, select(func.count()).select_from(ContentScript).where(
            ContentScript.workspace_id == w.id,
            ContentScript.status.in_(bekleyen_durumlar),
        )) + _sayi(db, select(func.count()).select_from(Report).where(
            Report.workspace_id == w.id,
            Report.status.in_(bekleyen_durumlar),
        ))

        yaklasan = _sayi(db, select(func.count()).select_from(ContentCalendar).where(
            ContentCalendar.workspace_id == w.id,
            ContentCalendar.published_at.is_(None),
            ContentCalendar.scheduled_for > an,
            ContentCalendar.scheduled_for <= sinir,
        ))

        hesap = _sayi(db, select(func.count()).select_from(SocialAccount).where(
            SocialAccount.workspace_id == w.id,
            SocialAccount.is_active.is_(True),
        ))

        ozet.musteriler.append(MusteriOzeti(
            id=str(w.id), ad=w.name,
            bekleyen_onay=bekleyen, yaklasan_plan=yaklasan, bagli_hesap=hesap,
            butce_sinir=Decimal(w.ai_monthly_budget_usd or 0),
            butce_harcanan=month_spend(db, w.id, now=an),
        ))
        ozet.bekleyen_onay += bekleyen
        ozet.yaklasan_plan += yaklasan
        ozet.bagli_hesap += hesap

    # GECIKMIS plan: zamani gecmis ama yayinlanmamis.
    # Bu sayi gizlenmez; gosterge panelinin isi kotu haberi de vermektir.
    ozet.gecikmis_plan = _sayi(db, select(func.count()).select_from(ContentCalendar).where(
        ContentCalendar.workspace_id.in_(kimlikler),
        ContentCalendar.published_at.is_(None),
        ContentCalendar.scheduled_for < an,
    ))

    # Son 24 saatte basarisiz is akisi calismalari.
    ozet.basarisiz_calisma = _sayi(db, select(func.count()).select_from(AutomationRun).where(
        AutomationRun.workspace_id.in_(kimlikler),
        AutomationRun.status == AutomationStatus.FAILED,
        AutomationRun.started_at >= an - timedelta(days=1),
    ))

    ad_ile = {w.id: w.name for w in musteriler}
    son = db.execute(
        select(AutomationRun)
        .where(AutomationRun.workspace_id.in_(kimlikler))
        .order_by(AutomationRun.started_at.desc())
        .limit(SON_CALISMA)
    ).scalars().all()
    ozet.son_calismalar = [
        {
            "musteri": ad_ile.get(r.workspace_id, "?"),
            "akis": r.workflow_key,
            "durum": r.status.value,
            "basarili": r.status == AutomationStatus.SUCCEEDED,
            "basarisiz": r.status == AutomationStatus.FAILED,
            "zaman": r.started_at,
            # Hata SAKLANMAZ; ozeti panelde gorunur.
            "hata": (r.error_message or "")[:200] or None,
        }
        for r in son
    ]

    if not ozet.son_calismalar:
        ozet.notlar.append(
            "Hiçbir iş akışı henüz çalışmadı. İş akışları müşteri başına "
            "açılır: Otomasyon sayfasından açabilirsiniz."
        )
    if ozet.bagli_hesap == 0:
        ozet.notlar.append(
            "Hiç bağlı sosyal medya hesabı yok. Veri toplayan iş akışları "
            "hesap bağlanana kadar \"yapacak iş yoktu\" diyecektir."
        )
    return ozet


def toplam_butce(ozet: Ozet) -> tuple[Decimal, Decimal]:
    """(harcanan, sinir) toplamlari."""
    harcanan = sum((m.butce_harcanan for m in ozet.musteriler), Decimal(0))
    sinir = sum((m.butce_sinir for m in ozet.musteriler), Decimal(0))
    return harcanan, sinir
