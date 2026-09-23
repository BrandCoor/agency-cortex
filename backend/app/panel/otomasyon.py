"""Otomasyon sayfasi.

KULLANICI n8n'E GIRMEK ZORUNDA DEGILDIR. Hangi is akisinin acik oldugu,
en son ne zaman calistigi, basarili mi oldugu ve hata verdiyse ne dedigi
burada gorunur.

Iki bolum var ve YETKILERI FARKLIDIR:
- Is akislari: kullanicinin YONETICI oldugu musteriler icin acilip kapanir
- API anahtarlari: yalnizca SISTEM YONETICISI; cunku bir anahtar birden
  fazla musteriyi kapsar
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
from app.cli.otomasyon import OTOMATIK_AD as OTOMATIK_ANAHTAR_ADI
from app.core.config import get_settings
from app.models.enums import AutomationTrigger
from app.models.identity import User, Workspace, WorkspaceMember
from app.models.otomasyon import ApiClient
from app.panel.auth import current_user_from_cookie
from app.panel.ortak import uyelik_bul
from app.services.denetim import kaydet
from app.services.makine_kimligi import (
    MakineKimligiHatasi,
    iptal_et,
    olustur,
    yetki_ver,
    yetkili_workspace_idleri,
)
from app.services.otomasyon import (
    IS_AKISLARI,
    OtomasyonHatasi,
    akis_durumlari,
    ayar_yaz,
    calistirma_baslat,
    son_calistirmalar,
)
from app.services.yetkiler import izin_var_mi

router = APIRouter(prefix="/panel/otomasyon", tags=["panel"])
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _giris_yonlendir() -> RedirectResponse:
    return RedirectResponse("/panel/giris", status_code=status.HTTP_303_SEE_OTHER)


def _uyelikler(db, user: User) -> list[tuple[WorkspaceMember, Workspace]]:
    return list(
        db.execute(
            select(WorkspaceMember, Workspace)
            .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
            .where(WorkspaceMember.user_id == user.id)
            .order_by(Workspace.name)
        ).all()
    )


def _sayfa(request, db, user, *, error=None, ok=None, anahtar=None, kod=200):
    uyelikler = _uyelikler(db, user)

    musteriler = [
        {
            "id": str(w.id),
            "ad": w.name,
            "yonetebilir": izin_var_mi(db, user, "otomasyon.ayar"),
            "calistirabilir": izin_var_mi(db, user, "otomasyon.calistir"),
            "akislar": akis_durumlari(db, w.id),
            "son_calistirmalar": [
                {
                    "akis": r.workflow_key,
                    "durum": r.status.value,
                    "baslangic": r.started_at,
                    "bitis": r.finished_at,
                    "hata": r.error_message,
                    "ozet": r.summary,
                    "tetik": r.trigger.value,
                }
                for r in son_calistirmalar(db, w.id, limit=8)
            ],
        }
        for m, w in uyelikler
    ]

    ayarlar = get_settings()

    # n8n gercekten bagli mi? Otomatik anahtarin kullanilmis olmasi,
    # n8n'in Agency Cortex'e ulastiginin KANITIDIR. "Kurdum" demek yerine
    # olculen bir sey gosteriliyor.
    otomatik = db.execute(
        select(ApiClient).where(
            ApiClient.name == OTOMATIK_ANAHTAR_ADI,
            ApiClient.is_active.is_(True),
        )
    ).scalar_one_or_none()

    if otomatik is None:
        n8n_durum = {
            "asama": "bekliyor",
            "baslik": "n8n hesabınız henüz oluşturulmadı",
            "aciklama": (
                "İş akışları n8n'e yüklenebilmesi için önce n8n'de sizin "
                "hesabınızın olması gerekiyor. Aşağıdaki adrese girip hesabınızı "
                "oluşturun; iş akışları birkaç dakika içinde kendiliğinden kurulur."
            ),
        }
    elif otomatik.last_used_at is None:
        n8n_durum = {
            "asama": "kuruldu",
            "baslik": "İş akışları kuruldu, ilk çalışma bekleniyor",
            "aciklama": (
                "n8n bağlantısı hazır ama henüz hiç çalışmadı. Akışlar "
                "zamanları geldiğinde çalışacak. Beklemek istemiyorsanız "
                "aşağıdan elle çalıştırabilirsiniz."
            ),
        }
    else:
        n8n_durum = {
            "asama": "calisiyor",
            "baslik": "n8n bağlı ve çalışıyor",
            "aciklama": (
                "Son bağlantı: "
                + otomatik.last_used_at.strftime("%d.%m.%Y %H:%M")
            ),
        }

    anahtarlar = []
    tum_musteriler = []
    n8n_giris = None
    if user.is_superuser:
        # n8n kapisinin sifresi: kullanicinin arayacagi tek yer burasi.
        # Sohbete veya loga YAZILMAZ; yalnizca oturum acmis sistem
        # yoneticisine gosterilir.
        if ayarlar.n8n_domain:
            n8n_giris = {
                "adres": f"https://{ayarlar.n8n_domain}",
                "kullanici": ayarlar.n8n_basic_user,
                "sifre": ayarlar.n8n_basic_password,
            }
        kayitlar = db.execute(
            select(ApiClient).order_by(ApiClient.created_at.desc())
        ).scalars().all()
        adlar = {
            w.id: w.name
            for w in db.execute(select(Workspace)).scalars().all()
        }
        anahtarlar = [
            {
                "id": str(k.id),
                "ad": k.name,
                "onek": k.key_prefix,
                "etkin": k.is_active and k.revoked_at is None,
                "son_kullanim": k.last_used_at,
                "iptal": k.revoked_at,
                "tum_musteriler": k.all_workspaces,
                "musteri_idleri": [str(i) for i in yetkili_workspace_idleri(db, k.id)],
                "musteri_adlari": [
                    adlar.get(i, "?") for i in yetkili_workspace_idleri(db, k.id)
                ],
            }
            for k in kayitlar
        ]
        tum_musteriler = [
            {"id": str(w.id), "ad": w.name}
            for w in db.execute(
                select(Workspace).where(Workspace.is_active.is_(True))
                .order_by(Workspace.name)
            ).scalars().all()
        ]

    return templates.TemplateResponse(
        request, "automation.html",
        {
            "user": user,
            "aktif": "otomasyon",
            "workspace": None,
            "yol": "Otomasyon",
            "musteriler": musteriler,
            "is_akislari": IS_AKISLARI,
            "anahtarlar": anahtarlar,
            "tum_musteriler": tum_musteriler,
            "yeni_anahtar": anahtar,
            "n8n_giris": n8n_giris,
            "n8n_durum": n8n_durum,
            "error": error,
            "ok": ok,
        },
        status_code=kod,
    )


@router.get("", response_class=HTMLResponse)
def otomasyon_sayfasi(request: Request, db: DbSession):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()
    return _sayfa(request, db, user)


@router.post("/akis")
def akis_degistir(
    request: Request,
    db: DbSession,
    workspace_id: Annotated[uuid.UUID, Form()],
    workflow_key: Annotated[str, Form()],
    acik: Annotated[str, Form()] = "",
):
    """Bir musteride bir is akisini acar veya kapatir."""
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()

    uyelik = uyelik_bul(request, db, user, workspace_id)
    # Uye degilse 404: musterinin varligi ele verilmez.
    if uyelik is None:
        return HTMLResponse("Bulunamadı.", status_code=404)
    if not izin_var_mi(db, user, "otomasyon.ayar"):
        return _sayfa(
            request, db, user,
            error="İş akışını açıp kapatma yetkiniz yok.",
            kod=status.HTTP_403_FORBIDDEN,
        )

    try:
        ayar_yaz(db, workspace_id, workflow_key, acik=bool(acik))
    except OtomasyonHatasi as hata:
        db.rollback()
        return _sayfa(request, db, user, error=str(hata), kod=status.HTTP_400_BAD_REQUEST)

    kaydet(
        db, action="otomasyon.akis_ayari", actor_user_id=user.id,
        workspace_id=workspace_id, request=request,
        details={"workflow_key": workflow_key, "acik": bool(acik)},
    )
    db.commit()
    durum = "açıldı" if acik else "kapatıldı"
    return _sayfa(request, db, user, ok=f"İş akışı {durum}.")


# --- API anahtarlari (yalnizca sistem yoneticisi) ----------------------------

def _yonetici(request, db) -> User | None:
    user = current_user_from_cookie(request, db)
    if user is None or not user.is_superuser:
        return None
    return user


@router.post("/anahtar/ekle")
def anahtar_ekle(
    request: Request,
    db: DbSession,
    ad: Annotated[str, Form()],
    workspace_ids: Annotated[list[uuid.UUID], Form()] = [],  # noqa: B006
    tum_musteriler: Annotated[str, Form()] = "",
):
    user = _yonetici(request, db)
    if user is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    try:
        kayit, tam_anahtar = olustur(
            db, ad=ad, olusturan_user_id=user.id, workspace_ids=list(workspace_ids),
            tum_musteriler=bool(tum_musteriler),
        )
    except MakineKimligiHatasi as hata:
        db.rollback()
        return _sayfa(request, db, user, error=str(hata), kod=status.HTTP_400_BAD_REQUEST)

    # Anahtarin KENDISI denetime yazilmaz; yalnizca uretildigi ve kapsami.
    kaydet(
        db, action="makine_kimligi.olustur", actor_user_id=user.id,
        subject_type="api_client", subject_id=kayit.id, request=request,
        details={
            "ad": kayit.name,
            "musteri_sayisi": len(workspace_ids),
            "tum_musteriler": kayit.all_workspaces,
        },
    )
    db.commit()
    return _sayfa(
        request, db, user, anahtar={"ad": kayit.name, "deger": tam_anahtar},
        ok=f"'{kayit.name}' anahtarı üretildi.",
    )


@router.post("/anahtar/yetki")
def anahtar_yetki(
    request: Request,
    db: DbSession,
    api_client_id: Annotated[uuid.UUID, Form()],
    workspace_ids: Annotated[list[uuid.UUID], Form()] = [],  # noqa: B006
):
    user = _yonetici(request, db)
    if user is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    kayit = db.get(ApiClient, api_client_id)
    if kayit is None:
        return _sayfa(
            request, db, user, error="Anahtar bulunamadı.",
            kod=status.HTTP_404_NOT_FOUND,
        )

    if kayit.all_workspaces:
        return _sayfa(
            request, db, user,
            error=(
                "Bu anahtar 'tüm müşteriler' kapsamında. Kapsamı daraltmak için "
                "iptal edip yeni bir anahtar üretin."
            ),
            kod=status.HTTP_400_BAD_REQUEST,
        )

    try:
        yetki_ver(db, kayit, list(workspace_ids))
    except MakineKimligiHatasi as hata:
        db.rollback()
        return _sayfa(request, db, user, error=str(hata), kod=status.HTTP_400_BAD_REQUEST)

    kaydet(
        db, action="makine_kimligi.yetki", actor_user_id=user.id,
        subject_type="api_client", subject_id=kayit.id, request=request,
        details={"musteri_sayisi": len(workspace_ids)},
    )
    db.commit()
    return _sayfa(request, db, user, ok=f"'{kayit.name}' kapsamı güncellendi.")


@router.post("/anahtar/iptal")
def anahtar_iptal(
    request: Request,
    db: DbSession,
    api_client_id: Annotated[uuid.UUID, Form()],
):
    user = _yonetici(request, db)
    if user is None:
        return HTMLResponse("Bulunamadı.", status_code=404)

    kayit = db.get(ApiClient, api_client_id)
    if kayit is None:
        return _sayfa(
            request, db, user, error="Anahtar bulunamadı.",
            kod=status.HTTP_404_NOT_FOUND,
        )

    iptal_et(db, kayit)
    kaydet(
        db, action="makine_kimligi.iptal", actor_user_id=user.id,
        subject_type="api_client", subject_id=kayit.id, request=request,
        details={"ad": kayit.name},
    )
    db.commit()
    return _sayfa(
        request, db, user,
        ok=f"'{kayit.name}' iptal edildi. Bu anahtarla artık bağlanılamaz.",
    )


@router.post("/calistir")
def elle_calistir(
    request: Request,
    db: DbSession,
    workspace_id: Annotated[uuid.UUID, Form()],
    workflow_key: Annotated[str, Form()],
):
    """Bir is akisini SIMDI calistirir.

    Is KUYRUGA alinir, panelde beklenmez: bir arastirma akisi dakikalarca
    surebilir ve tarayici zaman asimina ugrardi. Sonuc bu sayfadan
    takip edilir.
    """
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()

    uyelik = uyelik_bul(request, db, user, workspace_id)
    if uyelik is None:
        return HTMLResponse("Bulunamadı.", status_code=404)
    if not izin_var_mi(db, user, "otomasyon.calistir"):
        return _sayfa(
            request, db, user,
            error="İş akışını elle çalıştırma yetkiniz yok.",
            kod=status.HTTP_403_FORBIDDEN,
        )

    try:
        kayit = calistirma_baslat(
            db,
            workspace_id=workspace_id,
            workflow_key=workflow_key,
            trigger=AutomationTrigger.MANUAL,
        )
    except OtomasyonHatasi as hata:
        db.rollback()
        return _sayfa(request, db, user, error=str(hata), kod=status.HTTP_409_CONFLICT)

    kaydet(
        db, action="otomasyon.elle_calistir", actor_user_id=user.id,
        workspace_id=workspace_id, subject_type="automation_run",
        subject_id=kayit.id, request=request,
        details={"workflow_key": workflow_key},
    )
    db.commit()

    from app.workers.tasks import otomasyon_akisi_calistir

    try:
        otomasyon_akisi_calistir.delay(
            workspace_id=str(workspace_id),
            workflow_key=workflow_key,
            run_id=str(kayit.id),
        )
    except Exception as hata:  # noqa: BLE001 - kuyruga atilamadi, gizlenmez
        from app.services.otomasyon import calistirma_bitir

        calistirma_bitir(
            db, kayit, basarili=False,
            hata_mesaji=f"İş kuyruğa alınamadı: {type(hata).__name__}: {hata}",
        )
        db.commit()
        return _sayfa(
            request, db, user,
            error=(
                "İş kuyruğa alınamadı. Arka plan servisi çalışmıyor olabilir. "
                f"({type(hata).__name__})"
            ),
            kod=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return _sayfa(
        request, db, user,
        ok="İş akışı başlatıldı. Sonucu birkaç dakika içinde bu sayfada göreceksiniz.",
    )
