"""AI butcesinin ATOMIK oldugunun kaniti.

Korunan kural: ayni anda calisan iki is aylik butceyi ASAMAZ.

Bu dosyadaki esszamanlilik testi, diger testlerden farkli olarak GERCEK
ve AYRI veritabani baglantilari acar. Tek baglanti uzerinde yapilan bir
test, kilidin isleyip islemedigini kanitlayamazdi.
"""

from __future__ import annotations

import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.models.ai import AICostEvent
from app.models.enums import AIProviderName
from app.models.identity import Workspace
from app.services import ai_butce
from app.services.ai_butce import (
    BudgetExceeded,
    kesinlestir,
    month_spend,
    rezerve_et,
    serbest_birak,
)

# --- Rezervasyonun butceye yansimasi -----------------------------------------

def test_rezervasyon_butceye_hemen_yansir(db, make_workspace):
    """Cagri daha bitmeden butce dusmeli; yoksa ikinci is bos butce gorur."""
    ws = make_workspace(name="Rezervasyon")
    ws.ai_monthly_budget_usd = 10.0
    db.flush()

    assert month_spend(db, ws.id) == Decimal("0")

    rezerve_et(
        workspace_id=ws.id,
        provider=AIProviderName.CLAUDE,
        tutar=Decimal("3.00"),
        aciklama="test",
    )

    assert month_spend(db, ws.id) == Decimal("3.000000")


def test_kesinlestirme_gercek_tutari_yazar(db, make_workspace):
    ws = make_workspace(name="Kesinlestirme")
    ws.ai_monthly_budget_usd = 10.0
    db.flush()

    rez = rezerve_et(
        workspace_id=ws.id,
        provider=AIProviderName.CLAUDE,
        tutar=Decimal("3.00"),
        aciklama="test isi",
    )
    kesinlestir(rez, gercek_tutar=Decimal("0.42"), aciklama="test isi")

    kayit = db.get(AICostEvent, rez)
    db.refresh(kayit)
    assert kayit.reserved_until is None
    assert Decimal(str(kayit.amount_usd)) == Decimal("0.420000")
    assert month_spend(db, ws.id) == Decimal("0.420000")


def test_maliyet_bildirilmezse_tahmin_butcede_kalir(db, make_workspace):
    """Bilinmeyen maliyeti sifir saymak butce sinirini sessizce bozardi."""
    ws = make_workspace(name="Maliyet Bildirilmedi")
    ws.ai_monthly_budget_usd = 10.0
    db.flush()

    rez = rezerve_et(
        workspace_id=ws.id,
        provider=AIProviderName.CLAUDE,
        tutar=Decimal("3.00"),
        aciklama="test isi",
    )
    kesinlestir(rez, gercek_tutar=None, aciklama="test isi")

    kayit = db.get(AICostEvent, rez)
    db.refresh(kayit)
    assert kayit.reserved_until is None
    assert month_spend(db, ws.id) == Decimal("3.000000")


def test_serbest_birakma_butceyi_geri_verir(db, make_workspace):
    ws = make_workspace(name="Serbest")
    ws.ai_monthly_budget_usd = 10.0
    db.flush()

    rez = rezerve_et(
        workspace_id=ws.id,
        provider=AIProviderName.CLAUDE,
        tutar=Decimal("3.00"),
        aciklama="test",
    )
    serbest_birak(rez)

    assert month_spend(db, ws.id) == Decimal("0")


def test_suresi_gecen_rezervasyon_butceyi_kilitlemez(db, make_workspace):
    """Sureci cokerse acik rezervasyon sonsuza kadar butceyi tutmamali."""
    ws = make_workspace(name="Suresi Gecmis")
    ws.ai_monthly_budget_usd = 10.0
    simdi = datetime.now(UTC)
    db.add(AICostEvent(
        workspace_id=ws.id, provider=AIProviderName.CLAUDE, occurred_at=simdi,
        amount_usd=Decimal("9.00"), description="cokmus surec (rezerve)",
        reserved_until=simdi - timedelta(minutes=1),
    ))
    db.flush()

    assert month_spend(db, ws.id) == Decimal("0")


def test_bedava_veya_olculemeyen_cagri_rezervasyon_yapmaz(db, make_workspace):
    """Manus kredi ile calisir; USD tahmini yoktur, USD butcesini etkilemez."""
    ws = make_workspace(name="Olculemeyen")
    db.flush()

    assert rezerve_et(
        workspace_id=ws.id, provider=AIProviderName.MANUS,
        tutar=None, aciklama="manus arastirma",
    ) is None
    assert rezerve_et(
        workspace_id=ws.id, provider=AIProviderName.FAKE,
        tutar=Decimal("0"), aciklama="sahte",
    ) is None


