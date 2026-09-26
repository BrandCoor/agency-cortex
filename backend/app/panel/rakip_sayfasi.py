"""Rakip ve trend bulgulari sayfasi.

NE GOSTERIR: WF-02 (trend) ve WF-06 (rakip) akislarinin urettigi bulgular.

DURUSTLUK KURALLARI:
- Her bulgunun KAYNAGI ve GUVENILIRLIGI gorunur. Dusuk guvenilirlikli
  bulgu "kesin bilgi" gibi gosterilmez; hipotez olarak isaretlenir.
- Bulgu yoksa uydurma bir ozet uretilmez; neden olmadigi yazilir
  (akis kapali mi, rakip eklenmemis mi, anahtar mi eksik).
- Rakibin OZEL icgoru verisi (erisim, kaydetme, demografi) burada
  gorunmez; o veri yalnizca hesap sahibine aciktir.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from app.api.deps import DbSession
from app.models.identity import Workspace
from app.models.izlenen import IzlemeTuru, TrackedAccount
from app.models.otomasyon import AutomationSetting
from app.models.research import CompetitorObservation, TrendObservation
from app.panel.auth import current_user_from_cookie
from app.panel.ortak import uyelik_bul
from app.panel.sablon import templates
from app.services.denetim import kaydet
from app.services.ornek_veri_temizligi import say as ornek_veri_say
from app.services.ornek_veri_temizligi import temizle as ornek_veri_temizle
from app.services.yetkiler import izin_var_mi

router = APIRouter(prefix="/panel", tags=["panel"])

#: Kac gunluk bulgu gosterilir.
PENCERE_GUN = 30

GUVEN_ETIKETLERI = {
    "high": "yüksek güven",
    "medium": "orta güven",
    "low": "düşük güven — hipotez",
}


def _giris_yonlendir() -> RedirectResponse:
    return RedirectResponse("/panel/giris", status_code=status.HTTP_303_SEE_OTHER)


def _akis_acik_mi(db, workspace_id: uuid.UUID, anahtar: str) -> bool:
    ayar = db.execute(
        select(AutomationSetting).where(
            AutomationSetting.workspace_id == workspace_id,
            AutomationSetting.workflow_key == anahtar,
        )
    ).scalar_one_or_none()
    return bool(ayar and ayar.is_enabled)


@router.get("/musteri/{workspace_id}/rakip-trend", response_class=HTMLResponse)
def competitor_trend_page(workspace_id: uuid.UUID, request: Request, db: DbSession):
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()
    uyelik = uyelik_bul(request, db, user, workspace_id)
    if uyelik is None:
        return HTMLResponse("Bulunamadı.", status_code=404)
    # Rapor gorme izni olan bu bulgulari da gorur: ikisi de "okunan bilgi".
    if not izin_var_mi(db, user, "rapor.gor"):
        return HTMLResponse("Bulunamadı.", status_code=404)

    workspace = db.get(Workspace, workspace_id)
    sinir = datetime.now(UTC) - timedelta(days=PENCERE_GUN)

    trendler = list(db.execute(
        select(TrendObservation).where(
            TrendObservation.workspace_id == workspace_id,
            TrendObservation.observed_at >= sinir,
        ).order_by(TrendObservation.observed_at.desc()).limit(50)
    ).scalars().all())

    satirlar = list(db.execute(
        select(CompetitorObservation, TrackedAccount)
        .join(TrackedAccount, TrackedAccount.id == CompetitorObservation.tracked_account_id)
        .where(
            CompetitorObservation.workspace_id == workspace_id,
            CompetitorObservation.observed_at >= sinir,
        )
        .order_by(CompetitorObservation.observed_at.desc())
        .limit(50)
    ).all())

    rakip_sayisi = db.execute(
        select(TrackedAccount).where(
            TrackedAccount.workspace_id == workspace_id,
            TrackedAccount.tur == IzlemeTuru.RAKIP,
            TrackedAccount.is_active.is_(True),
        )
    ).scalars().all()

    return templates.TemplateResponse(
        request, "competitors.html",
        {
            "user": user,
            "aktif": "rakip",
            "workspace": workspace,
            "yol": "Rakip ve trend",
            "pencere_gun": PENCERE_GUN,
            "trendler": [
                {
                    "topic": t.topic,
                    "summary": t.summary,
                    "relevance": t.relevance_to_brand,
                    "platform": t.platform.value if t.platform else "genel",
                    "guven": GUVEN_ETIKETLERI.get(t.confidence or "", t.confidence or "—"),
                    "hipotez": (t.confidence or "") == "low",
                    "kaynaklar": list(t.source_urls or []),
                    "belirsizlikler": list(t.uncertainties or []),
                    "tarih": t.observed_at,
                }
                for t in trendler
            ],
            "rakip_bulgulari": [
                {
                    "username": hesap.username,
                    "platform": hesap.platform.value,
                    "summary": g.summary,
                    "onem": (g.data or {}).get("why_it_matters"),
                    "guven": GUVEN_ETIKETLERI.get(g.confidence or "", g.confidence or "—"),
                    "hipotez": (g.confidence or "") == "low",
                    "kaynaklar": list(g.source_urls or []),
                    "belirsizlikler": list(g.uncertainties or []),
                    "kaynak_turu": g.source_type,
                    "tarih": g.observed_at,
                }
                for g, hesap in satirlar
            ],
            "rakip_sayisi": len(rakip_sayisi),
            # Gecmiste ornek veri modunda yazilmis kayitlar. Artik
            # yazilmiyorlar ama eskiler duruyor; kullanici temizleyebilsin.
            "ornek_veri": ornek_veri_say(db, workspace_id),
            "temizleyebilir": izin_var_mi(db, user, "hesap.izle"),
            # NEDEN BOS: kullanici "bozuk mu?" diye sormasin diye.
            "trend_akisi_acik": _akis_acik_mi(db, workspace_id, "wf02_trend"),
            "rakip_akisi_acik": _akis_acik_mi(db, workspace_id, "wf06_rakip"),
        },
    )


@router.post("/musteri/{workspace_id}/rakip-trend/ornek-veri-temizle")
def ornek_veri_temizleme(
    workspace_id: uuid.UUID,
    request: Request,
    db: DbSession,
    onay: Annotated[str, Form()] = "",
):
    """Gecmiste ornek veri modunda yazilmis bulgulari siler.

    Silme geri alinamaz; bu yuzden form ACIK bir onay alani tasiyor.
    Silinen sey gercek bir bulgu degil, ornek metindir - ama yine de
    kullanicinin karari olmali.
    """
    user = current_user_from_cookie(request, db)
    if user is None:
        return _giris_yonlendir()
    uyelik = uyelik_bul(request, db, user, workspace_id)
    if uyelik is None:
        return HTMLResponse("Bulunamadı.", status_code=404)
    if not izin_var_mi(db, user, "hesap.izle"):
        return HTMLResponse("Bulunamadı.", status_code=404)
    if onay != "EVET":
        return HTMLResponse("Bulunamadı.", status_code=404)

    silinen = ornek_veri_temizle(db, workspace_id)
    kaydet(
        db, action="ornek_veri.temizlendi", actor_user_id=user.id,
        workspace_id=workspace_id, details=silinen, request=request,
    )
    db.commit()
    return RedirectResponse(
        f"/panel/musteri/{workspace_id}/rakip-trend",
        status_code=status.HTTP_303_SEE_OTHER,
    )
