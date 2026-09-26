"""Yapay zeka sayfasi: saglayicilar ve hangi gorevi hangisinin yapacagi.

BU SAYFA NE COZER:
Once saglayici listesi ve gorev dagilimi koda gomuluydu. Yeni bir
saglayici eklemek veya "trend arastirmasini su yapsin" demek kod
degisikligi gerektiriyordu. Artik ikisi de buradan yonetilir.

SINANMAMIS SAGLAYICI ATANAMAZ:
Checkbox ile acmak yetmez. "Bağlantıyı sına" GERCEK bir cagri yapar;
yalnizca basarili olan saglayici gorev listesinde secilebilir hale
gelir. Boylece panelde hazir gorunup calismayan bir entegrasyon
olusamaz.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.api.deps import DbSession
from app.core.config import get_settings
from app.models.ai_saglayici import SaglayiciTuru
from app.models.identity import User
from app.panel.auth import current_user_from_cookie
from app.panel.sablon import templates
from app.services.ai_saglayicilar import (
    GOREVLER,
    SaglayiciHatasi,
    atama_yap,
    atamalar,
    etkinlik_ayarla,
    listele,
    ozel_ekle,
    sil,
    sina,
    varsayilanlari_kur,
)
from app.services.denetim import kaydet
from app.services.sistem_ayarlari import deger_oku

router = APIRouter(prefix="/panel/yapay-zeka", tags=["panel"])

TUR_ADLARI = {
    SaglayiciTuru.ANTHROPIC: "Anthropic",
    SaglayiciTuru.GEMINI: "Google Gemini",
    SaglayiciTuru.MANUS: "Manus",
    SaglayiciTuru.OPENAI_UYUMLU: "OpenAI uyumlu",
}


def _giris_yonlendir() -> RedirectResponse:
    return RedirectResponse("/panel/giris", status_code=status.HTTP_303_SEE_OTHER)


def _yonetici(request: Request, db) -> User | None:
    """Saglayici ve anahtar yonetimi SISTEM YONETICISINE ozeldir."""
    user = current_user_from_cookie(request, db)
    if user is None or not user.is_superuser:
        return None
    return user


def _sayfa(request, db, user, *, ok=None, error=None, kod=200):
    varsayilanlari_kur(db)
    db.commit()

    kayitlar = listele(db)
    mevcut_atamalar = atamalar(db)

    satirlar = []
    for s in kayitlar:
        anahtar_var = bool(deger_oku(db, s.anahtar_ayari)) if s.anahtar_ayari else False
        satirlar.append({
            "anahtar": s.anahtar,
            "ad": s.ad,
            "tur": TUR_ADLARI.get(s.tur, s.tur.value),
            "tur_kodu": s.tur.value,
            "etkin": s.etkin,
            "yerlesik": s.yerlesik,
            "model": s.model or "",
            "taban_url": s.taban_url or "",
            "anahtar_ayari": s.anahtar_ayari or "",
            "anahtar_var": anahtar_var,
            "kullanilabilir": s.kullanilabilir,
            "sinama_zamani": s.son_sinama_zamani,
            "sinama_basarili": s.son_sinama_basarili,
            "sinama_mesaji": s.son_sinama_mesaji or "",
        })

    secilebilir = [s for s in satirlar if s["kullanilabilir"]]
    gorev_satirlari = []
    for gorev in GOREVLER:
        atanan = mevcut_atamalar.get(gorev.kod, gorev.varsayilan)
        kayit = next((s for s in satirlar if s["anahtar"] == atanan), None)
        gorev_satirlari.append({
            "kod": gorev.kod,
            "ad": gorev.ad,
            "aciklama": gorev.aciklama,
            "atanan": atanan,
            "atanan_ad": kayit["ad"] if kayit else atanan,
            # Atanmis ama kullanilamaz durumdaysa bu GORUNMELI: aksi halde
            # akis calismadiginda sebebi anlasilmaz.
            "calisir": bool(kayit and kayit["kullanilabilir"]),
        })

    ayarlar = get_settings()
    return templates.TemplateResponse(
        request, "yapay_zeka.html",
        {
            "user": user,
            "aktif": "yapay_zeka",
            "workspace": None,
            "yol": "Yapay zekâ",
            "saglayicilar": satirlar,
            "secilebilir": secilebilir,
            "gorevler": gorev_satirlari,
            "ornek_veri_modu": ayarlar.ai_provider_mode == "fake",
            "uretim": ayarlar.is_production,
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


@router.post("/etkinlik")
def etkinlik(
    request: Request, db: DbSession,
    anahtar: Annotated[str, Form()],
    etkin: Annotated[str, Form()] = "",
):
    user = _yonetici(request, db)
    if user is None:
        return _giris_yonlendir()
    try:
        etkinlik_ayarla(db, anahtar, etkin == "evet")
    except SaglayiciHatasi as hata:
        return _sayfa(request, db, user, error=str(hata), kod=400)
    kaydet(db, actor_user_id=user.id, action="ai.saglayici_etkinlik",
           details={"saglayici": anahtar, "etkin": etkin == "evet"})
    db.commit()
    return RedirectResponse("/panel/yapay-zeka", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/sina")
def sinama(request: Request, db: DbSession, anahtar: Annotated[str, Form()]):
    user = _yonetici(request, db)
    if user is None:
        return _giris_yonlendir()
    try:
        basarili, mesaj = sina(db, anahtar)
    except SaglayiciHatasi as hata:
        return _sayfa(request, db, user, error=str(hata), kod=400)
    kaydet(db, actor_user_id=user.id, action="ai.saglayici_sinandi",
           details={"saglayici": anahtar, "basarili": basarili})
    db.commit()
    return _sayfa(
        request, db, user,
        ok=f"{anahtar}: {mesaj}" if basarili else None,
        error=None if basarili else f"{anahtar}: {mesaj}",
    )


@router.post("/atama")
def atama(
    request: Request, db: DbSession,
    gorev: Annotated[str, Form()],
    saglayici: Annotated[str, Form()],
):
    user = _yonetici(request, db)
    if user is None:
        return _giris_yonlendir()
    try:
        atama_yap(db, gorev, saglayici)
    except SaglayiciHatasi as hata:
        return _sayfa(request, db, user, error=str(hata), kod=400)
    kaydet(db, actor_user_id=user.id, action="ai.gorev_atandi",
           details={"gorev": gorev, "saglayici": saglayici})
    db.commit()
    return RedirectResponse("/panel/yapay-zeka", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/ekle")
def ekle(
    request: Request, db: DbSession,
    anahtar: Annotated[str, Form()],
    ad: Annotated[str, Form()],
    taban_url: Annotated[str, Form()],
    model: Annotated[str, Form()],
    api_anahtari: Annotated[str, Form()],
):
    user = _yonetici(request, db)
    if user is None:
        return _giris_yonlendir()
    try:
        ozel_ekle(
            db, anahtar=anahtar, ad=ad, taban_url=taban_url, model=model,
            api_anahtari=api_anahtari, user_id=user.id,
        )
    except SaglayiciHatasi as hata:
        return _sayfa(request, db, user, error=str(hata), kod=400)
    # API anahtari denetim kaydina YAZILMAZ; yalnizca hangi saglayicinin
    # eklendigi yazilir.
    kaydet(db, actor_user_id=user.id, action="ai.saglayici_eklendi",
           details={"saglayici": anahtar.strip().lower()})
    db.commit()
    return _sayfa(
        request, db, user,
        ok="Sağlayıcı eklendi. Kullanabilmek için önce açın, "
           "sonra \"Bağlantıyı sına\" düğmesine basın.",
    )


@router.post("/sil")
def silme(request: Request, db: DbSession, anahtar: Annotated[str, Form()]):
    user = _yonetici(request, db)
    if user is None:
        return _giris_yonlendir()
    try:
        sil(db, anahtar)
    except SaglayiciHatasi as hata:
        return _sayfa(request, db, user, error=str(hata), kod=400)
    kaydet(db, actor_user_id=user.id, action="ai.saglayici_silindi",
           details={"saglayici": anahtar})
    db.commit()
    return _sayfa(request, db, user, ok="Sağlayıcı kaldırıldı.")
