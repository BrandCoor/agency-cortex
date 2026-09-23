"""Yayin takvimi.

NE YAPAR: onaylanmis icerigin ne zaman paylasilacagini planlar.

NE YAPMAZ: PAYLASMAZ. Bu surumde sistem hicbir seyi kendisi yayinlamaz;
yayin izinleri Meta'dan bilerek istenmiyor. Paylasimi kullanici yapar ve
takvimde "yayinlandi" olarak isaretler. Boylece takvim GERCEGI gosterir,
varsayimi degil.

EN ONEMLI KURAL: yalnizca ONAYLANMIS icerik planlanabilir. Onaysiz bir
icerigi takvime koymak, onay sistemini etkisiz hale getirirdi.
"""

from __future__ import annotations

import calendar as _takvim
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models.content import ContentCalendar, ContentIdea, ContentScript
from app.models.enums import ContentStatus

log = get_logger("takvim")

#: Takvime konulabilen tek durum. Onay sistemi burada da gecerlidir.
PLANLANABILIR_DURUM = ContentStatus.APPROVED


class TakvimHatasi(Exception):
    """Takvim isleminde kurala takilan durum."""


@dataclass
class Kayit:
    """Takvimdeki tek bir plan."""

    id: uuid.UUID
    script_id: uuid.UUID
    ne_zaman: datetime
    platform: str
    baslik: str
    kanca: str | None
    not_: str | None
    yayinlandi: bool
    yayin_zamani: datetime | None
    gecikti: bool


def _senaryo(db: Session, workspace_id: uuid.UUID, script_id: uuid.UUID) -> ContentScript:
    senaryo = db.execute(
        select(ContentScript).where(
            ContentScript.id == script_id,
            # Baska musterinin senaryosu, kimligi bilinse bile planlanamaz.
            ContentScript.workspace_id == workspace_id,
        )
    ).scalar_one_or_none()
    if senaryo is None:
        raise TakvimHatasi("İçerik bulunamadı.")
    return senaryo


def planla(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    script_id: uuid.UUID,
    ne_zaman: datetime,
    planlayan_user_id: uuid.UUID | None,
    notlar: str | None = None,
    simdi: datetime | None = None,
) -> ContentCalendar:
    """Onaylanmis bir icerigi takvime koyar."""
    senaryo = _senaryo(db, workspace_id, script_id)

    mevcut = db.execute(
        select(ContentCalendar).where(
            ContentCalendar.workspace_id == workspace_id,
            ContentCalendar.script_id == script_id,
        )
    ).scalar_one_or_none()

    if mevcut is not None and mevcut.published_at is not None:
        raise TakvimHatasi(
            "Bu içerik yayınlandı olarak işaretlenmiş; tekrar planlanamaz."
        )

    # Zaten planli bir icerigin durumu PLANLANDI'dir; bunu ONAYSIZ sayip
    # reddetmek, saati degistirmeyi imkansiz kilardi. Bu yuzden PLANLANDI
    # durumuna YALNIZCA bu icerigin kendi plani varken izin veriyoruz.
    izinli_durumlar = {PLANLANABILIR_DURUM}
    if mevcut is not None:
        izinli_durumlar.add(ContentStatus.SCHEDULED)

    if senaryo.status not in izinli_durumlar:
        raise TakvimHatasi(
            "Yalnızca ONAYLANMIŞ içerik planlanabilir. "
            f"Bu içeriğin durumu: {senaryo.status.value}."
        )

    an = simdi or datetime.now(UTC)
    if ne_zaman <= an:
        raise TakvimHatasi("Geçmiş bir zamana plan yapılamaz.")

    if mevcut is not None:
        # Zaten planliysa TASINIR; ikinci bir kayit olusturulmaz.
        mevcut.scheduled_for = ne_zaman
        mevcut.notes = notlar or mevcut.notes
        db.flush()
        log.info(
            "takvim_plani_tasindi",
            workspace_id=str(workspace_id), script_id=str(script_id),
        )
        return mevcut

    kayit = ContentCalendar(
        workspace_id=workspace_id,
        script_id=script_id,
        scheduled_for=ne_zaman,
        status=ContentStatus.SCHEDULED,
        notes=notlar,
        planned_by_user_id=planlayan_user_id,
    )
    db.add(kayit)
    senaryo.status = ContentStatus.SCHEDULED
    db.flush()
    log.info(
        "takvime_eklendi",
        workspace_id=str(workspace_id), script_id=str(script_id),
    )
    return kayit


def kaldir(db: Session, *, workspace_id: uuid.UUID, kayit_id: uuid.UUID) -> None:
    """Plani takvimden kaldirir; icerik onayli durumuna doner."""
    kayit = db.execute(
        select(ContentCalendar).where(
            ContentCalendar.id == kayit_id,
            ContentCalendar.workspace_id == workspace_id,
        )
    ).scalar_one_or_none()
    if kayit is None:
        raise TakvimHatasi("Plan bulunamadı.")
    if kayit.published_at is not None:
        raise TakvimHatasi(
            "Yayınlanmış bir plan kaldırılamaz. Geçmiş kaydı silmek, "
            "neyin ne zaman paylaşıldığını kaybetmek olurdu."
        )

    senaryo = db.get(ContentScript, kayit.script_id)
    if senaryo is not None and senaryo.status is ContentStatus.SCHEDULED:
        senaryo.status = ContentStatus.APPROVED

    db.delete(kayit)
    db.flush()


