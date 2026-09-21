"""n8n'in bagl andigi uclar (makine API'si).

MIMARI KURAL: n8n veritabanina DOGRUDAN YAZMAZ. Her sey buradan gecer,
cunku izolasyon, yetki, butce ve onay kurallari burada islerler.

EN KRITIK KURAL: istekle gelen `workspace_id`ye GUVENILMEZ. Her istekte
"bu makine kimligi bu musteride calisabilir mi" diye ayrica bakilir.
n8n'de yanlis bir ayar ya da ele gecirilmis bir akis, baska bir musterinin
verisine dokunamaz.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.logging_config import get_logger
from app.models.enums import AutomationTrigger
from app.models.identity import Workspace
from app.models.otomasyon import ApiClient, AutomationRun
from app.services.denetim import kaydet
from app.services.makine_kimligi import dogrula, yetkili_workspace_idleri
from app.services.otomasyon import (
    IS_AKISLARI,
    OtomasyonHatasi,
    akis_durumlari,
    calistirma_baslat,
    calistirma_bitir,
)

router = APIRouter(prefix="/api/v1/makine", tags=["makine (n8n)"])
log = get_logger("makine_api")

# Yetkisiz erisimde her zaman AYNI yanit. "Musteri yok" ile "yetkin yok"
# ayrimi yapilmaz; aksi halde bir musterinin VARLIGI ogrenilebilirdi.
_BULUNAMADI = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Musteri bulunamadi."
)


def makine_kimligi(
    db: Annotated[Session, Depends(get_db)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> ApiClient:
    """Anahtardan makine kimligini cozer."""
    kayit = dogrula(db, x_api_key)
    if kayit is None:
        # Hangi asamada takildigi SOYLENMEZ (anahtar yok mu, iptal mi).
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API anahtari gecersiz.",
        )
    db.commit()   # last_used_at kaydi
    return kayit


MakineKimligi = Annotated[ApiClient, Depends(makine_kimligi)]
DbSession = Annotated[Session, Depends(get_db)]


def yetkili_workspace(db: Session, kimlik: ApiClient, workspace_id: uuid.UUID) -> Workspace:
    """Bu makine kimligi bu musteride calisabilir mi?

    Istekle gelen workspace_id tek basina HICBIR SEY ifade etmez.
    """
    if workspace_id not in set(yetkili_workspace_idleri(db, kimlik.id)):
        log.warning(
            "makine_yetkisiz_musteri",
            api_client_id=str(kimlik.id),
            workspace_id=str(workspace_id),
        )
        raise _BULUNAMADI

    workspace = db.get(Workspace, workspace_id)
    if workspace is None or not workspace.is_active:
        raise _BULUNAMADI
    return workspace


# --- Kimlik ------------------------------------------------------------------

@router.get("/kendim", summary="Bu anahtar kimin, nerede calisabilir")
def kendim(kimlik: MakineKimligi, db: DbSession) -> dict:
    """n8n baslangicta buradan hangi musterilerde calisacagini ogrenir."""
    idler = yetkili_workspace_idleri(db, kimlik.id)
    musteriler = db.execute(
        select(Workspace).where(Workspace.id.in_(idler), Workspace.is_active.is_(True))
        .order_by(Workspace.name)
    ).scalars().all() if idler else []

    return {
        "ad": kimlik.name,
        "musteriler": [
            {
                "workspace_id": str(w.id),
                "ad": w.name,
                "slug": w.slug,
                "saat_dilimi": w.timezone,
                "akislar": [
                    {"anahtar": d["anahtar"], "ad": d["ad"], "acik": d["acik"]}
                    for d in akis_durumlari(db, w.id)
                ],
            }
            for w in musteriler
        ],
        "tanimli_akislar": [
            {"anahtar": a.anahtar, "ad": a.ad, "zamanlama": a.zamanlama}
            for a in IS_AKISLARI
        ],
    }


# --- Calistirma kaydi --------------------------------------------------------

class CalistirmaBaslat(BaseModel):
    workflow_key: str = Field(min_length=3, max_length=60)
    # n8n'in kendi calistirma kimligi: bir sorunda n8n kayitlarina bakilabilsin.
    external_execution_id: str | None = Field(default=None, max_length=100)


@router.post(
    "/workspaces/{workspace_id}/calistirma",
    status_code=status.HTTP_201_CREATED,
    summary="Is akisi calismaya basladi",
)
def calistirma_ac(
    workspace_id: uuid.UUID,
    govde: CalistirmaBaslat,
    kimlik: MakineKimligi,
    db: DbSession,
) -> dict:
    workspace = yetkili_workspace(db, kimlik, workspace_id)
    try:
        kayit = calistirma_baslat(
            db,
            workspace_id=workspace.id,
            workflow_key=govde.workflow_key,
            trigger=AutomationTrigger.SCHEDULE,
            api_client_id=kimlik.id,
            external_execution_id=govde.external_execution_id,
        )
    except OtomasyonHatasi as hata:
        # Akis kapaliysa veya tanimsizsa: 409. n8n bunu "atla" diye okur.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(hata)
        ) from hata

    db.commit()
    return {"run_id": str(kayit.id), "workflow_key": kayit.workflow_key}


class CalistirmaBitir(BaseModel):
    basarili: bool
    # Ham API yaniti DEGIL, sayisal ozet: "kac hesap tarandi" gibi.
    ozet: dict = Field(default_factory=dict)
    hata_mesaji: str | None = Field(default=None, max_length=2000)


@router.post("/calistirma/{run_id}/bitir", summary="Is akisi bitti")
def calistirma_kapat(
    run_id: uuid.UUID,
    govde: CalistirmaBitir,
    kimlik: MakineKimligi,
    db: DbSession,
) -> dict:
    kayit = db.get(AutomationRun, run_id)
    if kayit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kayit bulunamadi.")
    # Baskasinin calistirmasi kapatilamaz.
    yetkili_workspace(db, kimlik, kayit.workspace_id)

    try:
        calistirma_bitir(
            db, kayit, basarili=govde.basarili,
            ozet=govde.ozet, hata_mesaji=govde.hata_mesaji,
        )
    except OtomasyonHatasi as hata:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(hata)
        ) from hata

    if not govde.basarili:
        # Basarisizlik gizlenmez; denetime de yazilir.
        kaydet(
            db, action="otomasyon.basarisiz", workspace_id=kayit.workspace_id,
            subject_type="automation_run", subject_id=kayit.id,
            details={"workflow_key": kayit.workflow_key},
        )
    db.commit()
    return {"run_id": str(kayit.id), "durum": kayit.status.value}


# --- Musteri baglami ---------------------------------------------------------

@router.get(
    "/workspaces/{workspace_id}/baglam",
    summary="Is akisinin ihtiyaci olan musteri bilgisi",
)
def baglam(workspace_id: uuid.UUID, kimlik: MakineKimligi, db: DbSession) -> dict:
    """Marka ve bagli hesaplarin OZETI.

    Burada gizli bilgi YOKTUR: erisim anahtari, jeton veya sifre donmez.
    n8n'in dis servisle konusmasi gerekiyorsa bunu Agency Cortex uzerinden
    yapar; jetonlar n8n'e verilmez.
    """
    from app.models.brand import Brand, BrandGuideline
    from app.models.social import SocialAccount

    workspace = yetkili_workspace(db, kimlik, workspace_id)

    marka = db.execute(
        select(Brand).where(Brand.workspace_id == workspace.id).limit(1)
    ).scalar_one_or_none()

    kilavuz = None
    if marka is not None:
        kilavuz = db.execute(
            select(BrandGuideline).where(BrandGuideline.brand_id == marka.id).limit(1)
        ).scalar_one_or_none()

    hesaplar = db.execute(
        select(SocialAccount).where(
            SocialAccount.workspace_id == workspace.id,
            SocialAccount.is_active.is_(True),
        )
    ).scalars().all()

    return {
        "workspace_id": str(workspace.id),
        "ad": workspace.name,
        "saat_dilimi": workspace.timezone,
        "marka": None if marka is None else {
            "ad": marka.name,
            "sektor": marka.sector,
            "aciklama": marka.description,
            "hedef_kitle": kilavuz.target_audience if kilavuz else None,
            "marka_dili": kilavuz.tone_of_voice if kilavuz else None,
            # Yasakli ifadeler n8n'e de verilir: arastirma sonucu ozetlenirken
            # bu ifadelerin kullanilmamasi gerektigini bilsin.
            "yasakli_ifadeler": kilavuz.forbidden_phrases if kilavuz else [],
        },
        "hesaplar": [
            {
                "hesap_id": str(h.id),
                "platform": h.platform.value,
                "kullanici_adi": h.username,
            }
            for h in hesaplar
        ],
        "akislar": akis_durumlari(db, workspace.id),
    }
