"""Kampanyanin platform bazinda dagilimi.

Korunan kurallar:
- Ayni platform iki kez eklenirse GUNCELLENIR, kopya olusmaz
  (aksi halde toplam butce sessizce iki kez sayilirdi)
- Butce iki yazimda da kabul edilir: '1.500,50' ve '1500.50'
- Eksi veya sacma buyuklukte butce reddedilir
- Baska musterinin kampanyasi, kimligi bilinse bile degistirilemez
- Panel bu rakamlarin GERCEK HARCAMA OLMADIGINI acikca yazar
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from app.models.brand import Brand, Campaign
from app.models.enums import PermissionPackage, ReklamPlatformu
from app.services.kampanyalar import (
    KampanyaHatasi,
    butce_coz,
    gun_durumu,
    platform_ekle,
    platform_kaldir,
    platformlari_getir,
    toplam_butce,
)

SIFRE = "GucluSifre123!"


def _giris(client, kullanici):
    yanit = client.post(
        "/panel/giris", data={"email": kullanici.email, "password": SIFRE},
        follow_redirects=False,
    )
    assert yanit.status_code == 303


@pytest.fixture
def kampanya(db, make_workspace):
    def _kur(workspace=None, **kw):
        ws = workspace or make_workspace(name="Kampanya Müşterisi")
        db.flush()
        marka = Brand(workspace_id=ws.id, name="Marka")
        db.add(marka)
        db.flush()
        k = Campaign(
            workspace_id=ws.id, brand_id=marka.id, name="Ramazan 2026", **kw
        )
        db.add(k)
        db.flush()
        return ws, k

    return _kur


# --- Butce cozumleme ----------------------------------------------------------

@pytest.mark.parametrize(
    ("yazilan", "beklenen"),
    [
        ("1500", "1500.00"),
        ("1500.50", "1500.50"),
        ("1.500,50", "1500.50"),
        ("2 000,25", "2000.25"),
        ("₺750", "750.00"),
        ("", "0"),
    ],
)
def test_butce_iki_yazimda_da_kabul_ediliyor(yazilan, beklenen):
    """Tek bir bicim dayatmak 'neden kabul etmedi?' sorusunu dogururdu."""
    assert butce_coz(yazilan) == Decimal(beklenen)


@pytest.mark.parametrize("yazilan", ["-5", "abc", "99999999999999"])
def test_gecersiz_butce_reddediliyor(yazilan):
    with pytest.raises(KampanyaHatasi):
        butce_coz(yazilan)


# --- Platform satirlari -------------------------------------------------------

def test_platform_eklenebiliyor(db, kampanya):
    ws, k = kampanya()
    platform_ekle(
        db, workspace_id=ws.id, campaign_id=k.id,
        platform=ReklamPlatformu.META, butce=Decimal("15000"),
        hedef="500 rezervasyon",
    )
    satirlar = platformlari_getir(db, k.id)
    assert len(satirlar) == 1
    assert satirlar[0].platform == "meta"
    assert "Meta" in satirlar[0].platform_adi


def test_ayni_platform_kopya_olusturmuyor(db, kampanya):
    """Kopya olussaydi toplam butce SESSIZCE iki kez sayilirdi."""
    ws, k = kampanya()
    platform_ekle(db, workspace_id=ws.id, campaign_id=k.id,
                  platform=ReklamPlatformu.META, butce=Decimal("10000"))
    platform_ekle(db, workspace_id=ws.id, campaign_id=k.id,
                  platform=ReklamPlatformu.META, butce=Decimal("12000"))

    satirlar = platformlari_getir(db, k.id)
    assert len(satirlar) == 1
    assert satirlar[0].butce == Decimal("12000.00")
    assert toplam_butce(db, k.id) == Decimal("12000.00")


def test_toplam_butce_platformlari_topluyor(db, kampanya):
    ws, k = kampanya()
    platform_ekle(db, workspace_id=ws.id, campaign_id=k.id,
                  platform=ReklamPlatformu.META, butce=Decimal("10000"))
    platform_ekle(db, workspace_id=ws.id, campaign_id=k.id,
                  platform=ReklamPlatformu.GOOGLE_ADS, butce=Decimal("5500.50"))
    assert toplam_butce(db, k.id) == Decimal("15500.50")


def test_organik_platform_butcesiz_olabiliyor(db, kampanya):
    """Her kampanyanin reklam butcesi olmak zorunda degildir."""
    ws, k = kampanya()
    platform_ekle(db, workspace_id=ws.id, campaign_id=k.id,
                  platform=ReklamPlatformu.ORGANIK, butce=Decimal("0"))
    assert toplam_butce(db, k.id) == Decimal("0")
    assert len(platformlari_getir(db, k.id)) == 1


def test_baska_musterinin_kampanyasina_eklenemiyor(db, kampanya, make_workspace):
    ws, k = kampanya()
    baskasi = make_workspace(name="Başkası")
    db.flush()
    with pytest.raises(KampanyaHatasi):
        platform_ekle(db, workspace_id=baskasi.id, campaign_id=k.id,
                      platform=ReklamPlatformu.META, butce=Decimal("1"))


def test_baska_musterinin_satiri_silinemiyor(db, kampanya, make_workspace):
    ws, k = kampanya()
    satir = platform_ekle(db, workspace_id=ws.id, campaign_id=k.id,
                          platform=ReklamPlatformu.META, butce=Decimal("1"))
    baskasi = make_workspace(name="Başkası")
    db.flush()
    with pytest.raises(KampanyaHatasi):
        platform_kaldir(db, workspace_id=baskasi.id, satir_id=satir.id)


# --- Asama --------------------------------------------------------------------

def test_tarih_yoksa_tahmin_edilmiyor():
    assert gun_durumu(dt.date(2026, 6, 1), None, None) == "tarih girilmedi"


@pytest.mark.parametrize(
    ("bugun", "bas", "bit", "beklenen"),
    [
        (dt.date(2026, 6, 1), dt.date(2026, 7, 1), dt.date(2026, 7, 30), "başlamadı"),
        (dt.date(2026, 7, 15), dt.date(2026, 7, 1), dt.date(2026, 7, 30), "devam ediyor"),
        (dt.date(2026, 8, 1), dt.date(2026, 7, 1), dt.date(2026, 7, 30), "bitti"),
    ],
)
def test_asama_dogru_hesaplaniyor(bugun, bas, bit, beklenen):
    assert gun_durumu(bugun, bas, bit) == beklenen


# --- Panel --------------------------------------------------------------------

@pytest.fixture
def panel(client, db, make_user, make_workspace, add_member, kampanya):
    def _kur(paket=PermissionPackage.ADMIN):
        kullanici = make_user(password=SIFRE)
        kullanici.permission_package = paket
        ws = make_workspace(name="Panel Müşterisi")
        add_member(ws, kullanici)
        _ws, k = kampanya(workspace=ws)
        db.commit()
        _giris(client, kullanici)
        return kullanici, ws, k

    return _kur


def test_panelde_gercek_harcama_olmadigi_yaziyor(client, panel):
    """Kullanici bu rakamlari Meta'dan geliyor sanmamali."""
    _, ws, _k = panel()
    sayfa = client.get(f"/panel/musteri/{ws.id}/kampanya")
    assert sayfa.status_code == 200
    assert "gerçek harcama" in sayfa.text


