"""Gosterge paneli (dashboard).

Giriste ilk gorulen ekran. Sorusu su: "bugun neye bakmam gerekiyor?"

BURADA UYDURMA SAYI YOKTUR. Bir olcu uretilemiyorsa gosterilmez ve
nedeni yazilir. Gosterge paneli "her sey yolunda" hissi veren bir
ekrandir; uydurma bir sayi burada, baska hicbir yerde olmadigi kadar
zarar verir cunku kimse sorgulamaz.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.deps import DbSession
from app.panel.auth import current_user_from_cookie
from app.services.dashboard import ozet_getir, toplam_butce

router = APIRouter(prefix="/panel/dashboard", tags=["panel"])
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@router.get("", response_class=HTMLResponse)
def dashboard(request: Request, db: DbSession):
    user = current_user_from_cookie(request, db)
    if user is None:
        return RedirectResponse("/panel/giris", status_code=status.HTTP_303_SEE_OTHER)

    ozet = ozet_getir(db, user)
    harcanan, sinir = toplam_butce(ozet)

    return templates.TemplateResponse(
        request, "dashboard.html",
        {
            "user": user,
            "aktif": "dashboard",
            "workspace": None,
            "yol": "Gösterge paneli",
            "ozet": ozet,
            "butce_harcanan": harcanan,
            "butce_sinir": sinir,
            "butce_yuzde": (
                min(100, int(harcanan / sinir * 100)) if sinir else 0
            ),
        },
    )
