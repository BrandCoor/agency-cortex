"""Panel sayfalari.

Sunucu tarafinda uretilen sade HTML. Ayri bir JavaScript uygulamasi
kullanilmadi - gerekcesi DECISIONS.md K-017'de.

Guvenlik: Her sayfa, kullanicinin o musteriye UYE oldugunu dogrular.
Uye degilse 404 doner (403 degil - 403, o musterinin varligini ele verirdi).
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbSession
from app.cli.hesap import MIN_SIFRE_UZUNLUGU
from app.core.security import create_token, hash_password, verify_password
from app.models.brand import Brand, BrandGuideline, Campaign
from app.models.content import ContentScript
from app.models.enums import ContentStatus, Platform
from app.models.identity import User, Workspace, WorkspaceMember
from app.models.reporting import Report, ReportSection
from app.models.social import SocialAccount
from app.panel.auth import clear_session_cookie, current_user_from_cookie, set_session_cookie
from app.panel.ortak import uyelik_bul
from app.platforms.base import PlatformError
from app.platforms.meta_ayar import meta_ayarlarini_oku
from app.platforms.registry import get_adapter, platform_status
from app.services.ai_runner import month_spend
from app.services.approvals import (
    ALLOWED_TRANSITIONS,
    ApprovalError,
    approval_history,
    can_publish,
    gerekli_izin,
    transition,
)
from app.services.baglanti_sinama import SINAYICILAR, sina
from app.services.denetim import kaydet
from app.services.oauth_state import create_state
from app.services.sifre_sifirlama import JetonHatasi, jeton_gecerli_mi, jetonu_tuket
from app.services.sistem_ayarlari import (
    AYAR_ANAHTARLARI,
    deger_sil,
    deger_yaz,
    durum_listesi,
)
from app.services.yetkiler import PAKET_ADLARI, izin_var_mi

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


def _giris_yonlendir() -> RedirectResponse:
    return RedirectResponse("/panel/giris", status_code=status.HTTP_303_SEE_OTHER)


def _izinli_hedefler(db, user, mevcut: ContentStatus, tur: str) -> list[str]:
    """Kullanicinin bu durumdan gidebilecegi durumlar.

    Yetkisi yetmeyen secenekler listede GOSTERILMEZ; kullanici
    yapamayacagi bir seyi denemek zorunda kalmaz.

    Ayni izin tablosunu `transition` da kullanir. Burasi yalnizca
    GORUNUMU belirler; asil kilit servis katmanindadir. Ikisi ayri
    tablolara baksaydi, panelde gorunen bir dugme sunucuda reddedilirdi.
    """
    sonuc = []
    for hedef in ALLOWED_TRANSITIONS.get(mevcut, set()):
        # Yayinlama kilidi kapali oldugu icin bu secenek hic sunulmaz.
        if hedef is ContentStatus.PUBLISHED:
            continue
        if izin_var_mi(db, user, gerekli_izin(tur, hedef)):
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


# --- Tek kullanimlik sifre belirleme -----------------------------------------
#
# Sifrenin kullanicidan sisteme ulasirken bicim degistirmesi (kacan bosluk,
# Turkce harflerin farkli Unicode gosterimleri, klavye farklari) "sifre dogru
# ama giris olmuyor" arizasina yol acar. Bu akista sifre hic aktarilmaz:
# kullanici sifresini dogrudan burada, sistemin kendi formunda belirler.

def _belirle_sayfasi(request, *, jeton="", gecersiz=False, error=None, kod=200):
    return templates.TemplateResponse(
        request, "set_password.html",
        {
            "user": None, "jeton": jeton, "gecersiz": gecersiz,
            "error": error, "min_uzunluk": MIN_SIFRE_UZUNLUGU,
        },
        status_code=kod,
    )


@router.get("/sifre-belirle", response_class=HTMLResponse)
def set_password_page(request: Request, jeton: str = ""):
    # Jeton burada TUKETILMEZ; yalnizca gecerli mi diye bakilir. Boylece
    # sayfayi yenilemek bagi harcamaz.
    if not jeton_gecerli_mi(jeton):
        return _belirle_sayfasi(request, gecersiz=True, kod=status.HTTP_404_NOT_FOUND)
    return _belirle_sayfasi(request, jeton=jeton)


@router.post("/sifre-belirle")
def set_password_submit(
    request: Request,
    db: DbSession,
    jeton: Annotated[str, Form()],
    yeni: Annotated[str, Form()],
    yeni_tekrar: Annotated[str, Form()],
):
    if not jeton_gecerli_mi(jeton):
        return _belirle_sayfasi(request, gecersiz=True, kod=status.HTTP_404_NOT_FOUND)

    # Once bicim kontrolleri: hatali girdide bag harcanmasin.
    if yeni != yeni_tekrar:
        return _belirle_sayfasi(
            request, jeton=jeton, error="Şifreler birbirini tutmuyor.",
            kod=status.HTTP_400_BAD_REQUEST,
        )
    if len(yeni) < MIN_SIFRE_UZUNLUGU:
        return _belirle_sayfasi(
            request, jeton=jeton,
            error=f"Şifre en az {MIN_SIFRE_UZUNLUGU} karakter olmalı.",
            kod=status.HTTP_400_BAD_REQUEST,
        )

    # Girdi gecerli; simdi bag tek kullanimlik olarak tuketilir.
    try:
        user_id = jetonu_tuket(jeton)
    except JetonHatasi:
        return _belirle_sayfasi(request, gecersiz=True, kod=status.HTTP_404_NOT_FOUND)

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return _belirle_sayfasi(request, gecersiz=True, kod=status.HTTP_404_NOT_FOUND)

    user.password_hash = hash_password(yeni)
    db.commit()

    # Kullanici dogrudan iceri alinir; bir kez daha sifre yazmasi gerekmez.
    yanit = RedirectResponse("/panel", status_code=status.HTTP_303_SEE_OTHER)
    set_session_cookie(yanit, create_token(user.id, "access"))
    return yanit


# --- Sifre degistirme --------------------------------------------------------

def _sifre_sayfasi(request, user, *, error=None, ok=None, kod=200):
    return templates.TemplateResponse(
        request, "password.html",
        {"user": user, "aktif": "sifre", "error": error, "ok": ok,
         "min_uzunluk": MIN_SIFRE_UZUNLUGU},
        status_code=kod,
    )


@router.get("/sifre", response_class=HTMLResponse)
def password_page(request: Request, db: DbSession):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()
    return _sifre_sayfasi(request, user)


@router.post("/sifre")
def password_submit(
    request: Request,
    db: DbSession,
    mevcut: Annotated[str, Form()],
    yeni: Annotated[str, Form()],
    yeni_tekrar: Annotated[str, Form()],
):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()

    # Cerez calinmis olsa bile mevcut sifre bilinmeden degistirilemez.
    if not verify_password(mevcut, user.password_hash):
        return _sifre_sayfasi(
            request, user, error="Mevcut şifre hatalı.",
            kod=status.HTTP_401_UNAUTHORIZED,
        )
    if yeni != yeni_tekrar:
        return _sifre_sayfasi(
            request, user, error="Yeni şifreler birbirini tutmuyor.",
            kod=status.HTTP_400_BAD_REQUEST,
        )
    if len(yeni) < MIN_SIFRE_UZUNLUGU:
        return _sifre_sayfasi(
            request, user,
            error=f"Yeni şifre en az {MIN_SIFRE_UZUNLUGU} karakter olmalı.",
            kod=status.HTTP_400_BAD_REQUEST,
        )
    if yeni == mevcut:
        return _sifre_sayfasi(
            request, user, error="Yeni şifre eskisiyle aynı olamaz.",
            kod=status.HTTP_400_BAD_REQUEST,
        )

    user.password_hash = hash_password(yeni)
    db.commit()

    # Yeni bir oturum anahtari verilir; eski anahtarin omru kisalmaz ama
    # kullanici en azindan temiz bir oturumla devam eder.
    yanit = _sifre_sayfasi(request, user, ok="Şifreniz değiştirildi.")
    set_session_cookie(yanit, create_token(user.id, "access"))
    return yanit


# --- Musteri listesi ---------------------------------------------------------

def _musteri_listesi(request, db, user, *, error=None, kod=200):
    """Musteri listesi sayfasini cizer. Liste her zaman kullaniciya gore filtrelidir."""
    satirlar = db.execute(
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id)
        .order_by(Workspace.name)
    ).all()

    return templates.TemplateResponse(
        request, "workspaces.html",
        {
            "user": user,
            "aktif": "musteriler",
            "error": error,
            "memberships": [
                {"workspace": ws}
                for (ws,) in satirlar
            ],
        },
        status_code=kod,
    )


@router.get("", response_class=HTMLResponse)
def workspaces_page(request: Request, db: DbSession):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()
    return _musteri_listesi(request, db, user)


# --- Yeni musteri ------------------------------------------------------------

# Turkce harfler URL'de sorun cikarir; once ASCII karsiliklarina cevrilir.
TR_HARFLER = str.maketrans({
    "ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g", "ı": "i", "İ": "i",
    "ö": "o", "Ö": "o", "ş": "s", "Ş": "s", "ü": "u", "Ü": "u",
})


def kisa_ad_uret(ad: str) -> str:
    """Musteri adindan URL'de kullanilabilir kisa ad (slug) uretir."""
    temiz = ad.translate(TR_HARFLER).lower()
    temiz = re.sub(r"[^a-z0-9]+", "-", temiz).strip("-")
    # Ayni ada sahip iki musteri olabilir; sonuna kisa bir ek konur.
    return f"{temiz[:80] or 'musteri'}-{uuid.uuid4().hex[:6]}"