def test_tahmin_siniri_asiyorsa_cagri_baslamaz(db, make_workspace):
    ws = make_workspace(name="Tahmin Asiyor")
    ws.ai_monthly_budget_usd = 10.0
    db.add(AICostEvent(
        workspace_id=ws.id, provider=AIProviderName.CLAUDE,
        occurred_at=datetime.now(UTC), amount_usd=Decimal("9.50"),
        description="onceki",
    ))
    db.flush()

    with pytest.raises(BudgetExceeded) as hata:
        rezerve_et(
            workspace_id=ws.id, provider=AIProviderName.CLAUDE,
            tutar=Decimal("1.00"), aciklama="yeni is",
        )
    assert hata.value.reserved == Decimal("1.00")


# --- ESSZAMANLILIK KANITI ----------------------------------------------------

def _temizle(workspace_id: uuid.UUID) -> None:
    with SessionLocal() as oturum:
        oturum.execute(delete(AICostEvent).where(AICostEvent.workspace_id == workspace_id))
        oturum.execute(delete(Workspace).where(Workspace.id == workspace_id))
        oturum.commit()


def test_ayni_anda_calisan_iki_is_butceyi_asamaz(monkeypatch):
    """GERCEK esszamanlilik testi: iki ayri baglanti, ayni anda.

    Butce 10 USD; her is 6 USD tahmin ediyor. Ikisi de gecerse 12 USD olur.
    Yalnizca biri gecmeli.

    Bu test `db` fixture'ini KULLANMAZ: o fixture tek bir baglanti uzerinde
    calisir ve kilidi sinayamaz. Veri gercekten islenir, sonunda silinir.

    YARIS PENCERESI GENISLETILIR: toplam okuma ile rezervasyon yazma arasina
    bilerek gecikme konur. Bu olmadan iki is parcacigi pratikte hic ust uste
    binmez ve test, kilit KALDIRILSA BILE gecerdi - yani hicbir sey
    kanitlamazdi. Gecikmeyle birlikte, kilit kaldirildiginda test duser.
    """
    gercek_month_spend = ai_butce.month_spend

    def gecikmeli_month_spend(*args, **kwargs):
        sonuc = gercek_month_spend(*args, **kwargs)
        time.sleep(0.4)
        return sonuc

    monkeypatch.setattr(ai_butce, "month_spend", gecikmeli_month_spend)
    with SessionLocal() as kurulum:
        ws = Workspace(
            name="Esszamanli", slug=f"esszamanli-{uuid.uuid4().hex[:8]}",
            ai_monthly_budget_usd=10.0,
        )
        kurulum.add(ws)
        kurulum.commit()
        workspace_id = ws.id

    try:
        kapi = threading.Barrier(2)
        sonuclar: list[object] = []
        kilit = threading.Lock()

        def calis() -> None:
            kapi.wait(timeout=10)
            try:
                sonuc: object = rezerve_et(
                    workspace_id=workspace_id,
                    provider=AIProviderName.CLAUDE,
                    tutar=Decimal("6.00"),
                    aciklama="esszamanli is",
                )
            except BudgetExceeded as exc:
                sonuc = exc
            with kilit:
                sonuclar.append(sonuc)

        is_parcaciklari = [threading.Thread(target=calis) for _ in range(2)]
        for t in is_parcaciklari:
            t.start()
        for t in is_parcaciklari:
            t.join(timeout=30)
            assert not t.is_alive(), "Kilit acilmadi; islem takildi."

        assert len(sonuclar) == 2
        gecenler = [s for s in sonuclar if isinstance(s, uuid.UUID)]
        engellenenler = [s for s in sonuclar if isinstance(s, BudgetExceeded)]

        assert len(gecenler) == 1, f"Iki is de gecti; butce asildi: {sonuclar}"
        assert len(engellenenler) == 1

        with SessionLocal() as kontrol:
            toplam = month_spend(kontrol, workspace_id)
        assert toplam == Decimal("6.000000")

        # Kayit sayisi da bir olmali; ikinci is hicbir sey yazmamali.
        with SessionLocal() as kontrol:
            kayitlar = kontrol.execute(
                select(AICostEvent).where(AICostEvent.workspace_id == workspace_id)
            ).scalars().all()
        assert len(kayitlar) == 1
    finally:
        _temizle(workspace_id)
