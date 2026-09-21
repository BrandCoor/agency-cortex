"""Kullanici yonetimi sayfasi (sistem yoneticisi).

Bu sayfa SISTEM genelindeki hesaplari yonetir: kim giris yapabilir, kim
sistem yoneticisidir, kim pasiftir. Bir musterinin ekibindeki YETKI ise
ayri bir yerdedir (Musteri > Ekip), cunku kapsamlari farklidir.

SIFRE BU SAYFADAN BELIRLENMEZ. Yonetici tek kullanimlik bir bag uretir,
kullanici sifresini kendi belirler. Boylece sifre ne ekranda gorunur, ne
kopyalanirken bozulur, ne de yoneticinin eline gecer.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbSession
from app.core.config import get_settings
from app.models.identity import User, Workspace, WorkspaceMember
from app.panel.auth import current_user_from_cookie
from app.services.denetim import kaydet
from app.services.kullanicilar import (
    KullaniciHatasi,
    kullanici_guncelle,
    kullanici_olustur,
    kullanici_sil,
)
from app.services.sifre_sifirlama import jeton_uret

router = APIRouter(prefix="/panel/kullanicilar", tags=["panel"])
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

#: Yeni hesabin sifre belirleme bagi bu kadar sure gecerlidir.
#: Kisa tutmak kullaniciyi magdur ediyordu; asil koruma bagin TEK
#: KULLANIMLIK olmasidir, suresinin kisaligi degil.
BAG_OMUR_SAAT = 24

ROL_ETIKETLERI = {
    "owner": "Sahip",
    "admin": "Yönetici",
    "strategist": "Stratejist",
    "editor": "Editör",
    "viewer": "İzleyici",
}


def _giris_yonlendir() -> RedirectResponse:
    return RedirectResponse("/panel/giris", status_code=status.HTTP_303_SEE_OTHER)


def _yonetici_mi(request: Request, db) -> User | None:
    """Oturumu acan kisi sistem yoneticisi mi?

    Degilse None doner; cagiran taraf 404 verir. 403 vermek, boyle bir
    sayfanin VAR OLDUGUNU ele verirdi.
    """
    user = current_user_from_cookie(request, db)
    if user is None or not user.is_superuser:
        return None
    return user


def _bag_uret(user_id: uuid.UUID) -> str:
    alan_adi = get_settings().public_domain
    jeton = jeton_uret(user_id, omur_saniye=BAG_OMUR_SAAT * 3600)
    return f"https://{alan_adi}/panel/sifre-belirle?jeton={jeton}"


def _sayfa(request, db, user, *, error=None, ok=None, bag=None, bag_kisi=None, kod=200):
    uyelik_sayilari = dict(
        db.execute(
            select(WorkspaceMember.user_id, func.count())
            .group_by(WorkspaceMember.user_id)
        ).all()
    )

    kayitlar = db.execute(select(User).order_by(User.email)).scalars().all()

    kullanicilar = [
        {
            "id": str(k.id),
            "email": k.email,
            "full_name": k.full_name,
            "is_active": k.is_active,
            "is_superuser": k.is_superuser,
            "last_login_at": k.last_login_at,
            "uyelik": uyelik_sayilari.get(k.id, 0),
            "kendisi": k.id == user.id,
        }
        for k in kayitlar
    ]

    return templates.TemplateResponse(
        request, "users.html",
        {
            "user": user,
            "aktif": "kullanicilar",
            "workspace": None,
            "yol": "Kullanıcılar",
            "kullanicilar": kullanicilar,
            "etkin_sayisi": sum(1 for k in kullanicilar if k["is_active"]),
            "yonetici_sayisi": sum(
                1 for k in kullanicilar if k["is_superuser"] and k["is_active"]
            ),
            "bag": bag,
            "bag_kisi": bag_kisi,
            "bag_omur_saat": BAG_OMUR_SAAT,
            "error": error,
            "ok": ok,
        },
        status_code=kod,
    )


@router.get("", response_class=HTMLResponse)
def kullanicilar_sayfasi(request: Request, db: DbSession):
    user = _yonetici_mi(request, db)
    if user is None:
        if current_user_from_cookie(request, db) is None:
            return _giris_yonlendir()
        return HTMLResponse("Bulunamadı.", status_code=404)
    return _sayfa(request, db, user)


@router.post("/ekle")
def kullanici_ekle(
    request: Request,
    db: DbSession,
    email: Annotated[str, Form()],
    ad: Annotated[str, Form()],
    yonetici: Annotated[str, Form()] = "",
):
    user = _yonetici_mi(request, db)
    if user is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    try:
        yeni = kullanici_olustur(
            db, email=email, full_name=ad, is_superuser=bool(yonetici),
        )
    except KullaniciHatasi as hata:
        return _sayfa(request, db, user, error=str(hata), kod=status.HTTP_400_BAD_REQUEST)

    kaydet(
        db, action="kullanici.olustur", actor_user_id=user.id,
        subject_type="user", subject_id=yeni.id, request=request,
        details={"email": yeni.email, "is_superuser": yeni.is_superuser},
    )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _sayfa(
            request, db, user,
            error="Bu e-posta ile kayıtlı bir kullanıcı zaten var.",
            kod=status.HTTP_409_CONFLICT,
        )

    # Bag yalnizca BIR KEZ gosterilir; sayfa yenilenince kaybolur.
    return _sayfa(
        request, db, user,
        ok=f"{yeni.email} hesabı açıldı. Şifresini belirlemesi için aşağıdaki bağı iletin.",
        bag=_bag_uret(yeni.id), bag_kisi=yeni.email,
    )


@router.post("/duzenle")
def kullanici_duzenle(
    request: Request,
    db: DbSession,
    user_id: Annotated[uuid.UUID, Form()],
    ad: Annotated[str, Form()],
    etkin: Annotated[str, Form()] = "",
    yonetici: Annotated[str, Form()] = "",
):
    user = _yonetici_mi(request, db)
    if user is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    hedef = db.get(User, user_id)
    if hedef is None:
        return _sayfa(
            request, db, user, error="Kullanıcı bulunamadı.",
            kod=status.HTTP_404_NOT_FOUND,
        )

    try:
        degisenler = kullanici_guncelle(
            db, hedef, duzenleyen=user, full_name=ad,
            is_active=bool(etkin), is_superuser=bool(yonetici),
        )
    except KullaniciHatasi as hata:
        db.rollback()
        return _sayfa(request, db, user, error=str(hata), kod=status.HTTP_400_BAD_REQUEST)

    if not degisenler:
        return _sayfa(request, db, user, ok="Değişiklik yok.")

    # Denetim kaydina ALAN ADLARI yazilir, degerler degil.
    kaydet(
        db, action="kullanici.guncelle", actor_user_id=user.id,
        subject_type="user", subject_id=hedef.id, request=request,
        details={"email": hedef.email, "degisen_alanlar": degisenler},
    )
    db.commit()
    return _sayfa(request, db, user, ok=f"{hedef.email} güncellendi.")


@router.post("/sil")
def kullanici_kaldir(
    request: Request,
    db: DbSession,
    user_id: Annotated[uuid.UUID, Form()],
):
    user = _yonetici_mi(request, db)
    if user is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    hedef = db.get(User, user_id)
    if hedef is None:
        return _sayfa(
            request, db, user, error="Kullanıcı bulunamadı.",
            kod=status.HTTP_404_NOT_FOUND,
        )

    eposta = hedef.email
    try:
        kullanici_sil(db, hedef, silen=user)
    except KullaniciHatasi as hata:
        db.rollback()
        return _sayfa(request, db, user, error=str(hata), kod=status.HTTP_400_BAD_REQUEST)

    kaydet(
        db, action="kullanici.sil", actor_user_id=user.id,
        subject_type="user", subject_id=user_id, request=request,
        details={"email": eposta},
    )
    db.commit()
    return _sayfa(request, db, user, ok=f"{eposta} silindi.")


@router.post("/bag")
def sifre_bagi(
    request: Request,
    db: DbSession,
    user_id: Annotated[uuid.UUID, Form()],
):
    """Kullanici icin yeni bir sifre belirleme bagi uretir."""
    user = _yonetici_mi(request, db)
    if user is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    hedef = db.get(User, user_id)
    if hedef is None:
        return _sayfa(
            request, db, user, error="Kullanıcı bulunamadı.",
            kod=status.HTTP_404_NOT_FOUND,
        )
    if not hedef.is_active:
        return _sayfa(
            request, db, user,
            error="Pasif hesap için bağ üretilmez. Önce hesabı etkinleştirin.",
            kod=status.HTTP_400_BAD_REQUEST,
        )

    # Bagin KENDISI loglanmaz; yalnizca uretildigi kaydedilir.
    kaydet(
        db, action="kullanici.sifre_bagi", actor_user_id=user.id,
        subject_type="user", subject_id=hedef.id, request=request,
        details={"email": hedef.email, "omur_saat": BAG_OMUR_SAAT},
    )
    db.commit()
    return _sayfa(
        request, db, user, bag=_bag_uret(hedef.id), bag_kisi=hedef.email,
        ok=f"{hedef.email} için yeni bağ üretildi. Önceki bağ geçersizdir.",
    )


@router.get("/{user_id}", response_class=HTMLResponse)
def kullanici_detay(user_id: uuid.UUID, request: Request, db: DbSession):
    """Kullanicinin hangi musteride hangi yetkiye sahip oldugu."""
    user = _yonetici_mi(request, db)
    if user is None:
        if current_user_from_cookie(request, db) is None:
            return _giris_yonlendir()
        return HTMLResponse("Bulunamadı.", status_code=404)

    hedef = db.get(User, user_id)
    if hedef is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    satirlar = db.execute(
        select(WorkspaceMember, Workspace)
        .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
        .where(WorkspaceMember.user_id == user_id)
        .order_by(Workspace.name)
    ).all()

    return templates.TemplateResponse(
        request, "user_detail.html",
        {
            "user": user,
            "aktif": "kullanicilar",
            "workspace": None,
            "yol": hedef.full_name,
            "hedef": hedef,
            "uyelikler": [
                {
                    "workspace_id": str(w.id),
                    "workspace_name": w.name,
                    "rol": ROL_ETIKETLERI.get(m.role.value, m.role.value),
                }
                for m, w in satirlar
            ],
        },
    )
