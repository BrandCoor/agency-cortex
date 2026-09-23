"""Is akislarinin tanimi ve calistirma kayitlari.

ROL DAGILIMI (DECISIONS.md K-032):
- n8n: zamanlama, sira, tekrar deneme, dis servis cagrilari
- Agency Cortex: kim, hangi musteride, ne yapabilir; butce; onay

Bu dosya ikisinin bulustugu yerdir. Is akislarinin LISTESI burada durur;
n8n'de hangi akisin var oldugu panelden gorulsun diye.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models.enums import AutomationStatus, AutomationTrigger
from app.models.otomasyon import AutomationRun, AutomationSetting

log = get_logger("otomasyon")

#: Bir calistirma bu sureden uzun "calisiyor" kalamaz. Kalmissa surec
#: kapanmadan olmustur (konteyner yeniden basladi, aglantı koptu).
#: Boyle bir kayit sonsuza kadar "calisiyor" gorunmemelidir.
CALISMA_ZAMAN_ASIMI_SAATI = 2


@dataclass(frozen=True)
class IsAkisi:
    anahtar: str
    ad: str
    aciklama: str
    #: Insan diliyle zamanlama. Gercek zamanlama n8n'dedir; burasi
    #: yalnizca panelde ne bekleneceğini yazar.
    zamanlama: str


IS_AKISLARI: tuple[IsAkisi, ...] = (
    IsAkisi(
        anahtar="wf01_gunluk_zeka",
        ad="Günlük sosyal zekâ",
        aciklama=(
            "Bağlı hesapların önceki güne ait metriklerini toplar, "
            "olağandışı değişimleri işaretler ve panele yazar."
        ),
        zamanlama="Her gün 07:00",
    ),
    IsAkisi(
        anahtar="wf02_trend",
        ad="Trend araştırması",
        aciklama=(
            "Markanın sektöründe öne çıkan konuları ve rakip hareketlerini "
            "araştırır, bulguları panele yazar."
        ),
        zamanlama="Her gün 09:00",
    ),
    IsAkisi(
        anahtar="wf03_icerik",
        ad="İçerik zekâsı",
        aciklama=(
            "Toplanan veriden içerik fikri önerir. Öneriler TASLAKTIR; "
            "insan onayı olmadan hiçbir yere gönderilmez."
        ),
        zamanlama="Haftada 3 gün 10:00",
    ),
    IsAkisi(
        anahtar="wf04_haftalik_rapor",
        ad="Haftalık zekâ raporu",
        aciklama=(
            "Haftanın metriklerini, trendlerini ve içerik performansını "
            "tek rapora toplar. Rapor onaya düşer."
        ),
        zamanlama="Her pazartesi 08:00",
    ),
    IsAkisi(
        anahtar="wf05_baglanti_sagligi",
        ad="Bağlantı sağlığı",
        aciklama=(
            "Bağlı hesapların erişim anahtarlarını süresi dolmadan yeniler "
            "ve yenilenemeyenleri işaretler. Bu akış olmadan hesaplar "
            "yaklaşık 60 gün sonra sessizce çalışmaz hale gelir."
        ),
        zamanlama="Her gün 06:00",
    ),
    IsAkisi(
        anahtar="wf06_rakip",
        ad="Rakip araştırması",
        aciklama=(
            "İzlenen RAKİP hesapların son dönemdeki hareketlerini araştırır "
            "ve markayı ilgilendiren yanlarını yazar. Yalnızca kamuya açık "
            "bilgi kullanılır; rakibin özel içgörü verisi sisteme girmez."
        ),
        zamanlama="Haftada 2 gün 11:00",
    ),
)

IS_AKISI_ANAHTARLARI = frozenset(a.anahtar for a in IS_AKISLARI)
IS_AKISI_SOZLUGU = {a.anahtar: a for a in IS_AKISLARI}


class OtomasyonHatasi(Exception):
    """Otomasyon isleminde kurala takilan durum."""


def akis_dogrula(anahtar: str) -> IsAkisi:
    akis = IS_AKISI_SOZLUGU.get(anahtar)
    if akis is None:
        raise OtomasyonHatasi(f"Tanımsız iş akışı: {anahtar}")
    return akis


# --- Ayarlar ----------------------------------------------------------------

def ayar_oku(db: Session, workspace_id: uuid.UUID, workflow_key: str) -> AutomationSetting | None:
    return db.execute(
        select(AutomationSetting).where(
            AutomationSetting.workspace_id == workspace_id,
            AutomationSetting.workflow_key == workflow_key,
        )
    ).scalar_one_or_none()


def acik_mi(db: Session, workspace_id: uuid.UUID, workflow_key: str) -> bool:
    """Bu musteride bu akis acik mi? Varsayilan KAPALI."""
    ayar = ayar_oku(db, workspace_id, workflow_key)
    return bool(ayar and ayar.is_enabled)


def ayar_yaz(
    db: Session, workspace_id: uuid.UUID, workflow_key: str, *, acik: bool
) -> AutomationSetting:
    akis_dogrula(workflow_key)
    ayar = ayar_oku(db, workspace_id, workflow_key)
    if ayar is None:
        ayar = AutomationSetting(
            workspace_id=workspace_id, workflow_key=workflow_key, is_enabled=acik
        )
        db.add(ayar)
    else:
        ayar.is_enabled = acik
    db.flush()
    return ayar


# --- Calistirmalar ----------------------------------------------------------

def takilan_calistirmalari_kapat(db: Session, *, now: datetime | None = None) -> int:
    """Kapanmadan kalmis calistirmalari "hata" olarak isaretler.

    Bir surec cokerse kaydi kimse kapatmaz. Boyle bir kayit panelde
    sonsuza kadar "calisiyor" gorunur ve yeni calistirma da baslatamaz.
    Gercekte olan sey gizlenmez: hata olarak, nedeniyle kapatilir.
    """
    simdi = now or datetime.now(UTC)
    sinir = simdi - timedelta(hours=CALISMA_ZAMAN_ASIMI_SAATI)

    takilanlar = db.execute(
        select(AutomationRun).where(
            AutomationRun.status == AutomationStatus.RUNNING,
            AutomationRun.started_at < sinir,
        )
    ).scalars().all()

    for kayit in takilanlar:
        kayit.status = AutomationStatus.FAILED
        kayit.finished_at = simdi
        kayit.error_message = (
            f"Zaman asimi: calistirma {CALISMA_ZAMAN_ASIMI_SAATI} saatten uzun "
            "surdu ve kapanmadi. Surec beklenmedik sekilde sonlanmis olabilir."
        )
        log.warning(
            "otomasyon_takildi",
            workspace_id=str(kayit.workspace_id),
            workflow_key=kayit.workflow_key,
            run_id=str(kayit.id),
        )

    if takilanlar:
        db.flush()
    return len(takilanlar)


def calistirma_baslat(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    workflow_key: str,
    trigger: AutomationTrigger,
    api_client_id: uuid.UUID | None = None,
    external_execution_id: str | None = None,
) -> AutomationRun:
    """Yeni bir calistirma kaydi acar (durum: calisiyor)."""
    akis_dogrula(workflow_key)
    takilan_calistirmalari_kapat(db)
    if not acik_mi(db, workspace_id, workflow_key):
        raise OtomasyonHatasi(
            "Bu iş akışı bu müşteri için kapalı. Panelden açılmadan çalıştırılamaz."
        )

    kayit = AutomationRun(
        workspace_id=workspace_id,
        workflow_key=workflow_key,
        status=AutomationStatus.RUNNING,
        trigger=trigger,
        api_client_id=api_client_id,
        external_execution_id=external_execution_id,
        started_at=datetime.now(UTC),
        summary={},
    )
    db.add(kayit)
    db.flush()
    return kayit


def calistirma_bitir(
    db: Session,
    kayit: AutomationRun,
    *,
    basarili: bool,
    ozet: dict | None = None,
    hata_mesaji: str | None = None,
) -> AutomationRun:
    """Calistirmayi kapatir.

    Basarisizlik GIZLENMEZ: hata mesaji kaydedilir ve panelde gorunur.
    """
    if kayit.status is not AutomationStatus.RUNNING:
        raise OtomasyonHatasi("Bu çalıştırma zaten kapanmış.")

    kayit.status = AutomationStatus.SUCCEEDED if basarili else AutomationStatus.FAILED
    kayit.finished_at = datetime.now(UTC)
    kayit.summary = ozet or {}
    # Hata metni sinirlanir: bir yigin izi (stack trace) tablonun icine
    # sigmaz ve okunmaz.
    kayit.error_message = (hata_mesaji or None) if not basarili else None
    if kayit.error_message:
        kayit.error_message = kayit.error_message[:2000]
    db.flush()
    return kayit


def son_calistirmalar(
    db: Session, workspace_id: uuid.UUID, *, limit: int = 20
) -> list[AutomationRun]:
    return list(
        db.execute(
            select(AutomationRun)
            .where(AutomationRun.workspace_id == workspace_id)
            .order_by(AutomationRun.started_at.desc())
            .limit(limit)
        ).scalars().all()
    )


def akis_durumlari(db: Session, workspace_id: uuid.UUID) -> list[dict]:
    """Panel icin: her akisin acik mi oldugu ve en son ne zaman calistigi."""
    sonuc = []
    for akis in IS_AKISLARI:
        son = db.execute(
            select(AutomationRun)
            .where(
                AutomationRun.workspace_id == workspace_id,
                AutomationRun.workflow_key == akis.anahtar,
            )
            .order_by(AutomationRun.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        takildi = bool(
            son
            and son.status is AutomationStatus.RUNNING
            and son.started_at
            < datetime.now(UTC) - timedelta(hours=CALISMA_ZAMAN_ASIMI_SAATI)
        )

        sonuc.append({
            "anahtar": akis.anahtar,
            "ad": akis.ad,
            "aciklama": akis.aciklama,
            "zamanlama": akis.zamanlama,
            "acik": acik_mi(db, workspace_id, akis.anahtar),
            "son_durum": ("failed" if takildi else son.status.value) if son else None,
            "takildi": takildi,
            "son_baslangic": son.started_at if son else None,
            "son_bitis": son.finished_at if son else None,
            "son_hata": son.error_message if son else None,
            "son_ozet": son.summary if son else {},
        })
    return sonuc
