"""Yayin takvimi sayfasi.

Sistem bu surumde HICBIR SEYI KENDISI PAYLASMAZ. Takvim, ne zaman ne
paylasilacagini planlamak ve paylasildiginda isaretlemek icindir.
Bu, ekranda da acikca yazar.
"""

from __future__ import annotations

import datetime as dt
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.api.deps import DbSession
from app.models.identity import Workspace, WorkspaceMember
from app.panel.auth import current_user_from_cookie
from app.services.denetim import kaydet
from app.services.takvim import (
    TakvimHatasi,
    ay_gorunumu,
    kaldir,
    planla,
    planlanabilir_icerikler,
    yayinlandi_isaretle,
)
from app.services.yetkiler import izin_var_mi

router = APIRouter(prefix="/panel/musteri/{workspace_id}/takvim", tags=["panel"])
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

AY_ADLARI = [
    "", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]
GUN_ADLARI = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]


def _giris_yonlendir() -> RedirectResponse:
    return RedirectResponse("/panel/giris", status_code=status.HTTP_303_SEE_OTHER)


def _uyelik(db, user, workspace_id: uuid.UUID) -> WorkspaceMember | None:
    return db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    ).scalar_one_or_none()


def _sayfa(
    request, db, user, uyelik, workspace, *,
    yil=None, ay=None, error=None, ok=None, kod=200,
):
    bugun = dt.date.today()
    yil = yil or bugun.year
    ay = ay or bugun.month

    gorunum = ay_gorunumu(db, workspace.id, yil=yil, ay=ay)

    onceki = dt.date(yil, ay, 1) - dt.timedelta(days=1)
    son_gun = gorunum["haftalar"][-1][-1]["tarih"]
    sonraki = dt.date(yil, ay, 28) + dt.timedelta(days=7)

    return templates.TemplateResponse(
        request, "calendar.html",
        {
            "user": user,
            "aktif": "takvim",
            "workspace": workspace,
            "yol": "Takvim",
            "gorunum": gorunum,
            "ay_adi": AY_ADLARI[ay],
            "gun_adlari": GUN_ADLARI,
            "onceki": {"yil": onceki.year, "ay": onceki.month},
            "sonraki": {"yil": sonraki.year, "ay": sonraki.month},
            "bekleyenler": planlanabilir_icerikler(db, workspace.id),
            "planlayabilir": izin_var_mi(db, workspace.id, uyelik.role, "takvim.planla"),
            "son_gun": son_gun,
            "error": error,
            "ok": ok,
        },
        status_code=kod,
    )


@router.get("", response_class=HTMLResponse)
def takvim_sayfasi(
    workspace_id: uuid.UUID, request: Request, db: DbSession,
    yil: int = 0, ay: int = 0,
):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()
    uyelik = _uyelik(db, user, workspace_id)
    if uyelik is None:
        return HTMLResponse("Bulunamadı.", status_code=404)
    if not izin_var_mi(db, workspace_id, uyelik.role, "takvim.gor"):
        return HTMLResponse("Bulunamadı.", status_code=404)

    if ay and not 1 <= ay <= 12:
        ay = 0
    return _sayfa(
        request, db, user, uyelik, db.get(Workspace, workspace_id),
        yil=yil or None, ay=ay or None,
    )


def _yetki_gerek(request, db, workspace_id, izin: str):
    """(user, uyelik, workspace) veya hata yaniti doner."""
    user = current_user_from_cookie(request, db)
    if user is None:
        return None, None, None, _giris_yonlendir()
    uyelik = _uyelik(db, user, workspace_id)
    if uyelik is None:
        return None, None, None, HTMLResponse("Bulunamadı.", status_code=404)
    workspace = db.get(Workspace, workspace_id)
    if not izin_var_mi(db, workspace_id, uyelik.role, izin):
        return user, uyelik, workspace, None
    return user, uyelik, workspace, "izinli"