@router.post("/musteri-ekle")
def workspace_create(request: Request, db: DbSession, ad: Annotated[str, Form()]):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()

    ad = ad.strip()
    if len(ad) < 2:
        return _musteri_listesi(request, db, user, error="Müşteri adı en az 2 karakter olmalı.")

    workspace = Workspace(name=ad, slug=kisa_ad_uret(ad))
    db.add(workspace)
    db.flush()
    # Musteriyi ekleyen kisi otomatik olarak sahibi (owner) olur.
    db.add(
        WorkspaceMember(
            workspace_id=workspace.id, user_id=user.id
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _musteri_listesi(
            request, db, user, error="Müşteri eklenemedi, lütfen tekrar deneyin."
        )

    return RedirectResponse(
        f"/panel/musteri/{workspace.id}", status_code=status.HTTP_303_SEE_OTHER
    )


# --- Musteri ekrani ----------------------------------------------------------

@router.get("/musteri/{workspace_id}", response_class=HTMLResponse)
def workspace_page(workspace_id: uuid.UUID, request: Request, db: DbSession):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()

    uyelik = uyelik_bul(request, db, user, workspace_id)
    if uyelik is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    ws = db.get(Workspace, workspace_id)
    bekleyen = [ContentStatus.INTERNAL_REVIEW, ContentStatus.CLIENT_REVIEW]

    return templates.TemplateResponse(
        request, "workspace.html",
        {
            "user": user,
            "aktif": "ozet",
            "workspace": ws,
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
            # Ozet kutulari icin: bir bakista eksigi gormek kolay olsun.
            "hesap_sayisi": db.execute(
                select(func.count()).select_from(SocialAccount)
                .where(SocialAccount.workspace_id == workspace_id)
            ).scalar_one(),
            "marka_var": db.execute(
                select(func.count()).select_from(Brand)
                .where(Brand.workspace_id == workspace_id)
            ).scalar_one() > 0,
            "ai_exceeded": float(month_spend(db, workspace_id)) >= float(ws.ai_monthly_budget_usd),
            "using_fake": get_fake_mode(),
        },
    )


# --- Marka bilgileri ---------------------------------------------------------
#
# Yapay zeka icerik uretirken bu kayitlari temel alir. Bos birakilirsa uretilen
# icerik genel gecer olur; bu yuzden panelden doldurulabilmesi gerekir.


def _satirlara_bol(metin: str) -> list[str]:
    """Her satiri ayri bir ifade sayar. Bos satirlar atilir."""
    return [satir.strip() for satir in (metin or "").splitlines() if satir.strip()]


def _marka_sayfasi(request, db, user, uyelik, workspace, *, error=None, ok=None, kod=200):
    marka = db.execute(
        select(Brand).where(Brand.workspace_id == workspace.id)
    ).scalars().first()
    kilavuz = None
    if marka is not None:
        kilavuz = db.execute(
            select(BrandGuideline).where(BrandGuideline.brand_id == marka.id)
        ).scalars().first()

    return templates.TemplateResponse(
        request, "brand.html",
        {
            "user": user,
            "aktif": "marka",
            "workspace": workspace,
            "marka": marka,
            "kilavuz": kilavuz,
            "yasakli_metin": "\n".join(kilavuz.forbidden_phrases) if kilavuz else "",
            "tercih_metin": "\n".join(kilavuz.preferred_phrases) if kilavuz else "",
            "duzenleyebilir": izin_var_mi(db, user, "marka.duzenle"),
            "error": error,
            "ok": ok,
        },
        status_code=kod,
    )


@router.get("/musteri/{workspace_id}/marka", response_class=HTMLResponse)
def brand_page(workspace_id: uuid.UUID, request: Request, db: DbSession):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()
    uyelik = uyelik_bul(request, db, user, workspace_id)
    if uyelik is None:
        return HTMLResponse("Bulunamadı.", status_code=404)
    return _marka_sayfasi(request, db, user, uyelik, db.get(Workspace, workspace_id))


@router.post("/musteri/{workspace_id}/marka")
def brand_submit(
    workspace_id: uuid.UUID,
    request: Request,
    db: DbSession,
    ad: Annotated[str, Form()],
    sektor: Annotated[str, Form()] = "",
    site: Annotated[str, Form()] = "",
    aciklama: Annotated[str, Form()] = "",
    ton: Annotated[str, Form()] = "",
    kitle: Annotated[str, Form()] = "",
    yasakli: Annotated[str, Form()] = "",
    tercih: Annotated[str, Form()] = "",
    notlar: Annotated[str, Form()] = "",
):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()
    uyelik = uyelik_bul(request, db, user, workspace_id)
    if uyelik is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    workspace = db.get(Workspace, workspace_id)
    # Yetki sunucuda dogrulanir; formun kapali olmasi tek basina yeterli degil.
    if not izin_var_mi(db, user, "marka.duzenle"):
        return _marka_sayfasi(
            request, db, user, uyelik, workspace,
            error="Bu işlem için en az stratejist yetkisi gerekir.",
            kod=status.HTTP_403_FORBIDDEN,
        )

    ad = ad.strip()
    if len(ad) < 2:
        return _marka_sayfasi(
            request, db, user, uyelik, workspace,
            error="Marka adı en az 2 karakter olmalı.",
            kod=status.HTTP_400_BAD_REQUEST,
        )

    marka = db.execute(
        select(Brand).where(Brand.workspace_id == workspace_id)
    ).scalars().first()
    if marka is None:
        marka = Brand(workspace_id=workspace_id, name=ad)
        db.add(marka)
        db.flush()

    marka.name = ad
    marka.sector = sektor.strip() or None
    marka.website = site.strip() or None
    marka.description = aciklama.strip() or None

    kilavuz = db.execute(
        select(BrandGuideline).where(BrandGuideline.brand_id == marka.id)
    ).scalars().first()
    if kilavuz is None:
        kilavuz = BrandGuideline(workspace_id=workspace_id, brand_id=marka.id)
        db.add(kilavuz)

    kilavuz.tone_of_voice = ton.strip() or None
    kilavuz.target_audience = kitle.strip() or None
    kilavuz.forbidden_phrases = _satirlara_bol(yasakli)
    kilavuz.preferred_phrases = _satirlara_bol(tercih)
    kilavuz.notes = notlar.strip() or None
    db.commit()

    return _marka_sayfasi(
        request, db, user, uyelik, workspace, ok="Marka bilgileri kaydedildi."
    )


# --- Ekip --------------------------------------------------------------------
#
# Ekip sayfasi ATAMA yapar, YETKI VERMEZ. Bir kisinin neyi yapabilecegi
# kullanicinin kendisinde tutulur (Yonetim -> Kullanicilar -> Yetkiler).
# Burada yalnizca "bu kisi bu musteride calisiyor mu" belirlenir.

def _ekip_sayfasi(request, db, user, uyelik, workspace, *, error=None, ok=None, kod=200):
    satirlar = db.execute(
        select(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .where(WorkspaceMember.workspace_id == workspace.id)
        .order_by(User.email)
    ).all()

    return templates.TemplateResponse(
        request, "members.html",
        {
            "user": user,
            "aktif": "ekip",
            "workspace": workspace,
            "uyeler": [
                {
                    "id": str(u.id),
                    "email": u.email,
                    "full_name": u.full_name,
                    "paket": PAKET_ADLARI.get(
                        u.permission_package, u.permission_package.value
                    ),
                    "sistem_yoneticisi": u.is_superuser,
                    "kendisi": u.id == user.id,
                }
                for _m, u in satirlar
            ],
            "yonetebilir": izin_var_mi(db, user, "ekip.yonet"),
            "yol": "Ekip",
            "error": error,
            "ok": ok,
        },
        status_code=kod,
    )


@router.get("/musteri/{workspace_id}/ekip", response_class=HTMLResponse)
def members_page(workspace_id: uuid.UUID, request: Request, db: DbSession):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()
    uyelik = uyelik_bul(request, db, user, workspace_id)
    if uyelik is None:
        return HTMLResponse("Bulunamadı.", status_code=404)
    if not izin_var_mi(db, user, "ekip.gor"):
        # 404, 403 degil: yetkisi olmayan kisiye sayfanin VARLIGI bile
        # bilgi verir. "Yok" demek en az bilgi sizdiran cevaptir.
        return HTMLResponse("Bulunamadı.", status_code=404)
    return _ekip_sayfasi(request, db, user, uyelik, db.get(Workspace, workspace_id))


@router.post("/musteri/{workspace_id}/ekip/ekle")
def member_add(
    workspace_id: uuid.UUID,
    request: Request,
    db: DbSession,
    email: Annotated[str, Form()],
):
    """Var olan bir kullaniciyi bu musteriye atar.

    Yetki SORULMAZ: kisinin yetkileri zaten kendisinde tanimlidir.
    """
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()
    uyelik = uyelik_bul(request, db, user, workspace_id)
    if uyelik is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    workspace = db.get(Workspace, workspace_id)
    if not izin_var_mi(db, user, "ekip.yonet"):
        return _ekip_sayfasi(
            request, db, user, uyelik, workspace,
            error="Ekibi yönetme yetkiniz yok.",
            kod=status.HTTP_403_FORBIDDEN,
        )

    hedef = db.execute(
        select(User).where(User.email == email.strip().lower())
    ).scalar_one_or_none()
    if hedef is None:
        return _ekip_sayfasi(
            request, db, user, uyelik, workspace,
            error="Bu e-posta ile kayıtlı bir kullanıcı yok. Önce hesabı açılmalı.",
            kod=status.HTTP_404_NOT_FOUND,
        )

    db.add(WorkspaceMember(workspace_id=workspace_id, user_id=hedef.id))
    kaydet(
        db, action="ekip.ekle", actor_user_id=user.id, workspace_id=workspace_id,
        subject_type="user", subject_id=hedef.id, request=request,
        details={"email": hedef.email},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _ekip_sayfasi(
            request, db, user, uyelik, workspace,
            error="Bu kişi zaten ekipte.", kod=status.HTTP_409_CONFLICT,
        )

    return _ekip_sayfasi(
        request, db, user, uyelik, workspace, ok=f"{hedef.email} ekibe eklendi."
    )


@router.post("/musteri/{workspace_id}/ekip/cikar")
def member_remove(
    workspace_id: uuid.UUID,
    request: Request,
    db: DbSession,
    user_id: Annotated[uuid.UUID, Form()],
):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()
    uyelik = uyelik_bul(request, db, user, workspace_id)
    if uyelik is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    workspace = db.get(Workspace, workspace_id)
    if not izin_var_mi(db, user, "ekip.yonet"):
        return _ekip_sayfasi(
            request, db, user, uyelik, workspace,
            error="Ekibi yönetme yetkiniz yok.",
            kod=status.HTTP_403_FORBIDDEN,
        )
    if user_id == user.id:
        # Kendini cikarmak, o musteriye erisimi aninda keserdi.
        return _ekip_sayfasi(
            request, db, user, uyelik, workspace,
            error="Kendinizi çıkaramazsınız.", kod=status.HTTP_400_BAD_REQUEST,
        )

    hedef_uyelik = db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    ).scalar_one_or_none()
    if hedef_uyelik is None:
        return _ekip_sayfasi(
            request, db, user, uyelik, workspace,
            error="Bu kişi ekipte değil.", kod=status.HTTP_404_NOT_FOUND,
        )

    db.delete(hedef_uyelik)
    kaydet(
        db, action="ekip.cikar", actor_user_id=user.id, workspace_id=workspace_id,
        subject_type="user", subject_id=user_id, request=request,
    )
    db.commit()
    return _ekip_sayfasi(
        request, db, user, uyelik, workspace, ok="Kişi ekipten çıkarıldı."
    )



def _ayarlar_sayfasi(
    request, db, user, *, error=None, ok=None, kod=200, sinama=None
):
    """`sinama`: (anahtar, basarili, mesaj) — sinama sonucunu gosterir."""
    return templates.TemplateResponse(
        request, "settings.html",
        {
            "user": user,
            "aktif": "ayarlar",
            "ayarlar": durum_listesi(db),
            "sinanabilir": set(SINAYICILAR),
            "sinama": sinama,
            "error": error,
            "ok": ok,
        },
        status_code=kod,
    )


@router.get("/ayarlar", response_class=HTMLResponse)
def settings_page(request: Request, db: DbSession):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()
    if not user.is_superuser:
        # 404: bu sayfanin varligini yetkisiz kisiye bildirmeye gerek yok.
        return HTMLResponse("Bulunamadı.", status_code=404)
    return _ayarlar_sayfasi(request, db, user)


@router.post("/ayarlar")
def settings_save(
    request: Request,
    db: DbSession,
    anahtar: Annotated[str, Form()],
    deger: Annotated[str, Form()] = "",
):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()
    if not user.is_superuser:
        return HTMLResponse("Bulunamadı.", status_code=404)

    if anahtar not in AYAR_ANAHTARLARI:
        return _ayarlar_sayfasi(
            request, db, user, error="Bilinmeyen ayar.",
            kod=status.HTTP_400_BAD_REQUEST,
        )
    if not deger.strip():
        return _ayarlar_sayfasi(
            request, db, user,
            error="Değer boş bırakılamaz. Silmek istiyorsanız 'Bu değeri sil' düğmesini kullanın.",
            kod=status.HTTP_400_BAD_REQUEST,
        )

    deger_yaz(db, anahtar, deger, user_id=user.id)
    db.commit()
    # Kaydedilen degerin KENDISI yanitta yer almaz.
    return _ayarlar_sayfasi(request, db, user, ok=f"{anahtar} kaydedildi.")


@router.post("/ayarlar/sina")
def settings_test(
    request: Request,
    db: DbSession,
    anahtar: Annotated[str, Form()],
):
    """Kayitli ayarin gercekten calistigini sunucudan dogrular.

    Sonuc mesaji anahtarin kendisini ICERMEZ.
    """
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()
    if not user.is_superuser:
        return HTMLResponse("Bulunamadı.", status_code=404)

    if anahtar not in SINAYICILAR:
        return _ayarlar_sayfasi(
            request, db, user, error="Bu ayar için sınama tanımlı değil.",
            kod=status.HTTP_400_BAD_REQUEST,
        )

    basarili, mesaj = sina(db, anahtar)
    return _ayarlar_sayfasi(request, db, user, sinama=(anahtar, basarili, mesaj))


@router.post("/ayarlar/sil")
def settings_delete(
    request: Request,
    db: DbSession,
    anahtar: Annotated[str, Form()],
):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()
    if not user.is_superuser:
        return HTMLResponse("Bulunamadı.", status_code=404)

    if anahtar not in AYAR_ANAHTARLARI:
        return _ayarlar_sayfasi(
            request, db, user, error="Bilinmeyen ayar.",
            kod=status.HTTP_400_BAD_REQUEST,
        )

    silindi = deger_sil(db, anahtar)
    db.commit()
    return _ayarlar_sayfasi(
        request, db, user,
        ok=f"{anahtar} silindi." if silindi else f"{anahtar} zaten tanımlı değildi.",
    )


# --- Kampanyalar -------------------------------------------------------------

def _tarih_coz(metin: str) -> dt.date | None:
    """Form tarihini cozer. Bos veya hatali ise None doner."""
    metin = (metin or "").strip()
    if not metin:
        return None
    try:
        return dt.date.fromisoformat(metin)
    except ValueError:
        return None


def _kampanya_sayfasi(request, db, user, uyelik, workspace, *, error=None, ok=None, kod=200):
    marka = db.execute(
        select(Brand).where(Brand.workspace_id == workspace.id)
    ).scalars().first()

    kampanyalar = []
    if marka is not None:
        kampanyalar = db.execute(
            select(Campaign)
            .where(Campaign.workspace_id == workspace.id)
            .order_by(Campaign.starts_on.desc().nullslast(), Campaign.created_at.desc())
        ).scalars().all()

    return templates.TemplateResponse(
        request, "campaigns.html",
        {
            "user": user,
            "aktif": "kampanya",
            "workspace": workspace,
            "marka": marka,
            "kampanyalar": kampanyalar,
            "status_labels": STATUS_LABELS,
            "duzenleyebilir": izin_var_mi(db, user, "kampanya.yonet"),
            "error": error,
            "ok": ok,
        },
        status_code=kod,
    )


@router.get("/musteri/{workspace_id}/kampanya", response_class=HTMLResponse)
def campaigns_page(workspace_id: uuid.UUID, request: Request, db: DbSession):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()
    uyelik = uyelik_bul(request, db, user, workspace_id)
    if uyelik is None:
        return HTMLResponse("Bulunamadı.", status_code=404)
    return _kampanya_sayfasi(request, db, user, uyelik, db.get(Workspace, workspace_id))


@router.post("/musteri/{workspace_id}/kampanya")
def campaign_create(
    workspace_id: uuid.UUID,
    request: Request,
    db: DbSession,
    ad: Annotated[str, Form()],
    hedef: Annotated[str, Form()] = "",
    baslangic: Annotated[str, Form()] = "",
    bitis: Annotated[str, Form()] = "",
):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()
    uyelik = uyelik_bul(request, db, user, workspace_id)
    if uyelik is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    workspace = db.get(Workspace, workspace_id)
    if not izin_var_mi(db, user, "kampanya.yonet"):
        return _kampanya_sayfasi(
            request, db, user, uyelik, workspace,
            error="Bu işlem için en az stratejist yetkisi gerekir.",
            kod=status.HTTP_403_FORBIDDEN,
        )

    marka = db.execute(
        select(Brand).where(Brand.workspace_id == workspace_id)
    ).scalars().first()
    if marka is None:
        return _kampanya_sayfasi(
            request, db, user, uyelik, workspace,
            error="Önce marka bilgilerini girmeniz gerekiyor.",
            kod=status.HTTP_400_BAD_REQUEST,
        )

    ad = ad.strip()
    if len(ad) < 2:
        return _kampanya_sayfasi(
            request, db, user, uyelik, workspace,
            error="Kampanya adı en az 2 karakter olmalı.",
            kod=status.HTTP_400_BAD_REQUEST,
        )

    basi = _tarih_coz(baslangic)
    sonu = _tarih_coz(bitis)
    # Bitis baslangictan once olamaz; sessizce kabul edilirse raporlama
    # sonradan anlamsiz sonuc uretir.
    if basi and sonu and sonu < basi:
        return _kampanya_sayfasi(
            request, db, user, uyelik, workspace,
            error="Bitiş tarihi başlangıçtan önce olamaz.",
            kod=status.HTTP_400_BAD_REQUEST,
        )

    db.add(Campaign(
        workspace_id=workspace_id, brand_id=marka.id, name=ad,
        objective=hedef.strip() or None, starts_on=basi, ends_on=sonu,
    ))
    db.commit()
    return _kampanya_sayfasi(
        request, db, user, uyelik, workspace, ok=f"'{ad}' kampanyası oluşturuldu."
    )


@router.post("/musteri/{workspace_id}/kampanya/sil")
def campaign_delete(
    workspace_id: uuid.UUID,
    request: Request,
    db: DbSession,
    kampanya_id: Annotated[uuid.UUID, Form()],
):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()
    uyelik = uyelik_bul(request, db, user, workspace_id)
    if uyelik is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    workspace = db.get(Workspace, workspace_id)
    if not izin_var_mi(db, user, "kampanya.yonet"):
        return _kampanya_sayfasi(
            request, db, user, uyelik, workspace,
            error="Bu işlem için en az stratejist yetkisi gerekir.",
            kod=status.HTTP_403_FORBIDDEN,
        )

    # Calisma alani kontrolu sorgunun ICINDE: baska musterinin kampanyasi
    # kimligi bilinse bile silinemez.
    kampanya = db.execute(
        select(Campaign).where(
            Campaign.id == kampanya_id,
            Campaign.workspace_id == workspace_id,
        )
    ).scalar_one_or_none()
    if kampanya is None:
        return _kampanya_sayfasi(
            request, db, user, uyelik, workspace,
            error="Kampanya bulunamadı.", kod=status.HTTP_404_NOT_FOUND,
        )

    db.delete(kampanya)
    db.commit()
    return _kampanya_sayfasi(request, db, user, uyelik, workspace, ok="Kampanya silindi.")


# --- Bagli hesaplar ----------------------------------------------------------
#
# DURUSTLUK KURALI: "Bagla" dugmesi YALNIZCA platform gercekten hazirsa
# gosterilir. Hazir olmayan platformda dugme yerine NEDEN hazir olmadigi ve
# hangi ayarlarin eksik oldugu yazilir. Calismayan bir dugme gostermek,
# kullaniciya olmayan bir yetenek varmis gibi sunmaktir.

PLATFORM_ETIKETLERI = {
    "instagram": "Instagram",
    "facebook": "Facebook",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "linkedin": "LinkedIn",
    "x": "X",
    "pinterest": "Pinterest",
}

# Ilk surumde yalnizca Meta platformlari hedefleniyor; digerleri listede
# gereksiz gurultu yapmasin.
PANELDE_GOSTERILEN_PLATFORMLAR = ("instagram", "facebook")


def _eksik_meta_ayarlari() -> list[str]:
    """Baglanti icin eksik olan alanlar (panel ayarlari dahil)."""
    from app.platforms.meta_ayar import meta_ayarlarini_oku

    return meta_ayarlarini_oku().eksikler


def _sahte_platform_modu() -> bool:
    """Sistem GERCEKTEN sahte veriyle mi calisiyor?

    Ortam degiskenine degil, ortaya cikan duruma bakar: Meta bilgileri
    girilmisse sahte mod yoktur, gercek baglanti yapilir.
    """
    from app.core.config import get_settings
    from app.platforms.meta_ayar import meta_hazir_mi

    return get_settings().platform_mode == "fake" and not meta_hazir_mi()


def _hesaplar_sayfasi(
    request, db, user, uyelik, workspace, *,
    error=None, ok=None, uyari=None, kod=200,
):
    from app.platforms.meta_ayar import meta_ayarlarini_oku

    durumlar = {d["platform"]: d for d in platform_status()}
    meta_ayar = meta_ayarlarini_oku()
    meta_eksikler = meta_ayar.eksikler

    sahte = _sahte_platform_modu()
    platformlar = []
    for ad in PANELDE_GOSTERILEN_PLATFORMLAR:
        durum = durumlar.get(ad, {})
        platformlar.append(
            {
                "platform": ad,
                "etiket": PLATFORM_ETIKETLERI.get(ad, ad),
                # Sahte adaptor "saglikli" der ama gercek hesap baglayamaz.
                # Bunu "baglanabilir" diye gostermek yalan olurdu.
                "available": bool(durum.get("available")) and not sahte,
                "detail": durum.get("detail") or "Ayrıntı bildirilmedi.",
                "eksik_ayarlar": meta_eksikler if not durum.get("available") else [],
            }
        )

    return templates.TemplateResponse(
        request, "accounts.html",
        {
            "user": user,
            "aktif": "hesaplar",
            "workspace": workspace,
            "yol": "Bağlı hesaplar",
            "hesaplar": db.execute(
                select(SocialAccount)
                .where(SocialAccount.workspace_id == workspace.id)
                .order_by(SocialAccount.created_at)
            ).scalars().all(),
            "platformlar": platformlar,
            "baglayabilir": izin_var_mi(db, user, "hesap.bagla"),
            # Sahte modda "Bagla" dugmesi GOSTERILMEZ: basilsa gercek bir
            # hesap baglanmaz, yalnizca ornek veri uretilir. Calisiyormus
            # gibi gostermek yaniltici olur.
            "sahte_mod": sahte,
            # Meta'ya girilecek donus adresi: birebir ayni olmali, bu yuzden
            # kullanicinin kopyalayabilecegi sekilde gosterilir.
            "donus_adresi": meta_ayar.redirect_uri,
            "izinler": meta_ayar.scopes,
            "eksik_ayarlar": meta_eksikler,
            "sistem_yoneticisi": user.is_superuser,
            "error": error,
            "ok": ok,
            "uyari": uyari,
        },
        status_code=kod,
    )


@router.get("/musteri/{workspace_id}/hesaplar", response_class=HTMLResponse)
def accounts_page(
    workspace_id: uuid.UUID,
    request: Request,
    db: DbSession,
    baglandi: str = "",
    hata: str = "",
    uyari: str = "",
):
    """Bagli hesaplar.

    `baglandi`/`hata`/`uyari`: Meta izin ekranindan donuste sonucun
    kullaniciya gosterilmesi icin.
    """
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()
    uyelik = uyelik_bul(request, db, user, workspace_id)
    if uyelik is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    if not izin_var_mi(db, user, "hesap.gor"):
        # 404, 403 degil: yetkisi olmayan kisiye sayfanin VARLIGI bile
        # bilgi verir. "Yok" demek en az bilgi sizdiran cevaptir.
        return HTMLResponse("Bulunamadı.", status_code=404)

    return _hesaplar_sayfasi(
        request, db, user, uyelik, db.get(Workspace, workspace_id),
        ok=(f"{baglandi} hesabı bağlandı." if baglandi else None),
        error=hata or None,
        uyari=uyari or None,
    )


@router.post("/musteri/{workspace_id}/hesaplar/baglan")
def account_connect(
    workspace_id: uuid.UUID,
    request: Request,
    db: DbSession,
    platform: Annotated[str, Form()],
):
    """Izin akisini baslatir.

    Platform hazir DEGILSE hicbir sey yapmaz ve nedenini gosterir. Boylece
    yapilandirilmamis bir platforma yonlendirme uretilmez.
    """
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()
    uyelik = uyelik_bul(request, db, user, workspace_id)
    if uyelik is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    workspace = db.get(Workspace, workspace_id)
    if not izin_var_mi(db, user, "hesap.bagla"):
        return _hesaplar_sayfasi(
            request, db, user, uyelik, workspace,
            error="Hesap bağlamak için en az yönetici yetkisi gerekir.",
            kod=status.HTTP_403_FORBIDDEN,
        )

    try:
        secilen = Platform(platform)
    except ValueError:
        return _hesaplar_sayfasi(
            request, db, user, uyelik, workspace,
            error="Geçersiz platform.", kod=status.HTTP_400_BAD_REQUEST,
        )

    if _sahte_platform_modu():
        return _hesaplar_sayfasi(
            request, db, user, uyelik, workspace,
            error=(
                "Sistem şu an sahte sağlayıcı ile çalışıyor. Bu modda gerçek "
                "bir hesap bağlanamaz; bağlanmış gibi göstermeyeceğiz."
            ),
            kod=status.HTTP_409_CONFLICT,
        )

    durum = next(
        (d for d in platform_status() if d["platform"] == secilen.value), None
    )
    if durum is None or not durum["available"]:
        return _hesaplar_sayfasi(
            request, db, user, uyelik, workspace,
            error=(
                "Bu platform henüz bağlanamıyor. Eksik ayarlar aşağıda yazıyor; "
                "bunlar resmî dokümandan doğrulanmadan doldurulmayacak."
            ),
            kod=status.HTTP_409_CONFLICT,
        )

    # Izin adresi BURADA uretilir.
    #
    # Daha once API ucuna yonlendiriliyordu ve DUGME HIC CALISMIYORDU:
    # o uc POST bekliyor ve Bearer anahtari istiyor; tarayicinin izledigi
    # yonlendirme ise GET ve cerezle gelir. Panel kendi oturumuyla
    # yetkilendirildigi icin akisi dogrudan baslatmasi hem calisir hem
    # de dogrudur.
    ayar = meta_ayarlarini_oku()
    if not ayar.redirect_uri:
        return _hesaplar_sayfasi(
            request, db, user, uyelik, workspace,
            error=(
                "Dönüş adresi (META_REDIRECT_URI) belirlenemedi. "
                "Sistem ayarlarından girin."
            ),
            kod=status.HTTP_409_CONFLICT,
        )

    state = create_state(
        workspace_id=workspace_id,
        user_id=user.id,
        platform=secilen.value,
        redirect_uri=ayar.redirect_uri,
    )

    try:
        izin = get_adapter(secilen).authorize(
            state=state, redirect_uri=ayar.redirect_uri
        )
    except PlatformError as hata:
        return _hesaplar_sayfasi(
            request, db, user, uyelik, workspace,
            error=f"İzin adresi üretilemedi: {hata}",
            kod=status.HTTP_409_CONFLICT,
        )

    kaydet(
        db, action="social_account.baglama_baslatildi", actor_user_id=user.id,
        workspace_id=workspace_id, request=request,
        details={"platform": secilen.value},
    )
    db.commit()

    # Kullanici Meta'nin izin ekranina gider. Girisi ve izni KENDISI yapar;
    # sifresi bize hicbir zaman ulasmaz.
    return RedirectResponse(izin.url, status_code=status.HTTP_303_SEE_OTHER)


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

    uyelik = uyelik_bul(request, db, user, workspace_id)
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
            "allowed_targets": _izinli_hedefler(
                db, user, s.status, "content_script",
            ),
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

    uyelik = uyelik_bul(request, db, user, workspace_id)
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
            db, workspace_id=workspace_id, actor=user, subject=s,
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

    uyelik = uyelik_bul(request, db, user, workspace_id)
    if uyelik is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    if not izin_var_mi(db, user, "rapor.gor"):
        # 404, 403 degil: yetkisi olmayan kisiye sayfanin VARLIGI bile
        # bilgi verir. "Yok" demek en az bilgi sizdiran cevaptir.
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
            "allowed_targets": _izinli_hedefler(
                db, user, r.status, "report",
            ),
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

    uyelik = uyelik_bul(request, db, user, workspace_id)
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
            db, workspace_id=workspace_id, actor=user, subject=r,
            target=ContentStatus(target), comment=comment or None,
        )
        db.commit()
    except (ApprovalError, ValueError) as exc:
        db.rollback()
        from urllib.parse import quote

        return RedirectResponse(f"{temel}?error={quote(str(exc))}", status_code=303)

    return RedirectResponse(temel, status_code=303)
