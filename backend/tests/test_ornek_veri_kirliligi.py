"""Ornek veri, musteri verisine bulgu olarak yazilmamali.

OLAY: Kullanici rakip analizi sayfasinda BES KEZ ayni satiri gordu:
    "@gokaymedia — Ornek veri saglayicisi uretti — gercek gozlem DEGIL."
Hicbiri analiz degildi ve silinemiyorlardi.

UC AYRI HATA VARDI:
1. Ornek veri saglayicisinin ciktisi VERITABANINA YAZILIYORDU. Metnin
   uzerinde "ornek veridir" yazmasi yetmez; kayit listede kalir, birikir.
2. Rakip akisinda TEKRAR KONTROLU YOKTU. Trend akisinda vardi, burada
   unutulmustu; her calismada ayni metin yeniden ekleniyordu.
3. Yazilmis kayitlari SILMENIN YOLU YOKTU.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.brand import Brand
from app.models.enums import Platform
from app.models.izlenen import IzlemeTuru, TrackedAccount
from app.models.research import CompetitorObservation, TrendObservation
from app.services.is_akislari import wf06_rakip_arastirmasi
from app.services.ornek_veri_temizligi import say, temizle

ORNEK_METIN = "Örnek veri sağlayıcısı üretti — gerçek gözlem DEĞİL."
GERCEK_METIN = "Rakip son 14 günde üç kısa video paylaştı."


@pytest.fixture
def musteri(db, make_workspace):
    ws = make_workspace(name="Kirlilik Musterisi")
    db.flush()
    db.add(Brand(workspace_id=ws.id, name="Taha Usta"))
    hesap = TrackedAccount(
        workspace_id=ws.id, platform=Platform.INSTAGRAM,
        username="gokaymedia", tur=IzlemeTuru.RAKIP,
    )
    db.add(hesap)
    db.flush()
    return ws, hesap


def _bulgular(db, ws):
    return list(db.execute(
        select(CompetitorObservation).where(
            CompetitorObservation.workspace_id == ws.id
        )
    ).scalars())


# --- 1. Tekrar kontrolu -------------------------------------------------------

def test_ayni_bulgu_tekrar_tekrar_yazilmiyor(db, musteri):
    """Akis bes kez calissa bile ayni metin bir kez yazilmali."""
    ws, _ = musteri
    for _ in range(5):
        wf06_rakip_arastirmasi(db, ws)

    ozetler = [b.summary for b in _bulgular(db, ws)]
    assert len(ozetler) == len(set(ozetler)), (
        f"Ayni metin birden fazla kez yazilmis: {ozetler}"
    )


def test_tekrar_edilen_bulgu_sayisi_bildiriliyor(db, musteri):
    """Sessizce atlamak, kullanicinin 'akis calismadi' sanmasina yol acardi."""
    ws, _ = musteri
    wf06_rakip_arastirmasi(db, ws)
    ikinci = wf06_rakip_arastirmasi(db, ws)
    assert any("tekrar kaydedilmedi" in n for n in ikinci.notlar)


# --- 2. Uretimde hic yazilmamali ---------------------------------------------

def test_uretimde_ornek_veri_uretilemiyor_ve_kaydedilmiyor(db, musteri, monkeypatch):
    """Uretimde ornek veri saglayicisi HIC calismaz.

    Akis sessizce bos donmez, ACIK hata verir: kullanici "neden bulgu
    yok?" diye sormaz, ne yapmasi gerektigini okur. Hicbir kayit yazilmaz.
    """
    from app.core.config import get_settings
    from app.services.is_akislari import IsAkisiHatasi

    ws, _ = musteri
    ayarlar = get_settings()
    monkeypatch.setattr(type(ayarlar), "is_production", property(lambda self: True))

    with pytest.raises(IsAkisiHatasi) as hata:
        wf06_rakip_arastirmasi(db, ws)

    assert "örnek veri modu" in str(hata.value)
    assert _bulgular(db, ws) == []


def test_ikinci_savunma_hatti_da_yaziyi_engelliyor(db, musteri, monkeypatch):
    """Birinci hat (saglayici secimi) ileride acilirsa ikinci hat tutmali.

    Burada saglayici cagrisi BASARILI donuyormus gibi davraniliyor;
    kaydin yine de yazilmamasi gerekir.
    """
    from app.core.config import get_settings
    from app.services import is_akislari

    ws, _ = musteri
    ayarlar = get_settings()
    monkeypatch.setattr(type(ayarlar), "is_production", property(lambda self: True))
    # Birinci hat devre disi: ornek veri saglayicisi uretime sizmis gibi.
    monkeypatch.setattr(is_akislari, "run_ai_task", _ornek_cikti_uret)

    sonuc = is_akislari.wf06_rakip_arastirmasi(db, ws)

    assert _bulgular(db, ws) == []
    assert sonuc.yapilacak_is_yoktu is True
    # Kullaniciya NE YAPMASI gerektigi soyleniyor.
    assert any("Yapay zekâ sayfasından" in n for n in sonuc.notlar)


class _SahteSonuc:
    """run_ai_task'in dondurdugu seyin ornek veri saglayicisindan gelmis hali."""

    provider = "fake"
    task_id = None
    parsed = {"findings": [], "research_note": ""}
    total_cost_usd = 0


