"""Panel sayfalari.

Sunucu tarafinda uretilen sade HTML. Ayri bir JavaScript uygulamasi
kullanilmadi - gerekcesi DECISIONS.md K-017'de.

Guvenlik: Her sayfa, kullanicinin o musteriye UYE oldugunu dogrular.
Uye degilse 404 doner (403 degil - 403, o musterinin varligini ele verirdi).
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.api.deps import DbSession
from app.core.security import create_token, verify_password
from app.models.content import ContentScript
from app.models.enums import ContentStatus, WorkspaceRole
from app.models.identity import User, Workspace, WorkspaceMember
from app.models.reporting import Report, ReportSection
from app.panel.auth import clear_session_cookie, current_user_from_cookie, set_session_cookie
from app.services.ai_runner import month_spend
from app.services.approvals import (
    ALLOWED_TRANSITIONS,
    REQUIRED_ROLE,
    ApprovalError,
    approval_history,
    can_publish,
    transition,
)

router = APIRouter(prefix="/panel", tags=["panel"])
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

STATUS_LABELS = {
    "draft": "Taslak",
    "internal_review": "İç inceleme",
    "client_review": "Müşteri incelemesi",
    "approved": "Onaylandı",
    "rejected": "Reddedildi",
    "scheduled": "Planlandı",
    "published": "Yayınlandı",
    "archived": "Arşivlendi",
}

ROLE_LABELS = {
    "owner": "Sahip",
    "admin": "Yönetici",
    "strategist": "Stratejist",
    "editor": "Editör",
    "viewer": "İzleyici",
}


def _giris_yonlendir() -> RedirectResponse:
    return RedirectResponse("/panel/giris", status_code=status.HTTP_303_SEE_OTHER)


def _uyelik(db, user: User, workspace_id: uuid.UUID) -> WorkspaceMember | None:
    return db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    ).scalar_one_or_none()


def _izinli_hedefler(mevcut: ContentStatus, rol: WorkspaceRole) -> list[str]:
    """Kullanicinin bu durumdan gidebilecegi durumlar.

    Yetkisi yetmeyen secenekler listede GOSTERILMEZ; kullanici
    yapamayacagi bir seyi denemek zorunda kalmaz.
    """
    sonuc = []
    for hedef in ALLOWED_TRANSITIONS.get(mevcut, set()):
        # Yayinlama kilidi kapali oldugu icin bu secenek hic sunulmaz.
        if hedef is ContentStatus.PUBLISHED:
            continue
        if rol.covers(REQUIRED_ROLE.get(hedef, WorkspaceRole.ADMIN)):
            sonuc.append(hedef.value)
    return sorted(sonuc)


# --- Giris / cikis -----------------------------------------------------------

@router.get("/giris", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"user": None})


@router.post("/giris")
def login_submit(
    request: Request,
    db: DbSession,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
):
    user = db.execute(
        select(User).where(User.email == email.lower())
    ).scalar_one_or_none()

    # Hatali e-posta ve hatali sifre AYNI mesaji verir.
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request, "login.html",
            {"user": None, "error": "E-posta veya şifre hatalı."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    yanit = RedirectResponse("/panel", status_code=status.HTTP_303_SEE_OTHER)
    set_session_cookie(yanit, create_token(user.id, "access"))
    return yanit


@router.post("/cikis")
def logout():
    yanit = RedirectResponse("/panel/giris", status_code=status.HTTP_303_SEE_OTHER)
    clear_session_cookie(yanit)
    return yanit


# --- Musteri listesi ---------------------------------------------------------

@router.get("", response_class=HTMLResponse)
def workspaces_page(request: Request, db: DbSession):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()

    satirlar = db.execute(
        select(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id)
        .order_by(Workspace.name)
    ).all()

    return templates.TemplateResponse(
        request, "workspaces.html",
        {
            "user": user,
            "memberships": [
                {"workspace": ws, "role_label": ROLE_LABELS.get(rol.value, rol.value)}
                for ws, rol in satirlar
            ],
        },
    )


# --- Musteri ekrani ----------------------------------------------------------

@router.get("/musteri/{workspace_id}", response_class=HTMLResponse)
def workspace_page(workspace_id: uuid.UUID, request: Request, db: DbSession):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()

    uyelik = _uyelik(db, user, workspace_id)
    if uyelik is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    ws = db.get(Workspace, workspace_id)
    bekleyen = [ContentStatus.INTERNAL_REVIEW, ContentStatus.CLIENT_REVIEW]

    return templates.TemplateResponse(
        request, "workspace.html",
        {
            "user": user,
            "workspace": ws,
            "role_label": ROLE_LABELS.get(uyelik.role.value, uyelik.role.value),
            "status_labels": STATUS_LABELS,
            "pending_scripts": db.execute(
                select(ContentScript).where(
                    ContentScript.workspace_id == workspace_id,
                    ContentScript.status.in_(bekleyen),
                ).order_by(ContentScript.created_at.desc()).limit(20)
            ).scalars().all(),
            "pending_reports": db.execute(
                select(Report).where(
                    Report.workspace_id == workspace_id,
                    Report.status.in_(bekleyen),
                ).order_by(Report.period_start.desc()).limit(20)
            ).scalars().all(),
            "scripts": db.execute(
                select(ContentScript).where(ContentScript.workspace_id == workspace_id)
                .order_by(ContentScript.created_at.desc()).limit(10)
            ).scalars().all(),
            "reports": db.execute(
                select(Report).where(Report.workspace_id == workspace_id)
                .order_by(Report.period_start.desc()).limit(10)
            ).scalars().all(),
            "ai_spent": float(month_spend(db, workspace_id)),
            "ai_budget": float(ws.ai_monthly_budget_usd),
            "ai_exceeded": float(month_spend(db, workspace_id)) >= float(ws.ai_monthly_budget_usd),
            "using_fake": get_fake_mode(),
        },
    )


def get_fake_mode() -> bool:
    from app.core.config import get_settings

    return get_settings().ai_provider_mode == "fake"


# --- Senaryo ekrani ----------------------------------------------------------

@router.get("/musteri/{workspace_id}/senaryo/{script_id}", response_class=HTMLResponse)
def script_page(
    workspace_id: uuid.UUID, script_id: uuid.UUID, request: Request, db: DbSession,
    message: str | None = None, error: str | None = None,
):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()

    uyelik = _uyelik(db, user, workspace_id)
    if uyelik is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    s = db.execute(
        select(ContentScript).where(
            ContentScript.id == script_id,
            ContentScript.workspace_id == workspace_id,
        )
    ).scalar_one_or_none()
    if s is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    _, gerekce = can_publish(db, workspace_id=workspace_id, script=s)

    return templates.TemplateResponse(
        request, "script.html",
        {
            "user": user,
            "workspace": db.get(Workspace, workspace_id),
            "script": s,
            "status_labels": STATUS_LABELS,
            "allowed_targets": _izinli_hedefler(s.status, uyelik.role),
            "publish_reason": gerekce,
            "history": approval_history(
                db, workspace_id=workspace_id,
                subject_type="content_script", subject_id=s.id,
            ),
            "message": message,
            "error": error,
        },
    )


@router.post("/musteri/{workspace_id}/senaryo/{script_id}/karar")
def script_decision(
    workspace_id: uuid.UUID, script_id: uuid.UUID, request: Request, db: DbSession,
    target: Annotated[str, Form()],
    comment: Annotated[str, Form()] = "",
):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()

    uyelik = _uyelik(db, user, workspace_id)
    if uyelik is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    s = db.execute(
        select(ContentScript).where(
            ContentScript.id == script_id,
            ContentScript.workspace_id == workspace_id,
        )
    ).scalar_one_or_none()
    if s is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    temel = f"/panel/musteri/{workspace_id}/senaryo/{script_id}"
    try:
        transition(
            db, workspace_id=workspace_id, actor_user_id=user.id,
            actor_role=uyelik.role, subject=s,
            target=ContentStatus(target), comment=comment or None,
        )
        db.commit()
    except (ApprovalError, ValueError) as exc:
        db.rollback()
        from urllib.parse import quote

        return RedirectResponse(f"{temel}?error={quote(str(exc))}", status_code=303)

    return RedirectResponse(f"{temel}?message=Karar+kaydedildi.", status_code=303)


# --- Rapor ekrani ------------------------------------------------------------

@router.get("/musteri/{workspace_id}/rapor/{report_id}", response_class=HTMLResponse)
def report_page(
    workspace_id: uuid.UUID, report_id: uuid.UUID, request: Request, db: DbSession,
    error: str | None = None,
):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()

    uyelik = _uyelik(db, user, workspace_id)
    if uyelik is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    r = db.execute(
        select(Report).where(Report.id == report_id, Report.workspace_id == workspace_id)
    ).scalar_one_or_none()
    if r is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    return templates.TemplateResponse(
        request, "report.html",
        {
            "user": user,
            "workspace": db.get(Workspace, workspace_id),
            "report": r,
            "sections": db.execute(
                select(ReportSection).where(ReportSection.report_id == r.id)
                .order_by(ReportSection.order_index)
            ).scalars().all(),
            "status_labels": STATUS_LABELS,
            "allowed_targets": _izinli_hedefler(r.status, uyelik.role),
            "error": error,
        },
    )


@router.post("/musteri/{workspace_id}/rapor/{report_id}/karar")
def report_decision(
    workspace_id: uuid.UUID, report_id: uuid.UUID, request: Request, db: DbSession,
    target: Annotated[str, Form()],
    comment: Annotated[str, Form()] = "",
):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()

    uyelik = _uyelik(db, user, workspace_id)
    if uyelik is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    r = db.execute(
        select(Report).where(Report.id == report_id, Report.workspace_id == workspace_id)
    ).scalar_one_or_none()
    if r is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    temel = f"/panel/musteri/{workspace_id}/rapor/{report_id}"
    try:
        transition(
            db, workspace_id=workspace_id, actor_user_id=user.id,
            actor_role=uyelik.role, subject=r,
            target=ContentStatus(target), comment=comment or None,
        )
        db.commit()
    except (ApprovalError, ValueError) as exc:
        db.rollback()
        from urllib.parse import quote

        return RedirectResponse(f"{temel}?error={quote(str(exc))}", status_code=303)

    return RedirectResponse(temel, status_code=303)
