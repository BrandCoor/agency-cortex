"""Insan onay akisi.

SISTEMIN EN ONEMLI GUVENLIK KILIDI BURADADIR.

Hicbir icerik, rapor veya mesaj insan onayi olmadan yayinlanamaz. Bu kural
tek bir yerde uygulanir; boylece hicbir cagri yolu kilidi atlayamaz.

DURUM AKISI:
    draft -> internal_review -> client_review -> approved -> scheduled -> published
                     |                |              |
                     v                v              v
                 rejected         rejected       (geri cekilebilir)

ONAY ANINDA NE OLUR:
Icerigin o anki hali "snapshot" olarak saklanir. Icerik sonradan
degistirilirse, onaylanan sey ile yayinlanacak sey arasindaki fark
tespit edilebilir. Onay, icerigin O HALINE verilmistir.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.base import canonical_hash
from app.core.config import get_settings
from app.core.logging_config import get_logger
from app.models.content import ContentScript
from app.models.enums import ContentStatus
from app.models.ops import Approval, AuditLog
from app.models.reporting import Report

log = get_logger("approvals")


class ApprovalError(Exception):
    """Onay akisindaki tum hatalarin atasi."""


class InvalidTransition(ApprovalError):
    """Bu durumdan o duruma gecilemez."""

    def __init__(self, current: ContentStatus, target: ContentStatus) -> None:
        izinli = ALLOWED_TRANSITIONS.get(current, set())
        super().__init__(
            f"'{current.value}' durumundan '{target.value}' durumuna gecilemez. "
            f"Bu durumdan gecilebilecekler: {sorted(s.value for s in izinli) or 'yok'}"
        )
        self.current = current
        self.target = target


class InsufficientRole(ApprovalError):
    """Bu gecis icin yetki yetersiz."""

    def __init__(self, required: str, target: ContentStatus) -> None:
        super().__init__(
            f"'{target.value}' durumuna gecirmek icin '{required}' "
            f"izni gerekir. Bu izin hesabiniza verilmemis."
        )
        self.required = required


class PublishingLocked(ApprovalError):
    """Yayin kilidi kapali.

    Ilk surumde bu kilit HER ZAMAN kapalidir.
    """


class ContentChangedSinceApproval(ApprovalError):
    """Icerik onaydan sonra degistirilmis.

    Onay, icerigin o anki haline verilmistir. Degisen icerik yeniden
    onaylanmalidir; aksi halde onaylanmamis bir metin yayinlanabilirdi.
    """


# Hangi durumdan hangi duruma gecilebilir.
ALLOWED_TRANSITIONS: dict[ContentStatus, set[ContentStatus]] = {
    ContentStatus.DRAFT: {
        ContentStatus.INTERNAL_REVIEW,
        ContentStatus.ARCHIVED,
    },
    ContentStatus.INTERNAL_REVIEW: {
        ContentStatus.CLIENT_REVIEW,
        ContentStatus.REJECTED,
        ContentStatus.DRAFT,
        ContentStatus.ARCHIVED,
    },
    ContentStatus.CLIENT_REVIEW: {
        ContentStatus.APPROVED,
        ContentStatus.REJECTED,
        ContentStatus.INTERNAL_REVIEW,
        ContentStatus.ARCHIVED,
    },
    ContentStatus.APPROVED: {
        ContentStatus.SCHEDULED,
        # Onay geri cekilebilir.
        ContentStatus.INTERNAL_REVIEW,
        ContentStatus.ARCHIVED,
    },
    ContentStatus.SCHEDULED: {
        ContentStatus.PUBLISHED,
        # Yayindan once geri cekilebilir.
        ContentStatus.APPROVED,
        ContentStatus.ARCHIVED,
    },
    ContentStatus.REJECTED: {
        ContentStatus.DRAFT,
        ContentStatus.ARCHIVED,
    },
    # Yayinlanan icerik yalnizca arsivlenebilir; gecmise donulmez.
    ContentStatus.PUBLISHED: {ContentStatus.ARCHIVED},
    ContentStatus.ARCHIVED: set(),
}

# Her gecis icin gereken IZIN.
#
# ONCEDEN burada sabit bir ROL vardi ve degistirilemezdi. Artik her gecis
# bir izne baglidir; izinler ise musteri basina panelden ayarlanabilir
# (bkz. services/yetkiler.py).
#
# VARSAYILAN dagitim, eski rol tablosunu BIREBIR tekrar eder:
#   icerik.duzenle    -> EDITOR+      (eski: DRAFT, INTERNAL_REVIEW)
#   icerik.onaya_sun  -> STRATEGIST+  (eski: CLIENT_REVIEW, REJECTED)
#   icerik.onayla     -> ADMIN+       (eski: APPROVED, PUBLISHED, ARCHIVED)
#   takvim.planla     -> STRATEGIST+  (eski: SCHEDULED)
# Yani bu degisiklikle hic kimsenin yetkisi artmadi veya azalmadi.
IZIN_ICERIK: dict[ContentStatus, str] = {
    ContentStatus.DRAFT: "icerik.duzenle",
    ContentStatus.INTERNAL_REVIEW: "icerik.duzenle",
    ContentStatus.CLIENT_REVIEW: "icerik.onaya_sun",
    ContentStatus.REJECTED: "icerik.onaya_sun",
    ContentStatus.APPROVED: "icerik.onayla",
    ContentStatus.ARCHIVED: "icerik.onayla",
    ContentStatus.PUBLISHED: "icerik.onayla",
    # Takvime koymak takvim iznidir; icerik izni degil.
    ContentStatus.SCHEDULED: "takvim.planla",
}

#: Rapor gecisleri. Ayni mantik, rapor izinleriyle.
IZIN_RAPOR: dict[ContentStatus, str] = {
    ContentStatus.DRAFT: "rapor.hazirla",
    ContentStatus.INTERNAL_REVIEW: "rapor.hazirla",
    ContentStatus.CLIENT_REVIEW: "rapor.sun",
    ContentStatus.REJECTED: "rapor.sun",
    ContentStatus.APPROVED: "rapor.onayla",
    ContentStatus.ARCHIVED: "rapor.onayla",
    ContentStatus.PUBLISHED: "rapor.onayla",
    ContentStatus.SCHEDULED: "rapor.onayla",
}


def gerekli_izin(tur: str, target: ContentStatus) -> str:
    """Bu gecis icin hangi izin gerekir?"""
    tablo = IZIN_RAPOR if tur == "report" else IZIN_ICERIK
    # Bilinmeyen bir durum SESSIZCE gecmesin: en dar izne dusulur.
    return tablo.get(target, "icerik.onayla" if tur != "report" else "rapor.onayla")


def script_snapshot(script: ContentScript) -> dict[str, Any]:
    """Onay aninda icerigin kaydi.

    Sonradan degisiklik yapilirsa fark edilebilsin diye tutulur.
    """
    return {
        "platform": script.platform.value,
        "format": script.format.value,
        "hook": script.hook,
        "spoken_script": script.spoken_script,
        "caption": script.caption,
        "cta": script.cta,
        "on_screen_text": list(script.on_screen_text or []),
        "duration_seconds": script.duration_seconds,
        "claims_to_verify": list(script.claims_to_verify or []),
    }


def report_snapshot(report: Report) -> dict[str, Any]:
    return {
        "period": report.period.value,
        "period_start": report.period_start.isoformat(),
        "period_end": report.period_end.isoformat(),
        "title": report.title,
        "assumptions": list(report.assumptions or []),
        "data_quality_notes": list(report.data_quality_notes or []),
    }


@dataclass
class TransitionResult:
    subject_type: str
    subject_id: uuid.UUID
    previous_status: ContentStatus
    new_status: ContentStatus
    approval_id: uuid.UUID


def _check_izin(db: Session, actor, tur: str, target: ContentStatus) -> None:
    """Bu KULLANICI bu gecisi yapabilir mi?"""
    from app.services.yetkiler import izin_var_mi

    izin = gerekli_izin(tur, target)
    if not izin_var_mi(db, actor, izin):
        raise InsufficientRole(izin, target)


def transition(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    actor,
    subject: ContentScript | Report,
    target: ContentStatus,
    comment: str | None = None,
    request_id: str | None = None,
) -> TransitionResult:
    """Bir icerigi veya raporu yeni duruma gecirir.

    Tum kontroller BURADA yapilir; cagiran katmanda degil. Boylece hicbir
    yol kilidi atlayamaz.
    """
    settings = get_settings()
    mevcut = subject.status

    # 1) Gecis gecerli mi?
    if target not in ALLOWED_TRANSITIONS.get(mevcut, set()):
        raise InvalidTransition(mevcut, target)

    tur = "content_script" if isinstance(subject, ContentScript) else "report"

    # 2) Yetki yeterli mi? (kullanicinin kendi izinlerine bakar)
    _check_izin(db, actor, tur, target)

    anlik = (
        script_snapshot(subject) if isinstance(subject, ContentScript)
        else report_snapshot(subject)
    )

    # 3) YAYIN KILIDI - ilk surumde her zaman kapali
    if target is ContentStatus.PUBLISHED:
        if not settings.feature_publishing_enabled:
            log.warning(
                "yayin_denemesi_engellendi",
                workspace_id=str(workspace_id),
                subject_type=tur,
                subject_id=str(subject.id),
                actor_user_id=str(actor.id),
            )
            raise PublishingLocked(
                "Yayinlama kapali. Ilk surumde icerik sistem tarafindan "
                "yayinlanmaz; yayini insan yapar."
            )

        # 4) Icerik onaydan sonra degisti mi?
        onay = db.execute(
            select(Approval).where(
                Approval.workspace_id == workspace_id,
                Approval.subject_type == tur,
                Approval.subject_id == subject.id,
                Approval.status == ContentStatus.APPROVED,
            ).order_by(Approval.decided_at.desc())
        ).scalars().first()

        if onay is None:
            raise ContentChangedSinceApproval(
                "Bu icerik icin onay kaydi bulunamadi."
            )
        if canonical_hash(onay.snapshot) != canonical_hash(anlik):
            raise ContentChangedSinceApproval(
                "Icerik onaylandiktan sonra degistirilmis. Yeniden onay gerekir."
            )

    simdi = datetime.now(UTC)
    onceki = subject.status
    subject.status = target

    kayit = Approval(
        workspace_id=workspace_id,
        subject_type=tur,
        subject_id=subject.id,
        status=target,
        decided_by_user_id=actor.id,
        decided_at=simdi,
        comment=comment,
        snapshot=anlik,
    )
    db.add(kayit)

    db.add(
        AuditLog(
            workspace_id=workspace_id,
            actor_user_id=actor.id,
            action=f"{tur}.status_changed",
            subject_type=tur,
            subject_id=subject.id,
            occurred_at=simdi,
            request_id=request_id,
            details={
                "from": onceki.value,
                "to": target.value,
                "comment": comment,
            },
        )
    )
    db.flush()

    log.info(
        "durum_degisti",
        workspace_id=str(workspace_id),
        subject_type=tur,
        subject_id=str(subject.id),
        from_status=onceki.value,
        to_status=target.value,
        actor_user_id=str(actor.id),
    )

    return TransitionResult(
        subject_type=tur,
        subject_id=subject.id,
        previous_status=onceki,
        new_status=target,
        approval_id=kayit.id,
    )


def approval_history(
    db: Session, *, workspace_id: uuid.UUID, subject_type: str, subject_id: uuid.UUID
) -> list[Approval]:
    """Bir icerigin onay gecmisi.

    Onay ekraninda degisiklik gecmisi gorunmelidir.
    """
    return list(
        db.execute(
            select(Approval)
            .where(
                Approval.workspace_id == workspace_id,
                Approval.subject_type == subject_type,
                Approval.subject_id == subject_id,
            )
            .order_by(Approval.decided_at.asc())
        ).scalars()
    )


def can_publish(db: Session, *, workspace_id: uuid.UUID, script: ContentScript) -> tuple[bool, str]:
    """Bu icerik yayinlanabilir mi? (cevap, gerekce)

    Panelde kullaniciya neden yayinlanamadigini gostermek icin.
    """
    settings = get_settings()
    if not settings.feature_publishing_enabled:
        return False, "Yayinlama ilk surumde kapalidir; yayini insan yapar."
    if script.status is not ContentStatus.SCHEDULED:
        return False, f"Icerik '{script.status.value}' durumunda; once planlanmali."
    return True, "Yayinlanabilir."
