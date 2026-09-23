"""Gorunum tercihleri sayfasi: tema ve vurgu rengi.

KISIYE OZELDIR. Sunucu genelinde tek bir tema dayatmak yanlis olurdu;
aydinlik bir odada calisan biriyle gece calisan birinin ihtiyaci ayni
degildir.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.deps import DbSession
from app.panel.auth import current_user_from_cookie
from app.services.gorunum import (
    TEMALAR,
    VURGULAR,
    tema_gecerli,
    vurgu_gecerli,
)

router = APIRouter(prefix="/panel/gorunum", tags=["panel"])
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _giris_yonlendir() -> RedirectResponse:
    return RedirectResponse("/panel/giris", status_code=status.HTTP_303_SEE_OTHER)


@router.get("")
def gorunum_sayfasi(request: Request, db: DbSession):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()

    return templates.TemplateResponse(
        request, "appearance.html",
        {
            "user": user,
            "aktif": "gorunum",
            "workspace": None,
            "yol": "Görünüm",
            "temalar": [
                {"deger": d, "etiket": e, "secili": d == tema_gecerli(user.tema)}
                for d, e in TEMALAR
            ],
            "vurgular": [
                {
                    "deger": v.anahtar,
                    "ad": v.ad,
                    "renk": v.koyu,
                    "renk_acik": v.acik,
                    "secili": v.anahtar == vurgu_gecerli(user.vurgu),
                }
                for v in VURGULAR
            ],
        },
    )


@router.post("")
def gorunum_kaydet(
    request: Request,
    db: DbSession,
    tema: Annotated[str, Form()] = "sistem",
    vurgu: Annotated[str, Form()] = "mavi",
):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()

    # Bilinmeyen deger SESSIZCE varsayilana duser. Hata verip kullaniciyi
    # ekranda birakmak, tema gibi zararsiz bir ayar icin agir olurdu.
    user.tema = tema_gecerli(tema)
    user.vurgu = vurgu_gecerli(vurgu)
    db.commit()
    return RedirectResponse("/panel/gorunum", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/degistir")
def tema_degistir(
    request: Request,
    db: DbSession,
    nereye: Annotated[str, Form()] = "/panel",
):
    """Ust cubuktaki tek tiklik koyu/acik gecisi.

    "sistem" secili iken basilirsa KOYU'ya gecilir: tek tiklik dugmenin
    isi belirsizligi bitirmektir; kullaniciyi yine "sistem"de birakmak
    dugmeyi ise yaramaz gosterirdi.
    """
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()

    user.tema = "acik" if tema_gecerli(user.tema) == "koyu" else "koyu"
    db.commit()

    # Acik yonlendirme korumasi: yalnizca kendi panelimize doneriz.
    hedef = nereye if nereye.startswith("/panel") else "/panel"
    return RedirectResponse(hedef, status_code=status.HTTP_303_SEE_OTHER)
