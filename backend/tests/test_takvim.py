"""Yayin takvimi.

Korunan kurallar:
- YALNIZCA ONAYLANMIS icerik planlanabilir. Onaysiz bir icerigi takvime
  koymak, onay sistemini etkisiz hale getirirdi
- Sistem kendisi PAYLASMAZ; yayin elle isaretlenir
- Gecmis bir zamana plan yapilamaz
- Yayinlanmis bir plan silinemez (gecmis kaydi kaybolmaz)
- Baska musterinin icerigi planlanamaz
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app.models.brand import Brand
from app.models.content import ContentCalendar, ContentIdea, ContentScript
from app.models.enums import ContentStatus, MediaType, Platform, WorkspaceRole
from app.panel.auth import COOKIE_NAME
from app.services.takvim import (
    TakvimHatasi,
    ay_gorunumu,
    kaldir,
    planla,
    planlanabilir_icerikler,
    yayinlandi_isaretle,
)

SIFRE = "GucluSifre123!"


def _giris(client, kullanici):
    yanit = client.post(
        "/panel/giris", data={"email": kullanici.email, "password": SIFRE},
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    return yanit.cookies.get(COOKIE_NAME)


@pytest.fixture
def icerik(db, make_workspace):
    def _kur(workspace=None, durum=ContentStatus.APPROVED, baslik="Baklava videosu"):
        ws = workspace or make_workspace(name="Takvim Musterisi")
        db.flush()
        marka = Brand(workspace_id=ws.id, name="Taha Usta")
        db.add(marka)
        db.flush()
        fikir = ContentIdea(
            workspace_id=ws.id, brand_id=marka.id, title=baslik,
            status=durum, idea_fingerprint=f"parmak-{baslik}",
        )
        db.add(fikir)
        db.flush()
        senaryo = ContentScript(
            workspace_id=ws.id, idea_id=fikir.id,
            platform=Platform.INSTAGRAM, format=MediaType.REEL,
            hook="İlk üç saniye", status=durum,
        )
        db.add(senaryo)
        db.flush()
        return ws, senaryo

    return _kur


def _ileri(gun=3, saat=12):
    return dt.datetime.now(dt.UTC).replace(
        hour=saat, minute=0, second=0, microsecond=0
    ) + dt.timedelta(days=gun)


# --- Onay kapisi -------------------------------------------------------------

def test_onaysiz_icerik_planlanamiyor(db, icerik):
    """Onaysiz icerigi takvime koymak, onay sistemini etkisiz kilardi."""
    ws, senaryo = icerik(durum=ContentStatus.DRAFT)

    with pytest.raises(TakvimHatasi) as hata:
        planla(
            db, workspace_id=ws.id, script_id=senaryo.id,
            ne_zaman=_ileri(), planlayan_user_id=None,
        )
    assert "ONAYLANMIŞ" in str(hata.value)
    assert db.execute(select(ContentCalendar)).scalars().all() == []


def test_onayli_icerik_planlanabiliyor(db, icerik):
    ws, senaryo = icerik()
    ne_zaman = _ileri()

    kayit = planla(
        db, workspace_id=ws.id, script_id=senaryo.id,
        ne_zaman=ne_zaman, planlayan_user_id=None, notlar="kampanya görseliyle",
    )

    assert kayit.scheduled_for == ne_zaman
    assert kayit.notes == "kampanya görseliyle"
    db.refresh(senaryo)
    assert senaryo.status is ContentStatus.SCHEDULED


def test_gecmise_plan_yapilamiyor(db, icerik):
    ws, senaryo = icerik()
    with pytest.raises(TakvimHatasi) as hata:
        planla(
            db, workspace_id=ws.id, script_id=senaryo.id,
            ne_zaman=dt.datetime.now(dt.UTC) - dt.timedelta(hours=1),
            planlayan_user_id=None,
        )
    assert "Geçmiş" in str(hata.value)


def test_baska_musterinin_icerigi_planlanamiyor(db, icerik, make_workspace):
    _, senaryo = icerik()
    baskasi = make_workspace(name="Baskasi")
    db.flush()

    with pytest.raises(TakvimHatasi):
        planla(
            db, workspace_id=baskasi.id, script_id=senaryo.id,
            ne_zaman=_ileri(), planlayan_user_id=None,
        )


# --- Tasima, kaldirma --------------------------------------------------------

def test_ayni_icerik_tekrar_planlanirsa_tasiniyor(db, icerik):
    """Iki kayit olusursa takvimde ayni icerik iki kez gorunurdu."""
    ws, senaryo = icerik()
    planla(db, workspace_id=ws.id, script_id=senaryo.id,
           ne_zaman=_ileri(3), planlayan_user_id=None)
    yeni_zaman = _ileri(5)
    planla(db, workspace_id=ws.id, script_id=senaryo.id,
           ne_zaman=yeni_zaman, planlayan_user_id=None)

    kayitlar = db.execute(select(ContentCalendar)).scalars().all()
    assert len(kayitlar) == 1
    assert kayitlar[0].scheduled_for == yeni_zaman


def test_plan_kaldirilinca_icerik_onayliya_donuyor(db, icerik):
    ws, senaryo = icerik()
    kayit = planla(db, workspace_id=ws.id, script_id=senaryo.id,
                   ne_zaman=_ileri(), planlayan_user_id=None)

    kaldir(db, workspace_id=ws.id, kayit_id=kayit.id)

    assert db.execute(select(ContentCalendar)).scalars().all() == []
    db.refresh(senaryo)
    assert senaryo.status is ContentStatus.APPROVED


# --- Yayin elle isaretlenir --------------------------------------------------

def test_yayin_elle_isaretleniyor(db, icerik):
    """Sistem paylasmaz; bu yalnizca bir kayittir."""
    ws, senaryo = icerik()
    kayit = planla(db, workspace_id=ws.id, script_id=senaryo.id,
                   ne_zaman=_ileri(), planlayan_user_id=None)

    yayinlandi_isaretle(
        db, workspace_id=ws.id, kayit_id=kayit.id, isaretleyen_user_id=None
    )

    db.refresh(kayit)
    assert kayit.published_at is not None
    assert kayit.status is ContentStatus.PUBLISHED
    db.refresh(senaryo)
    assert senaryo.status is ContentStatus.PUBLISHED


def test_yayinlanmis_plan_silinemiyor(db, icerik):
    """Gecmis kaydi silmek, neyin ne zaman paylasildigini kaybetmektir."""
    ws, senaryo = icerik()
    kayit = planla(db, workspace_id=ws.id, script_id=senaryo.id,
                   ne_zaman=_ileri(), planlayan_user_id=None)
    yayinlandi_isaretle(db, workspace_id=ws.id, kayit_id=kayit.id,
                        isaretleyen_user_id=None)

    with pytest.raises(TakvimHatasi) as hata:
        kaldir(db, workspace_id=ws.id, kayit_id=kayit.id)
    assert "kaldırılamaz" in str(hata.value)


def test_iki_kez_yayinlandi_isaretlenemiyor(db, icerik):
    ws, senaryo = icerik()
    kayit = planla(db, workspace_id=ws.id, script_id=senaryo.id,
                   ne_zaman=_ileri(), planlayan_user_id=None)
    yayinlandi_isaretle(db, workspace_id=ws.id, kayit_id=kayit.id,
                        isaretleyen_user_id=None)

    with pytest.raises(TakvimHatasi):
        yayinlandi_isaretle(db, workspace_id=ws.id, kayit_id=kayit.id,
                            isaretleyen_user_id=None)


# --- Gorunum -----------------------------------------------------------------

def test_planlanabilir_listesi_yalnizca_onaylilari_veriyor(db, icerik):
    ws, onayli = icerik(baslik="Onayli icerik")
    icerik(workspace=ws, durum=ContentStatus.DRAFT, baslik="Taslak icerik")

    liste = planlanabilir_icerikler(db, ws.id)
    basliklar = {i["baslik"] for i in liste}
    assert "Onayli icerik" in basliklar
    assert "Taslak icerik" not in basliklar


def test_planlanan_icerik_listede_kalmıyor(db, icerik):
    ws, senaryo = icerik()
    planla(db, workspace_id=ws.id, script_id=senaryo.id,
           ne_zaman=_ileri(), planlayan_user_id=None)

    assert planlanabilir_icerikler(db, ws.id) == []


def test_ay_gorunumu_gecikmeyi_isaretliyor(db, icerik):
    """Zamani gecmis ama yayinlanmamis plan kullaniciya gorunmeli."""
    ws, senaryo = icerik()
    gelecek = _ileri(2)
    kayit = planla(db, workspace_id=ws.id, script_id=senaryo.id,
                   ne_zaman=gelecek, planlayan_user_id=None)

    # "Simdi"yi ileri alarak gecikmeyi tetikle.
    gorunum = ay_gorunumu(
        db, ws.id, yil=gelecek.year, ay=gelecek.month,
        simdi=gelecek + dt.timedelta(days=1),
    )
    assert gorunum["geciken"] == 1

    yayinlandi_isaretle(db, workspace_id=ws.id, kayit_id=kayit.id,
                        isaretleyen_user_id=None)
    gorunum2 = ay_gorunumu(
        db, ws.id, yil=gelecek.year, ay=gelecek.month,
        simdi=gelecek + dt.timedelta(days=1),
    )
    assert gorunum2["geciken"] == 0


def test_baska_musterinin_plani_gorunmuyor(db, icerik, make_workspace):
    ws, senaryo = icerik()
    ne_zaman = _ileri()
    planla(db, workspace_id=ws.id, script_id=senaryo.id,
           ne_zaman=ne_zaman, planlayan_user_id=None)

    baskasi = make_workspace(name="Baskasi")
    db.flush()
    gorunum = ay_gorunumu(db, baskasi.id, yil=ne_zaman.year, ay=ne_zaman.month)
    assert gorunum["toplam"] == 0


# --- Panel -------------------------------------------------------------------

@pytest.fixture
def ortam(client, db, make_user, make_workspace, add_member, icerik):
    def _kur(rol=WorkspaceRole.OWNER):
        kullanici = make_user(password=SIFRE)
        ws = make_workspace(name="Panel Takvimi")
        add_member(ws, kullanici, rol)
        _, senaryo = icerik(workspace=ws)
        db.commit()
        _giris(client, kullanici)
        return kullanici, ws, senaryo

    return _kur


def test_takvim_sayfasi_aciliyor(client, db, ortam):
    _, ws, _ = ortam()
    yanit = client.get(f"/panel/musteri/{ws.id}/takvim")
    assert yanit.status_code == 200
    assert "Takvim" in yanit.text
    # Sistemin paylasmadigi ACIKCA yazmali.
    assert "Sistem kendisi paylaşmaz" in yanit.text


def test_panelden_planlanabiliyor(client, db, ortam):
    _, ws, senaryo = ortam()
    gun = (dt.date.today() + dt.timedelta(days=4)).isoformat()

    yanit = client.post(
        f"/panel/musteri/{ws.id}/takvim/planla",
        data={"script_id": str(senaryo.id), "tarih": gun, "saat": "14:30",
              "notlar": "reels olarak"},
    )
    assert yanit.status_code == 200

    kayit = db.execute(select(ContentCalendar)).scalar_one()
    assert kayit.scheduled_for.strftime("%H:%M") == "14:30"
    assert kayit.notes == "reels olarak"


def test_izleyici_planlayamiyor(client, db, ortam):
    _, ws, senaryo = ortam(WorkspaceRole.VIEWER)
    gun = (dt.date.today() + dt.timedelta(days=4)).isoformat()

    yanit = client.post(
        f"/panel/musteri/{ws.id}/takvim/planla",
        data={"script_id": str(senaryo.id), "tarih": gun, "saat": "10:00"},
    )
    assert yanit.status_code == 403
    assert db.execute(select(ContentCalendar)).scalars().all() == []


def test_uye_olunmayan_musterinin_takvimi_gorunmuyor(
    client, db, make_user, make_workspace
):
    kullanici = make_user(password=SIFRE)
    baskasi = make_workspace(name="Baskasinin")
    db.commit()
    _giris(client, kullanici)

    yanit = client.get(f"/panel/musteri/{baskasi.id}/takvim")
    assert yanit.status_code == 404


def test_bozuk_tarih_reddediliyor(client, db, ortam):
    _, ws, senaryo = ortam()
    yanit = client.post(
        f"/panel/musteri/{ws.id}/takvim/planla",
        data={"script_id": str(senaryo.id), "tarih": "yarin", "saat": "10:00"},
    )
    assert yanit.status_code == 400
    assert "okunamadı" in yanit.text
