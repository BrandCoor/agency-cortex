"""Gosterge paneli.

Korunan kurallar:
- HER sayi gercek kayittan gelir; uydurma yer tutucu YOKTUR
- Musteri izolasyonu burada da gecerli: sistem yoneticisi olmak
  otomatik erisim VERMEZ
- Kotu haber gizlenmez (geciken plan, basarisiz calisma, hata mesaji)
- Veri yoksa SEBEBI yazilir
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.models.brand import Brand
from app.models.content import ContentCalendar, ContentIdea, ContentScript
from app.models.enums import (
    AutomationStatus,
    AutomationTrigger,
    ContentStatus,
    MediaType,
    Platform,
)
from app.models.otomasyon import AutomationRun
from app.models.social import SocialAccount
from app.panel.auth import COOKIE_NAME
from app.services.dashboard import ozet_getir

SIFRE = "GucluSifre123!"


def _giris(client, kullanici):
    yanit = client.post(
        "/panel/giris", data={"email": kullanici.email, "password": SIFRE},
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    return yanit.cookies.get(COOKIE_NAME)


@pytest.fixture
def ortam(client, db, make_user, make_workspace, add_member):
    def _kur(**kw):
        kullanici = make_user(password=SIFRE, **kw)
        ws = make_workspace(name="Gösterge Müşterisi")
        add_member(ws, kullanici)
        db.commit()
        return kullanici, ws

    return _kur


def _senaryo(db, ws, durum):
    marka = Brand(workspace_id=ws.id, name="Marka")
    db.add(marka)
    db.flush()
    fikir = ContentIdea(
        workspace_id=ws.id, brand_id=marka.id, title="Fikir",
        status=durum, idea_fingerprint=f"p-{durum.value}-{ws.id}",
    )
    db.add(fikir)
    db.flush()
    s = ContentScript(
        workspace_id=ws.id, idea_id=fikir.id, platform=Platform.INSTAGRAM,
        format=MediaType.REEL, hook="Kanca", status=durum,
    )
    db.add(s)
    db.flush()
    return s


# --- Izolasyon ----------------------------------------------------------------

def test_uye_olunmayan_musteri_sayilmiyor(db, ortam, make_workspace):
    kullanici, _ws = ortam()
    make_workspace(name="Baskasinin")
    db.flush()

    assert ozet_getir(db, kullanici).musteri_sayisi == 1


def test_sistem_yoneticisi_otomatik_erisim_almiyor(db, ortam, make_user, make_workspace):
    """Gosterge paneli de musteri izolasyonuna uyar."""
    yonetici = make_user(password=SIFRE)
    yonetici.is_superuser = True
    make_workspace(name="Uye olmadigi musteri")
    db.flush()

    assert ozet_getir(db, yonetici).musteri_sayisi == 0


def test_musterisi_olmayana_ne_yapmasi_gerektigi_yaziyor(db, make_user):
    kisi = make_user()
    db.flush()
    ozet = ozet_getir(db, kisi)
    assert ozet.musteri_sayisi == 0
    assert any("atanmadınız" in n for n in ozet.notlar)


# --- Sayilar ------------------------------------------------------------------

def test_onay_bekleyenler_sayiliyor(db, ortam):
    kullanici, ws = ortam()
    _senaryo(db, ws, ContentStatus.INTERNAL_REVIEW)
    _senaryo(db, ws, ContentStatus.CLIENT_REVIEW)
    _senaryo(db, ws, ContentStatus.APPROVED)
    db.flush()

    assert ozet_getir(db, kullanici).bekleyen_onay == 2


def test_geciken_plan_gizlenmiyor(db, ortam):
    """Gosterge panelinin isi kotu haberi de vermektir."""
    kullanici, ws = ortam()
    s = _senaryo(db, ws, ContentStatus.SCHEDULED)
    db.add(ContentCalendar(
        workspace_id=ws.id, script_id=s.id, status=ContentStatus.SCHEDULED,
        scheduled_for=dt.datetime.now(dt.UTC) - dt.timedelta(days=2),
    ))
    db.flush()

    assert ozet_getir(db, kullanici).gecikmis_plan == 1


def test_yaklasan_plan_sadece_yedi_gun(db, ortam):
    kullanici, ws = ortam()
    yakin = _senaryo(db, ws, ContentStatus.SCHEDULED)
    uzak = _senaryo(db, ws, ContentStatus.APPROVED)
    simdi = dt.datetime.now(dt.UTC)
    db.add(ContentCalendar(
        workspace_id=ws.id, script_id=yakin.id, status=ContentStatus.SCHEDULED,
        scheduled_for=simdi + dt.timedelta(days=2),
    ))
    db.add(ContentCalendar(
        workspace_id=ws.id, script_id=uzak.id, status=ContentStatus.SCHEDULED,
        scheduled_for=simdi + dt.timedelta(days=20),
    ))
    db.flush()

    assert ozet_getir(db, kullanici).yaklasan_plan == 1


def test_basarisiz_calisma_ve_hatasi_gorunuyor(db, ortam):
    kullanici, ws = ortam()
    db.add(AutomationRun(
        workspace_id=ws.id, workflow_key="wf01_gunluk_zeka",
        status=AutomationStatus.FAILED, trigger=AutomationTrigger.SCHEDULE,
        started_at=dt.datetime.now(dt.UTC), error_message="Anahtar gecersiz",
    ))
    db.flush()

    ozet = ozet_getir(db, kullanici)
    assert ozet.basarisiz_calisma == 1
    assert ozet.son_calismalar[0]["hata"] == "Anahtar gecersiz"


def test_bagli_hesap_yoksa_sebebi_yaziyor(db, ortam):
    kullanici, _ws = ortam()
    ozet = ozet_getir(db, kullanici)
    assert ozet.bagli_hesap == 0
    assert any("bağlı sosyal medya hesabı yok" in n for n in ozet.notlar)


def test_bagli_hesap_sayiliyor(db, ortam):
    kullanici, ws = ortam()
    db.add(SocialAccount(
        workspace_id=ws.id, platform=Platform.INSTAGRAM,
        external_id="1", username="marka", is_active=True,
    ))
    db.flush()
    assert ozet_getir(db, kullanici).bagli_hesap == 1


# --- Panel --------------------------------------------------------------------

def test_sayfa_aciliyor(client, db, ortam):
    kullanici, _ws = ortam()
    _giris(client, kullanici)
    yanit = client.get("/panel/dashboard")
    assert yanit.status_code == 200
    assert "Gösterge paneli" in yanit.text


def test_menude_baglantisi_var(client, db, ortam):
    kullanici, _ws = ortam()
    _giris(client, kullanici)
    assert "/panel/dashboard" in client.get("/panel").text


def test_giris_yapmadan_acilmiyor(client):
    yanit = client.get("/panel/dashboard", follow_redirects=False)
    assert yanit.headers["location"] == "/panel/giris"