def _ornek_cikti_uret(*_args, **_kwargs):
    return _SahteSonuc()


# --- 3. Temizlik --------------------------------------------------------------

def _ornek_kayit(ws, hesap, metin=ORNEK_METIN):
    return CompetitorObservation(
        workspace_id=ws.id, tracked_account_id=hesap.id,
        observed_at=datetime.now(UTC), source_type="research",
        source_urls=[], summary=metin, data={}, confidence="low",
        uncertainties=[],
    )


def test_ornek_kayitlar_sayiliyor(db, musteri):
    ws, hesap = musteri
    for _ in range(3):
        db.add(_ornek_kayit(ws, hesap))
    db.add(_ornek_kayit(ws, hesap, GERCEK_METIN))
    db.flush()

    assert say(db, ws.id)["rakip"] == 3


def test_eski_ascii_metinler_de_taniniyor(db, musteri):
    """Sunucuda eski (Turkce karaktersiz) kayitlar da olabilir."""
    ws, hesap = musteri
    db.add(_ornek_kayit(ws, hesap, "Sahte saglayici tarafindan uretildi - gercek DEGIL."))
    db.flush()
    assert say(db, ws.id)["rakip"] == 1


def test_temizlik_yalnizca_ornek_kayitlari_siliyor(db, musteri):
    ws, hesap = musteri
    for _ in range(4):
        db.add(_ornek_kayit(ws, hesap))
    db.add(_ornek_kayit(ws, hesap, GERCEK_METIN))
    db.add(TrendObservation(
        workspace_id=ws.id, observed_at=datetime.now(UTC), platform=None,
        topic="Gercek trend", summary=GERCEK_METIN, relevance_to_brand="x",
        source_urls=[], confidence="high", uncertainties=[],
    ))
    db.add(TrendObservation(
        workspace_id=ws.id, observed_at=datetime.now(UTC), platform=None,
        topic="Ornek trend", summary=ORNEK_METIN, relevance_to_brand="x",
        source_urls=[], confidence="low", uncertainties=[],
    ))
    db.flush()

    silinen = temizle(db, ws.id)
    assert silinen == {"rakip": 4, "trend": 1}

    kalan = [b.summary for b in _bulgular(db, ws)]
    assert kalan == [GERCEK_METIN]
    kalan_trend = list(db.execute(
        select(TrendObservation).where(TrendObservation.workspace_id == ws.id)
    ).scalars())
    assert [t.topic for t in kalan_trend] == ["Gercek trend"]


def test_baska_musterinin_kayitlari_silinmiyor(db, musteri, make_workspace):
    """Musteri izolasyonu silme isleminde de gecerli."""
    ws, hesap = musteri
    baskasi = make_workspace(name="Baskasi")
    db.flush()
    baska_hesap = TrackedAccount(
        workspace_id=baskasi.id, platform=Platform.INSTAGRAM,
        username="baskarakip", tur=IzlemeTuru.RAKIP,
    )
    db.add(baska_hesap)
    db.flush()
    db.add(_ornek_kayit(ws, hesap))
    db.add(_ornek_kayit(baskasi, baska_hesap))
    db.flush()

    temizle(db, ws.id)

    kalan = db.execute(
        select(CompetitorObservation).where(
            CompetitorObservation.workspace_id == baskasi.id
        )
    ).scalars().all()
    assert len(kalan) == 1


def test_temizlenecek_bir_sey_yoksa_hata_yok(db, musteri):
    ws, _ = musteri
    assert temizle(db, ws.id) == {"rakip": 0, "trend": 0}