def yayinlandi_isaretle(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    kayit_id: uuid.UUID,
    isaretleyen_user_id: uuid.UUID | None,
    simdi: datetime | None = None,
) -> ContentCalendar:
    """Kullanici paylasimi yapti; takvim gercegi yansitsin.

    SISTEM PAYLASMAZ. Bu yalnizca bir KAYITTIR.
    """
    kayit = db.execute(
        select(ContentCalendar).where(
            ContentCalendar.id == kayit_id,
            ContentCalendar.workspace_id == workspace_id,
        )
    ).scalar_one_or_none()
    if kayit is None:
        raise TakvimHatasi("Plan bulunamadı.")
    if kayit.published_at is not None:
        raise TakvimHatasi("Bu plan zaten yayınlandı olarak işaretlenmiş.")

    kayit.published_at = simdi or datetime.now(UTC)
    kayit.published_by_user_id = isaretleyen_user_id
    kayit.status = ContentStatus.PUBLISHED

    senaryo = db.get(ContentScript, kayit.script_id)
    if senaryo is not None:
        senaryo.status = ContentStatus.PUBLISHED

    db.flush()
    return kayit


def planlanabilir_icerikler(db: Session, workspace_id: uuid.UUID) -> list[dict]:
    """Takvime konulmayi bekleyen ONAYLI icerikler."""
    satirlar = db.execute(
        select(ContentScript, ContentIdea)
        .join(ContentIdea, ContentIdea.id == ContentScript.idea_id)
        .where(
            ContentScript.workspace_id == workspace_id,
            ContentScript.status == PLANLANABILIR_DURUM,
        )
        .order_by(ContentScript.created_at.desc())
    ).all()

    return [
        {
            "id": str(s.id),
            "platform": s.platform.value,
            "baslik": f.title,
            "kanca": (s.hook or "")[:90],
        }
        for s, f in satirlar
    ]


def _kayda_cevir(
    kayit: ContentCalendar, senaryo: ContentScript | None,
    fikir: ContentIdea | None, simdi: datetime,
) -> Kayit:
    return Kayit(
        id=kayit.id,
        script_id=kayit.script_id,
        ne_zaman=kayit.scheduled_for,
        platform=senaryo.platform.value if senaryo else "?",
        baslik=fikir.title if fikir else "(içerik silinmiş)",
        kanca=(senaryo.hook or "")[:120] if senaryo else None,
        not_=kayit.notes,
        yayinlandi=kayit.published_at is not None,
        yayin_zamani=kayit.published_at,
        # Zamani gecti ama yayinlandi isaretlenmedi: kullanici gormeli.
        gecikti=kayit.published_at is None and kayit.scheduled_for < simdi,
    )


def ay_gorunumu(
    db: Session, workspace_id: uuid.UUID, *, yil: int, ay: int,
    simdi: datetime | None = None,
) -> dict:
    """Bir ayin takvimi: haftalara bolunmus gunler ve o gunun planlari."""
    an = simdi or datetime.now(UTC)

    ay_basi = datetime(yil, ay, 1, tzinfo=UTC)
    son_gun = _takvim.monthrange(yil, ay)[1]
    ay_sonu = datetime(yil, ay, son_gun, 23, 59, 59, tzinfo=UTC)

    satirlar = db.execute(
        select(ContentCalendar, ContentScript, ContentIdea)
        .outerjoin(ContentScript, ContentScript.id == ContentCalendar.script_id)
        .outerjoin(ContentIdea, ContentIdea.id == ContentScript.idea_id)
        .where(
            ContentCalendar.workspace_id == workspace_id,
            ContentCalendar.scheduled_for >= ay_basi,
            ContentCalendar.scheduled_for <= ay_sonu,
        )
        .order_by(ContentCalendar.scheduled_for)
    ).all()

    gune_gore: dict[date, list[Kayit]] = {}
    for kayit, senaryo, fikir in satirlar:
        gun = kayit.scheduled_for.date()
        gune_gore.setdefault(gun, []).append(
            _kayda_cevir(kayit, senaryo, fikir, an)
        )

    # Pazartesi ile baslayan haftalar.
    ilk = date(yil, ay, 1)
    baslangic = ilk - timedelta(days=ilk.weekday())
    haftalar: list[list[dict]] = []
    gun = baslangic
    while gun <= date(yil, ay, son_gun) or len(haftalar) * 7 < 1:
        hafta = []
        for _ in range(7):
            hafta.append({
                "tarih": gun,
                "bu_ay": gun.month == ay,
                "bugun": gun == an.date(),
                "kayitlar": gune_gore.get(gun, []),
            })
            gun += timedelta(days=1)
        haftalar.append(hafta)
        if gun > date(yil, ay, son_gun):
            break

    return {
        "yil": yil,
        "ay": ay,
        "haftalar": haftalar,
        "toplam": sum(len(v) for v in gune_gore.values()),
        "geciken": sum(
            1 for kayitlar in gune_gore.values() for k in kayitlar if k.gecikti
        ),
    }