@router.post("/planla")
def takvime_ekle(
    workspace_id: uuid.UUID,
    request: Request,
    db: DbSession,
    script_id: Annotated[uuid.UUID, Form()],
    tarih: Annotated[str, Form()],
    saat: Annotated[str, Form()],
    notlar: Annotated[str, Form()] = "",
):
    user, uyelik, workspace, durum = _yetki_gerek(
        request, db, workspace_id, "takvim.planla"
    )
    if durum is None:
        return _sayfa(
            request, db, user, uyelik, workspace,
            error="Takvime içerik yerleştirme izniniz yok.",
            kod=status.HTTP_403_FORBIDDEN,
        )
    if durum != "izinli":
        return durum

    try:
        ne_zaman = dt.datetime.fromisoformat(f"{tarih}T{saat}").replace(tzinfo=dt.UTC)
    except ValueError:
        return _sayfa(
            request, db, user, uyelik, workspace,
            error="Tarih veya saat okunamadı.", kod=status.HTTP_400_BAD_REQUEST,
        )

    try:
        planla(
            db, workspace_id=workspace_id, script_id=script_id,
            ne_zaman=ne_zaman, planlayan_user_id=user.id,
            notlar=notlar.strip() or None,
        )
    except TakvimHatasi as hata:
        db.rollback()
        return _sayfa(
            request, db, user, uyelik, workspace,
            error=str(hata), kod=status.HTTP_400_BAD_REQUEST,
        )

    kaydet(
        db, action="takvim.planla", actor_user_id=user.id,
        workspace_id=workspace_id, subject_type="content_script",
        subject_id=script_id, request=request,
        details={"ne_zaman": ne_zaman.isoformat()},
    )
    db.commit()
    return _sayfa(
        request, db, user, uyelik, workspace,
        yil=ne_zaman.year, ay=ne_zaman.month,
        ok="İçerik takvime eklendi.",
    )


@router.post("/kaldir")
def takvimden_cikar(
    workspace_id: uuid.UUID,
    request: Request,
    db: DbSession,
    kayit_id: Annotated[uuid.UUID, Form()],
):
    user, uyelik, workspace, durum = _yetki_gerek(
        request, db, workspace_id, "takvim.planla"
    )
    if durum is None:
        return _sayfa(
            request, db, user, uyelik, workspace,
            error="Takvimi değiştirme izniniz yok.", kod=status.HTTP_403_FORBIDDEN,
        )
    if durum != "izinli":
        return durum

    try:
        kaldir(db, workspace_id=workspace_id, kayit_id=kayit_id)
    except TakvimHatasi as hata:
        db.rollback()
        return _sayfa(
            request, db, user, uyelik, workspace,
            error=str(hata), kod=status.HTTP_400_BAD_REQUEST,
        )

    kaydet(
        db, action="takvim.kaldir", actor_user_id=user.id,
        workspace_id=workspace_id, subject_type="content_calendar",
        subject_id=kayit_id, request=request,
    )
    db.commit()
    return _sayfa(
        request, db, user, uyelik, workspace, ok="Plan takvimden kaldırıldı."
    )


@router.post("/yayinlandi")
def yayinlandi(
    workspace_id: uuid.UUID,
    request: Request,
    db: DbSession,
    kayit_id: Annotated[uuid.UUID, Form()],
):
    """Kullanici paylasimi yapti; takvim gercegi yansitsin.

    SISTEM PAYLASMAZ. Bu yalnizca bir kayittir.
    """
    user, uyelik, workspace, durum = _yetki_gerek(
        request, db, workspace_id, "takvim.planla"
    )
    if durum is None:
        return _sayfa(
            request, db, user, uyelik, workspace,
            error="Takvimi değiştirme izniniz yok.", kod=status.HTTP_403_FORBIDDEN,
        )
    if durum != "izinli":
        return durum

    try:
        yayinlandi_isaretle(
            db, workspace_id=workspace_id, kayit_id=kayit_id,
            isaretleyen_user_id=user.id,
        )
    except TakvimHatasi as hata:
        db.rollback()
        return _sayfa(
            request, db, user, uyelik, workspace,
            error=str(hata), kod=status.HTTP_400_BAD_REQUEST,
        )

    kaydet(
        db, action="takvim.yayinlandi", actor_user_id=user.id,
        workspace_id=workspace_id, subject_type="content_calendar",
        subject_id=kayit_id, request=request,
    )
    db.commit()
    return _sayfa(
        request, db, user, uyelik, workspace,
        ok="Yayınlandı olarak işaretlendi.",
    )
