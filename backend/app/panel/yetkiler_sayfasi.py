"""Yetkiler ekrani: tum kullanicilar tek tabloda.

NEDEN AYRI BIR SAYFA VAR:
Yetkiler yalnizca "Kullanicilar -> bir kisiye tikla -> asagi kaydir"
yolundan ulasilabiliyordu. Menude "Yetkiler" diye bir sey yoktu; bu
yuzden ozellik VAR olmasina ragmen YOK sanildi.

Gorunmeyen bir ozellik, olmayan bir ozelliktir.

BU SAYFA NE YAPAR:
- Herkesin KATEGORISINI (yetki paketi) tek ekrandan degistirir
- Kimin kac izinle calistigini ve ozellestirme olup olmadigini gosterir
- Kisi bazinda ince ayara gecis verir
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
from app.models.enums import PermissionPackage
from app.models.identity import User, WorkspaceMember
from app.panel.auth import current_user_from_cookie
from app.services.denetim import kaydet
from app.services.yetkiler import (
    IZIN_ANAHTARLARI,
    IZINLER,
    PAKET_ADLARI,
    PAKET_VARSAYILANI,
    YetkiHatasi,
    kullanici_izinleri,
    paketi_degistir,
)

router = APIRouter(prefix="/panel/yetkiler", tags=["panel"])
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _giris_yonlendir() -> RedirectResponse:
    return RedirectResponse("/panel/giris", status_code=status.HTTP_303_SEE_OTHER)


def _yonetici(request: Request, db) -> User | None:
    """Yetki ekrani SISTEM YONETICISINE ozeldir."""
    user = current_user_from_cookie(request, db)
    if user is None or not user.is_superuser:
        return None
    return user


def _sayfa(request, db, user, *, ok=None, error=None, kod=200):
    kisiler = db.execute(select(User).order_by(User.full_name)).scalars().all()

    satirlar = []
    for k in kisiler:
        gecerli = kullanici_izinleri(db, k)
        varsayilan = PAKET_VARSAYILANI.get(k.permission_package, frozenset())
        musteri_sayisi = len(db.execute(
            select(WorkspaceMember).where(WorkspaceMember.user_id == k.id)
        ).scalars().all())
        satirlar.append({
            "id": str(k.id),
            "ad": k.full_name,
            "email": k.email,
            "aktif": k.is_active,
            "sistem_yoneticisi": k.is_superuser,
            "paket": k.permission_package.value,
            "paket_adi": PAKET_ADLARI.get(k.permission_package, k.permission_package.value),
            "izin_sayisi": len(gecerli),
            # Paketten SAPMA var mi? Kullanici "bu kisi neden farkli?"
            # sorusunu tabloyu terk etmeden gorebilmeli.
            "ozellestirilmis": gecerli != varsayilan and not k.is_superuser,
            "musteri_sayisi": musteri_sayisi,
            "kendisi": k.id == user.id,
        })

    return templates.TemplateResponse(
        request, "permissions.html",
        {
            "user": user,
            "aktif": "yetkiler",
            "workspace": None,
            "yol": "Yetkiler",
            "satirlar": satirlar,
            "paketler": [
                {"deger": p.value, "etiket": PAKET_ADLARI.get(p, p.value)}
                for p in PermissionPackage
            ],
            "toplam_izin": len(IZIN_ANAHTARLARI),
            "paket_ozeti": [
                {
                    "etiket": PAKET_ADLARI.get(p, p.value),
                    "sayi": len(PAKET_VARSAYILANI.get(p, frozenset())),
                    "izinler": sorted(
                        i.ad for i in IZINLER
                        if i.anahtar in PAKET_VARSAYILANI.get(p, frozenset())
                    ),
                }
                for p in PermissionPackage
            ],
            "ok": ok,
            "error": error,
        },
        status_code=kod,
    )


@router.get("", response_class=HTMLResponse)
def yetkiler_sayfasi(request: Request, db: DbSession):
    user = _yonetici(request, db)
    if user is None:
        if current_user_from_cookie(request, db) is None:
            return _giris_yonlendir()
        return HTMLResponse("Bulunamadı.", status_code=404)
    return _sayfa(request, db, user)


@router.post("/paket")
def paket_ata(
    request: Request,
    db: DbSession,
    user_id: Annotated[uuid.UUID, Form()],
    paket: Annotated[str, Form()],
):
    """Bir kullanicinin kategorisini degistirir."""
    user = _yonetici(request, db)
    if user is None:
        if current_user_from_cookie(request, db) is None:
            return _giris_yonlendir()
        return HTMLResponse("Bulunamadı.", status_code=404)

    hedef = db.get(User, user_id)
    if hedef is None:
        return _sayfa(request, db, user, error="Kullanıcı bulunamadı.", kod=404)

    try:
        yeni = PermissionPackage(paket)
    except ValueError:
        return _sayfa(request, db, user, error="Geçersiz kategori.", kod=400)

    try:
        paketi_degistir(db, hedef, yeni)
    except YetkiHatasi as exc:
        return _sayfa(request, db, user, error=str(exc), kod=400)

    kaydet(
        db, action="yetki.paket_degisti", actor_user_id=user.id,
        subject_type="user", subject_id=hedef.id, request=request,
        details={"paket": yeni.value},
    )
    db.commit()
    return _sayfa(
        request, db, user,
        ok=f"{hedef.full_name} → {PAKET_ADLARI.get(yeni, yeni.value)}",
    )
