"""Yetki ayarlari sayfasi.

Her musteri icin, her rolun neyi yapip yapamayacagi buradan ayarlanir.

IKI KURAL EKRANDA DA GECERLI:
- Sahip satiri KILITLIDIR. Sahibin izni kisitlanamaz; aksi halde musteri
  yonetilemez hale gelirdi.
- Kendi yetkinizi duzenleyemezsiniz. Kendini kilitleyen bir degisiklik
  yapilamasin diye.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.deps import DbSession
from app.models.enums import WorkspaceRole
from app.models.identity import Workspace
from app.panel.auth import current_user_from_cookie
from app.panel.ortak import uyelik_bul
from app.services.denetim import kaydet
from app.services.yetkiler import (
    GRUPLAR,
    IZINLER,
    KISITLANAMAZ_ROL,
    YetkiHatasi,
    izin_var_mi,
    izinleri_yaz,
    matris,
    varsayilana_don,
)

router = APIRouter(prefix="/panel/musteri/{workspace_id}/yetkiler", tags=["panel"])
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

ROL_ETIKETLERI = {
    "owner": "Sahip",
    "admin": "Yönetici",
    "strategist": "Stratejist",
    "editor": "Editör",
    "viewer": "İzleyici",
}


def _giris_yonlendir() -> RedirectResponse:
    return RedirectResponse("/panel/giris", status_code=status.HTTP_303_SEE_OTHER)


def _sayfa(request, db, user, uyelik, workspace, *, error=None, ok=None, kod=200):
    satirlar = matris(db, workspace.id)

    gruplu = []
    for grup in GRUPLAR:
        gruplu.append({
            "ad": grup,
            "izinler": [s for s in satirlar if s["grup"] == grup],
        })

    return templates.TemplateResponse(
        request, "permissions.html",
        {
            "user": user,
            "aktif": "yetkiler",
            "workspace": workspace,
            "yol": "Yetkiler",
            "gruplar": gruplu,
            "roller": [
                {
                    "deger": r.value,
                    "etiket": ROL_ETIKETLERI.get(r.value, r.value),
                    "kilitli": r is KISITLANAMAZ_ROL,
                    "kendi_rolum": r is uyelik.role,
                }
                for r in WorkspaceRole
            ],
            "duzenleyebilir": izin_var_mi(
                db, workspace.id, uyelik.role, "yetki.duzenle"
            ),
            "error": error,
            "ok": ok,
        },
        status_code=kod,
    )


@router.get("", response_class=HTMLResponse)
def yetkiler_sayfasi(workspace_id: uuid.UUID, request: Request, db: DbSession):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()
    uyelik = uyelik_bul(request, db, user, workspace_id)
    if uyelik is None:
        return HTMLResponse("Bulunamadı.", status_code=404)
    return _sayfa(
        request, db, user, uyelik, db.get(Workspace, workspace_id)
    )


@router.post("/kaydet")
def yetkileri_kaydet(
    workspace_id: uuid.UUID,
    request: Request,
    db: DbSession,
    rol: Annotated[str, Form()],
    izin: Annotated[list[str], Form()] = [],  # noqa: B006
):
    """Bir rolun izinlerini yeniden yazar."""
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()
    uyelik = uyelik_bul(request, db, user, workspace_id)
    if uyelik is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    workspace = db.get(Workspace, workspace_id)
    if not izin_var_mi(db, workspace_id, uyelik.role, "yetki.duzenle"):
        return _sayfa(
            request, db, user, uyelik, workspace,
            error="Yetki ayarlarını değiştirme izniniz yok.",
            kod=status.HTTP_403_FORBIDDEN,
        )

    try:
        hedef_rol = WorkspaceRole(rol)
    except ValueError:
        return _sayfa(
            request, db, user, uyelik, workspace,
            error="Geçersiz rol.", kod=status.HTTP_400_BAD_REQUEST,
        )

    # Kendi rolunun izinlerini duzenlemek, kendini kilitlemeye yol acabilir.
    if hedef_rol is uyelik.role:
        return _sayfa(
            request, db, user, uyelik, workspace,
            error=(
                "Kendi rolünüzün izinlerini değiştiremezsiniz. "
                "Bunu sizden yetkili biri yapmalıdır."
            ),
            kod=status.HTTP_400_BAD_REQUEST,
        )

    try:
        izinleri_yaz(db, workspace_id, hedef_rol, set(izin))
    except YetkiHatasi as hata:
        db.rollback()
        return _sayfa(
            request, db, user, uyelik, workspace,
            error=str(hata), kod=status.HTTP_400_BAD_REQUEST,
        )

    kaydet(
        db, action="yetki.duzenle", actor_user_id=user.id,
        workspace_id=workspace_id, request=request,
        details={"rol": hedef_rol.value, "izin_sayisi": len(set(izin))},
    )
    db.commit()
    return _sayfa(
        request, db, user, uyelik, workspace,
        ok=f"{ROL_ETIKETLERI.get(rol, rol)} yetkileri güncellendi.",
    )


@router.post("/varsayilan")
def varsayilana_donder(
    workspace_id: uuid.UUID,
    request: Request,
    db: DbSession,
    rol: Annotated[str, Form()],
):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()
    uyelik = uyelik_bul(request, db, user, workspace_id)
    if uyelik is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    workspace = db.get(Workspace, workspace_id)
    if not izin_var_mi(db, workspace_id, uyelik.role, "yetki.duzenle"):
        return _sayfa(
            request, db, user, uyelik, workspace,
            error="Yetki ayarlarını değiştirme izniniz yok.",
            kod=status.HTTP_403_FORBIDDEN,
        )

    try:
        hedef_rol = WorkspaceRole(rol)
    except ValueError:
        return _sayfa(
            request, db, user, uyelik, workspace,
            error="Geçersiz rol.", kod=status.HTTP_400_BAD_REQUEST,
        )

    varsayilana_don(db, workspace_id, hedef_rol)
    kaydet(
        db, action="yetki.varsayilana_don", actor_user_id=user.id,
        workspace_id=workspace_id, request=request,
        details={"rol": hedef_rol.value},
    )
    db.commit()
    return _sayfa(
        request, db, user, uyelik, workspace,
        ok=f"{ROL_ETIKETLERI.get(rol, rol)} varsayılan yetkilere döndürüldü.",
    )


# Sablonun izin listesini gezebilmesi icin.
TUM_IZINLER = IZINLER
