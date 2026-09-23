"""Onay akisi testleri.

EN KRITIK TESTLER BURADA. Sistemin temel vaadi: insan onayi olmadan hicbir
sey yayinlanamaz. Bu dosya o vaadi korur.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models.brand import Brand
from app.models.content import ContentIdea, ContentScript
from app.models.enums import (
    ContentStatus,
    MediaType,
    PermissionPackage,
    Platform,
    ReportPeriod,
    WorkspaceRole,
)
from app.models.ops import Approval, AuditLog
from app.models.reporting import Report
from app.services.approvals import (
    ALLOWED_TRANSITIONS,
    ContentChangedSinceApproval,
    InsufficientRole,
    InvalidTransition,
    PublishingLocked,
    approval_history,
    can_publish,
    transition,
)
from tests.conftest import _ROL_PAKET


@pytest.fixture
def senaryo(db, make_workspace, make_user):
    ws = make_workspace(name="Onay Testi")
    user = make_user(email="onaylayan@ajans.com")
    marka = Brand(workspace_id=ws.id, name="Marka")
    db.add(marka)
    db.flush()
    fikir = ContentIdea(
        workspace_id=ws.id, brand_id=marka.id, title="Fikir",
        idea_fingerprint=uuid.uuid4().hex,
    )
    db.add(fikir)
    db.flush()
    s = ContentScript(
        workspace_id=ws.id, idea_id=fikir.id,
        platform=Platform.INSTAGRAM, format=MediaType.REEL,
        hook="Ornek kanca", spoken_script="Ornek metin", caption="Ornek aciklama",
        cta="Takip et", duration_seconds=20,
        status=ContentStatus.DRAFT, human_approval_required=True,
    )
    db.add(s)
    db.flush()
    return ws, user, s


def gecir(db, ws, user, s, hedef, rol=WorkspaceRole.OWNER, **kw):
    """Gecisi yapar.

    `rol`: geriye donuk uyumluluk. Yetki artik KULLANICIDA oldugu icin
    verilen rol, kullanicinin yetki paketine yazilir.
    """
    if rol is not None:
        user.permission_package = _ROL_PAKET[rol]
        db.flush()
    return transition(db, workspace_id=ws.id, actor=user, subject=s, target=hedef, **kw)


# ===========================================================================
# YAYIN KILIDI - sistemin en onemli vaadi
# ===========================================================================

def test_yayinlama_ilk_surumde_kapali(db, senaryo):
    """Insan onayi olmadan yayin YOK - ve ilk surumde hic yayin yok."""
    ws, user, s = senaryo
    gecir(db, ws, user, s, ContentStatus.INTERNAL_REVIEW)
    gecir(db, ws, user, s, ContentStatus.CLIENT_REVIEW)
    gecir(db, ws, user, s, ContentStatus.APPROVED)
    gecir(db, ws, user, s, ContentStatus.SCHEDULED)

    # Onaylanmis ve planlanmis olmasina RAGMEN yayinlanamaz.
    with pytest.raises(PublishingLocked):
        gecir(db, ws, user, s, ContentStatus.PUBLISHED)

    assert s.status is ContentStatus.SCHEDULED


def test_engellenen_yayin_denemesi_loglanir(db, senaryo, caplog):
    ws, user, s = senaryo
    for hedef in (ContentStatus.INTERNAL_REVIEW, ContentStatus.CLIENT_REVIEW,
                  ContentStatus.APPROVED, ContentStatus.SCHEDULED):
        gecir(db, ws, user, s, hedef)
    with pytest.raises(PublishingLocked):
        gecir(db, ws, user, s, ContentStatus.PUBLISHED)


def test_kilit_acilsa_bile_onaysiz_yayin_yapilamaz(db, senaryo, monkeypatch):
    """Ikinci koruma katmani: kilit acilsa bile onay kaydi sart."""
    from app.core.config import get_settings

    ws, user, s = senaryo
    gecir(db, ws, user, s, ContentStatus.INTERNAL_REVIEW)
    gecir(db, ws, user, s, ContentStatus.CLIENT_REVIEW)
    gecir(db, ws, user, s, ContentStatus.APPROVED)
    gecir(db, ws, user, s, ContentStatus.SCHEDULED)

    monkeypatch.setattr(get_settings(), "feature_publishing_enabled", True)

    # Onay kaydini sil - yayin yine engellenmelidir.
    for onay in db.execute(
        select(Approval).where(Approval.status == ContentStatus.APPROVED)
    ).scalars().all():
        db.delete(onay)
    db.flush()

    with pytest.raises(ContentChangedSinceApproval):
        gecir(db, ws, user, s, ContentStatus.PUBLISHED)


def test_onaydan_sonra_degisen_icerik_yayinlanamaz(db, senaryo, monkeypatch):
    """Onay, icerigin O HALINE verilmistir.

    Metin sonradan degistirilirse, onaylanmamis bir icerik yayinlanmis olurdu.
    """
    from app.core.config import get_settings

    ws, user, s = senaryo
    gecir(db, ws, user, s, ContentStatus.INTERNAL_REVIEW)
    gecir(db, ws, user, s, ContentStatus.CLIENT_REVIEW)
    gecir(db, ws, user, s, ContentStatus.APPROVED)
    gecir(db, ws, user, s, ContentStatus.SCHEDULED)

    monkeypatch.setattr(get_settings(), "feature_publishing_enabled", True)

    # Onaydan SONRA metin degistiriliyor.
    s.caption = "TAMAMEN FARKLI BIR ACIKLAMA"
    db.flush()

    with pytest.raises(ContentChangedSinceApproval):
        gecir(db, ws, user, s, ContentStatus.PUBLISHED)


def test_degismemis_icerik_kilit_acikken_yayinlanabilir(db, senaryo, monkeypatch):
    """Karsit test: koruma dogru calisiyorsa, degismemis icerik gecmeli."""
    from app.core.config import get_settings

    ws, user, s = senaryo
    for hedef in (ContentStatus.INTERNAL_REVIEW, ContentStatus.CLIENT_REVIEW,
                  ContentStatus.APPROVED, ContentStatus.SCHEDULED):
        gecir(db, ws, user, s, hedef)

    monkeypatch.setattr(get_settings(), "feature_publishing_enabled", True)
    sonuc = gecir(db, ws, user, s, ContentStatus.PUBLISHED)
    assert sonuc.new_status is ContentStatus.PUBLISHED


def test_can_publish_gerekceyi_soyler(db, senaryo):
    ws, user, s = senaryo
    olur, gerekce = can_publish(db, workspace_id=ws.id, script=s)
    assert olur is False
    assert "yayini insan yapar" in gerekce.lower()


# ===========================================================================
# Durum akisi
# ===========================================================================

def test_taslaktan_dogrudan_onaya_gecilemez(db, senaryo):
    """Inceleme adimlari atlanamaz."""
    ws, user, s = senaryo
    with pytest.raises(InvalidTransition):
        gecir(db, ws, user, s, ContentStatus.APPROVED)


def test_taslaktan_dogrudan_yayina_gecilemez(db, senaryo):
    ws, user, s = senaryo
    with pytest.raises(InvalidTransition):
        gecir(db, ws, user, s, ContentStatus.PUBLISHED)


def test_normal_akis_calisir(db, senaryo):
    ws, user, s = senaryo
    assert gecir(db, ws, user, s, ContentStatus.INTERNAL_REVIEW).new_status is ContentStatus.INTERNAL_REVIEW
    assert gecir(db, ws, user, s, ContentStatus.CLIENT_REVIEW).new_status is ContentStatus.CLIENT_REVIEW
    assert gecir(db, ws, user, s, ContentStatus.APPROVED).new_status is ContentStatus.APPROVED


def test_reddedilen_icerik_taslaga_donebilir(db, senaryo):
    ws, user, s = senaryo
    gecir(db, ws, user, s, ContentStatus.INTERNAL_REVIEW)
    gecir(db, ws, user, s, ContentStatus.REJECTED)
    gecir(db, ws, user, s, ContentStatus.DRAFT)
    assert s.status is ContentStatus.DRAFT


def test_onay_geri_cekilebilir(db, senaryo):
    ws, user, s = senaryo
    gecir(db, ws, user, s, ContentStatus.INTERNAL_REVIEW)
    gecir(db, ws, user, s, ContentStatus.CLIENT_REVIEW)
    gecir(db, ws, user, s, ContentStatus.APPROVED)
    gecir(db, ws, user, s, ContentStatus.INTERNAL_REVIEW)
    assert s.status is ContentStatus.INTERNAL_REVIEW


def test_arsivlenen_icerik_geri_donemez(db, senaryo):
    ws, user, s = senaryo
    gecir(db, ws, user, s, ContentStatus.ARCHIVED)
    assert ALLOWED_TRANSITIONS[ContentStatus.ARCHIVED] == set()
    with pytest.raises(InvalidTransition):
        gecir(db, ws, user, s, ContentStatus.DRAFT)


def test_tum_durumlar_akista_tanimli():
    """Tanimsiz bir durum kalmamali."""
    for durum in ContentStatus:
        assert durum in ALLOWED_TRANSITIONS, f"{durum.value} akista tanimsiz"


# ===========================================================================
# Yetkiler
# ===========================================================================

def test_izleyici_hicbir_gecis_yapamaz(db, senaryo):
    ws, user, s = senaryo
    with pytest.raises(InsufficientRole):
        gecir(db, ws, user, s, ContentStatus.INTERNAL_REVIEW, rol=WorkspaceRole.VIEWER)


def test_editor_onay_veremez(db, senaryo):
    """Onay vermek yonetici yetkisi ister."""
    ws, user, s = senaryo
    gecir(db, ws, user, s, ContentStatus.INTERNAL_REVIEW, rol=WorkspaceRole.EDITOR)
    gecir(db, ws, user, s, ContentStatus.CLIENT_REVIEW, rol=WorkspaceRole.STRATEGIST)
    with pytest.raises(InsufficientRole):
        gecir(db, ws, user, s, ContentStatus.APPROVED, rol=WorkspaceRole.EDITOR)


def test_editor_incelemeye_gonderebilir(db, senaryo):
    ws, user, s = senaryo
    gecir(db, ws, user, s, ContentStatus.INTERNAL_REVIEW, rol=WorkspaceRole.EDITOR)
    assert s.status is ContentStatus.INTERNAL_REVIEW


def test_yonetici_onay_verebilir(db, senaryo):
    ws, user, s = senaryo
    gecir(db, ws, user, s, ContentStatus.INTERNAL_REVIEW)
    gecir(db, ws, user, s, ContentStatus.CLIENT_REVIEW)
    gecir(db, ws, user, s, ContentStatus.APPROVED, rol=WorkspaceRole.ADMIN)
    assert s.status is ContentStatus.APPROVED


# ===========================================================================
# Kayit ve izlenebilirlik
# ===========================================================================

def test_her_gecis_onay_kaydi_olusturur(db, senaryo):
    ws, user, s = senaryo
    gecir(db, ws, user, s, ContentStatus.INTERNAL_REVIEW, comment="incelemeye aldim")

    onay = db.execute(
        select(Approval).where(Approval.subject_id == s.id)
    ).scalars().one()
    assert onay.decided_by_user_id == user.id
    assert onay.decided_at is not None
    assert onay.comment == "incelemeye aldim"
    assert onay.snapshot["hook"] == "Ornek kanca"


def test_her_gecis_denetim_kaydina_yazilir(db, senaryo):
    """Kim ne zaman neyi degistirdi - silinmez kayit."""
    ws, user, s = senaryo
    gecir(db, ws, user, s, ContentStatus.INTERNAL_REVIEW)

    kayit = db.execute(
        select(AuditLog).where(AuditLog.subject_id == s.id)
    ).scalars().one()
    assert kayit.action == "content_script.status_changed"
    assert kayit.actor_user_id == user.id
    assert kayit.details["from"] == "draft"
    assert kayit.details["to"] == "internal_review"


def test_onay_gecmisi_sirayla_doner(db, senaryo):
    ws, user, s = senaryo
    gecir(db, ws, user, s, ContentStatus.INTERNAL_REVIEW)
    gecir(db, ws, user, s, ContentStatus.CLIENT_REVIEW)
    gecir(db, ws, user, s, ContentStatus.APPROVED)

    gecmis = approval_history(
        db, workspace_id=ws.id, subject_type="content_script", subject_id=s.id
    )
    assert [g.status.value for g in gecmis] == [
        "internal_review", "client_review", "approved"
    ]


def test_onay_kayitlari_dogru_musteriye_yazilir(db, senaryo, make_workspace):
    ws, user, s = senaryo
    diger = make_workspace(name="Ilgisiz")
    gecir(db, ws, user, s, ContentStatus.INTERNAL_REVIEW)
    db.flush()

    from sqlalchemy import func

    for model in (Approval, AuditLog):
        sayi = db.execute(
            select(func.count()).select_from(model)
            .where(model.workspace_id == diger.id)
        ).scalar_one()
        assert sayi == 0


# ===========================================================================
# Raporlar da onaydan gecer
# ===========================================================================

def test_rapor_da_onay_akisindan_gecer(db, make_workspace, make_user):
    ws = make_workspace(name="Rapor Onayi")
    user = make_user(email="rapor@ajans.com")
    user.permission_package = PermissionPackage.ADMIN
    r = Report(
        workspace_id=ws.id, period=ReportPeriod.DAILY,
        period_start=datetime.now(UTC).date(), period_end=datetime.now(UTC).date(),
        title="Test raporu", status=ContentStatus.DRAFT,
    )
    db.add(r)
    db.flush()

    sonuc = transition(
        db, workspace_id=ws.id, actor=user, subject=r,
        target=ContentStatus.INTERNAL_REVIEW,
    )
    assert sonuc.subject_type == "report"
    assert r.status is ContentStatus.INTERNAL_REVIEW