def test_panelden_platform_eklenebiliyor(client, db, panel):
    _, ws, k = panel()
    yanit = client.post(
        f"/panel/musteri/{ws.id}/kampanya/platform",
        data={
            "kampanya_id": str(k.id), "platform": "google_ads",
            "butce": "12.500,75", "hedef": "800 tıklama",
        },
    )
    assert yanit.status_code == 200
    satirlar = platformlari_getir(db, k.id)
    assert satirlar[0].butce == Decimal("12500.75")


def test_panelden_platform_kaldirilabiliyor(client, db, panel):
    _, ws, k = panel()
    satir = platform_ekle(db, workspace_id=ws.id, campaign_id=k.id,
                          platform=ReklamPlatformu.META, butce=Decimal("1"))
    db.commit()
    yanit = client.post(
        f"/panel/musteri/{ws.id}/kampanya/platform/sil",
        data={"satir_id": str(satir.id)},
    )
    assert yanit.status_code == 200
    assert platformlari_getir(db, k.id) == []


def test_yetkisiz_kisi_platform_ekleyemiyor(client, db, panel):
    _, ws, k = panel(PermissionPackage.VIEWER)
    yanit = client.post(
        f"/panel/musteri/{ws.id}/kampanya/platform",
        data={"kampanya_id": str(k.id), "platform": "meta", "butce": "1"},
    )
    assert yanit.status_code == 403
    assert platformlari_getir(db, k.id) == []


def test_bozuk_butce_panelde_reddediliyor(client, db, panel):
    _, ws, k = panel()
    yanit = client.post(
        f"/panel/musteri/{ws.id}/kampanya/platform",
        data={"kampanya_id": str(k.id), "platform": "meta", "butce": "abc"},
    )
    assert yanit.status_code == 400
    assert "Bütçe anlaşılamadı" in yanit.text
