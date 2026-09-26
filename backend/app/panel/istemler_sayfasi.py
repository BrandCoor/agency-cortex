"""Istem (prompt) yonetimi: is akislarinin yapay zekaya verdigi yonergeler.

ISTENEN: "is akislarinin promptlari disaridan da girilebilmeli,
duzenlenebilmeli, eklenip kaldirilabilmeli."

BU SAYFA NE YAPAR:
- Her is akisinin sistem istemini GOSTERIR (gizli degil, okunabilir)
- Metni duzenletir; kaydedince SURUM artar
- "Varsayilana don" ile koddaki metne geri doner
- Yeni istem ekletir, kullanicinin ekledigini sildirir

NEDEN SURUM ARTIYOR:
Uretilen her AI ciktisi hangi istem surumuyle uretildigini kaydeder.
Surum artmasaydi "bu rapor neden boyle cikmis?" sorusunun cevabi
kaybolurdu.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.api.deps import DbSession
from app.models.identity import User
from app.panel.auth import current_user_from_cookie
from app.panel.sablon import templates
from app.services.denetim import kaydet
from app.services.istemler import (
    IstemHatasi,
    ekle,
    guncelle,
    listele,
    sil,
    varsayilana_don,
    varsayilanlari_kur,
    yerlesikler,
)

router = APIRouter(prefix="/panel/istemler", tags=["panel"])


def _giris_yonlendir() -> RedirectResponse:
    return RedirectResponse("/panel/giris", status_code=status.HTTP_303_SEE_OTHER)


def _yonetici(request: Request, db) -> User | None:
    """Istem metni ciktinin tamamini belirler; SISTEM YONETICISINE ozeldir."""
    user = current_user_from_cookie(request, db)
    if user is None or not user.is_superuser:
        return None
    return user


def _sayfa(request, db, user, *, ok=None, error=None, kod=200, acik=None):
    varsayilanlari_kur(db)
    db.commit()

    kod_metinleri = {y.kod: y.metin for y in yerlesikler()}
    satirlar = []
    for i in listele(db):
        varsayilan = kod_metinleri.get(i.kod)
        satirlar.append({
            "kod": i.kod,
            "ad": i.ad,
            "akis": i.akis or "",
            "aciklama": i.aciklama,
            "metin": i.metin,
            "surum": i.surum,
            "etkin": i.etkin,
            "yerlesik": i.yerlesik,
            # Kullanici "bu metin kodda yazandan farkli mi?" sorusunun
            # cevabini gormeden "varsayilana don" demeyi goze alamaz.
            "degistirilmis": bool(varsayilan is not None and varsayilan != i.metin),
            "uzunluk": len(i.metin),
        })

    return templates.TemplateResponse(
        request, "istemler.html",
        {
            "user": user,
            "aktif": "istemler",
            "workspace": None,
            "yol": "İstemler",
            "istemler": satirlar,
            "acik": acik,
            "ok": ok,
            "error": error,
        },
        status_code=kod,
    )


@router.get("", response_class=HTMLResponse)
def sayfa(request: Request, db: DbSession):
    user = _yonetici(request, db)
    if user is None:
        return _giris_yonlendir()
    return _sayfa(request, db, user)


@router.post("/kaydet")
def kaydetme(
    request: Request, db: DbSession,
    kod: Annotated[str, Form()],
    metin: Annotated[str, Form()],
):
    user = _yonetici(request, db)
    if user is None:
        return _giris_yonlendir()
    try:
        kayit = guncelle(db, kod, metin)
    except IstemHatasi as hata:
        return _sayfa(request, db, user, error=str(hata), kod=400, acik=kod)
    kaydet(db, actor_user_id=user.id, action="istem.guncellendi",
           details={"kod": kod, "surum": kayit.surum})
    db.commit()
    return _sayfa(
        request, db, user, acik=kod,
        ok=f"“{kayit.ad}” kaydedildi. Yeni sürüm: v{kayit.surum}",
    )


@router.post("/varsayilan")
def varsayilan(request: Request, db: DbSession, kod: Annotated[str, Form()]):
    user = _yonetici(request, db)
    if user is None:
        return _giris_yonlendir()
    try:
        kayit = varsayilana_don(db, kod)
    except IstemHatasi as hata:
        return _sayfa(request, db, user, error=str(hata), kod=400, acik=kod)
    kaydet(db, actor_user_id=user.id, action="istem.varsayilana_dondu",
           details={"kod": kod, "surum": kayit.surum})
    db.commit()
    return _sayfa(
        request, db, user, acik=kod,
        ok=f"“{kayit.ad}” koddaki varsayılan metne döndürüldü (v{kayit.surum}).",
    )


@router.post("/ekle")
def ekleme(
    request: Request, db: DbSession,
    kod: Annotated[str, Form()],
    ad: Annotated[str, Form()],
    metin: Annotated[str, Form()],
    akis: Annotated[str, Form()] = "",
    aciklama: Annotated[str, Form()] = "",
):
    user = _yonetici(request, db)
    if user is None:
        return _giris_yonlendir()
    try:
        kayit = ekle(db, kod=kod, ad=ad, akis=akis, aciklama=aciklama, metin=metin)
    except IstemHatasi as hata:
        return _sayfa(request, db, user, error=str(hata), kod=400)
    kaydet(db, actor_user_id=user.id, action="istem.eklendi",
           details={"kod": kayit.kod})
    db.commit()
    return _sayfa(
        request, db, user, acik=kayit.kod,
        ok=f"“{kayit.ad}” eklendi. Bir iş akışının bunu kullanabilmesi için "
           "kodda çağrılıyor olması gerekir.",
    )


@router.post("/sil")
def silme(request: Request, db: DbSession, kod: Annotated[str, Form()]):
    user = _yonetici(request, db)
    if user is None:
        return _giris_yonlendir()
    try:
        sil(db, kod)
    except IstemHatasi as hata:
        return _sayfa(request, db, user, error=str(hata), kod=400)
    kaydet(db, actor_user_id=user.id, action="istem.silindi", details={"kod": kod})
    db.commit()
    return _sayfa(request, db, user, ok="İstem kaldırıldı.")
