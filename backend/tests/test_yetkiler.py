"""Ayrintili yetki sistemi. Izinler KULLANICIYA aittir.

Korunan kurallar:
- Izinler kullanicinindir; musteriyle ilgisi yoktur
- SISTEM YONETICISI kisitlanamaz; aksi halde sistem yonetilemez olurdu
- Paket varsayilanindan farksiz satir saklanmaz
- Tanimsiz izin asla verilmez
- Panelde acilip kapatilan her izin SUNUCUDA gercekten uygulanir
"""

from __future__ import annotations

import datetime as dt
import pathlib
import uuid

import pytest
from sqlalchemy import select

from app.models.enums import ContentStatus, PermissionPackage, ReportPeriod
from app.models.reporting import Report
from app.models.yetki import UserPermission
from app.panel.auth import COOKIE_NAME
from app.services.yetkiler import (
    IZIN_ANAHTARLARI,
    PAKET_VARSAYILANI,
    YetkiHatasi,
    izin_var_mi,
    izinleri_yaz,
    kullanici_izinleri,
    paketi_degistir,
    varsayilana_don,
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
def ortam(client, db, make_user, make_workspace, add_member):
    """Giris yapmis bir kullanici + uyesi oldugu musteri."""
    def _kur(paket=PermissionPackage.ADMIN, superuser=False):
        kullanici = make_user(password=SIFRE)
        kullanici.is_superuser = superuser
        kullanici.permission_package = paket
        ws = make_workspace(name="Yetki Musterisi")
        add_member(ws, kullanici)
        db.commit()
        _giris(client, kullanici)
        return kullanici, ws

    return _kur


@pytest.fixture
def iki_kisi(client, db, make_user, make_workspace, add_member):
    """Sistem yoneticisi (ayari yapan) + kisitlanacak kisi."""
    def _kur(paket=PermissionPackage.VIEWER):
        yonetici = make_user(password=SIFRE)
        yonetici.is_superuser = True
        kisi = make_user(password=SIFRE)
        kisi.permission_package = paket
        ws = make_workspace(name="Uygulama Kontrolu")
        add_member(ws, yonetici)
        add_member(ws, kisi)
        db.commit()
        return yonetici, kisi, ws

    return _kur


@pytest.fixture
def rapor_olustur(db):
    def _kur(ws, durum=ContentStatus.INTERNAL_REVIEW):
        rapor = Report(
            workspace_id=ws.id, period=ReportPeriod.WEEKLY,
            period_start=dt.date(2026, 9, 14), period_end=dt.date(2026, 9, 20),
            title="Haftalık rapor", status=durum,
        )
        db.add(rapor)
        db.flush()
        return rapor

    return _kur


# --- Varsayilanlar -----------------------------------------------------------

def test_ozellestirme_yoksa_paket_varsayilani_geciyor(db, make_user):
    kisi = make_user()
    kisi.permission_package = PermissionPackage.VIEWER
    db.flush()
    assert kullanici_izinleri(db, kisi) == PAKET_VARSAYILANI[PermissionPackage.VIEWER]


def test_sistem_yoneticisi_her_seyi_yapabiliyor(db, make_user):
    kisi = make_user()
    kisi.is_superuser = True
    kisi.permission_package = PermissionPackage.VIEWER
    db.flush()
    # Paketi en dar olsa bile her sey acik.
    assert kullanici_izinleri(db, kisi) == IZIN_ANAHTARLARI


def test_sistem_yoneticisinin_izni_kisitlanamiyor(db, make_user):
    kisi = make_user()
    kisi.is_superuser = True
    db.flush()
    with pytest.raises(YetkiHatasi):
        izinleri_yaz(db, kisi, set())
    assert kullanici_izinleri(db, kisi) == IZIN_ANAHTARLARI


def test_tanimsiz_izin_verilmiyor(db, make_user):
    kisi = make_user()
    db.flush()
    with pytest.raises(YetkiHatasi):
        izin_var_mi(db, kisi, "olmayan.izin")


# --- Yazma / sifirlama -------------------------------------------------------

def test_izin_eklenebiliyor_ve_kaldirilabiliyor(db, make_user):
    kisi = make_user()
    kisi.permission_package = PermissionPackage.VIEWER
    db.flush()

    izinleri_yaz(db, kisi, set(PAKET_VARSAYILANI[PermissionPackage.VIEWER]) | {"icerik.duzenle"})
    assert izin_var_mi(db, kisi, "icerik.duzenle") is True

    izinleri_yaz(db, kisi, set(PAKET_VARSAYILANI[PermissionPackage.VIEWER]) - {"rapor.gor"})
    assert izin_var_mi(db, kisi, "rapor.gor") is False


def test_varsayilanla_ayni_olan_satir_saklanmiyor(db, make_user):
    """Paket varsayilani ileride degisirse ozellestirilmemis kisiye yansimali."""
    kisi = make_user()
    kisi.permission_package = PermissionPackage.EDITOR
    db.flush()

    izinleri_yaz(db, kisi, set(PAKET_VARSAYILANI[PermissionPackage.EDITOR]))
    satirlar = db.execute(
        select(UserPermission).where(UserPermission.user_id == kisi.id)
    ).scalars().all()
    assert satirlar == []


def test_varsayilana_donulebiliyor(db, make_user):
    kisi = make_user()
    kisi.permission_package = PermissionPackage.VIEWER
    db.flush()

    izinleri_yaz(db, kisi, {"icerik.onayla"})
    assert izin_var_mi(db, kisi, "icerik.onayla") is True

    varsayilana_don(db, kisi)
    assert kullanici_izinleri(db, kisi) == PAKET_VARSAYILANI[PermissionPackage.VIEWER]


def test_paket_degisince_ozellestirmeler_siliniyor(db, make_user):
    """Eski pakete gore 'sunu kapat' ayari yeni pakette tehlikeli olurdu."""
    kisi = make_user()
    kisi.permission_package = PermissionPackage.VIEWER
    db.flush()

    izinleri_yaz(db, kisi, set(PAKET_VARSAYILANI[PermissionPackage.VIEWER]) - {"rapor.gor"})
    assert izin_var_mi(db, kisi, "rapor.gor") is False

    paketi_degistir(db, kisi, PermissionPackage.STRATEGIST)
    assert kullanici_izinleri(db, kisi) == PAKET_VARSAYILANI[PermissionPackage.STRATEGIST]


def test_ayar_yalnizca_o_kullaniciyi_etkiliyor(db, make_user):
    biri = make_user()
    digeri = make_user()
    biri.permission_package = PermissionPackage.VIEWER
    digeri.permission_package = PermissionPackage.VIEWER
    db.flush()

    izinleri_yaz(db, biri, set())
    assert izin_var_mi(db, biri, "rapor.gor") is False
    assert izin_var_mi(db, digeri, "rapor.gor") is True


def test_izinler_musteriye_gore_degismiyor(db, make_user, make_workspace, add_member):
    """Ayni kisi her musteride AYNI seyi yapabilir; kafa karisikligi olmaz."""
    kisi = make_user()
    kisi.permission_package = PermissionPackage.EDITOR
    a = make_workspace(name="Musteri A")
    b = make_workspace(name="Musteri B")
    add_member(a, kisi)
    add_member(b, kisi)
    db.flush()

    assert kullanici_izinleri(db, kisi) == PAKET_VARSAYILANI[PermissionPackage.EDITOR]


# --- Panel: yetkiler Kullanicilar altinda ------------------------------------

def test_yetki_sayfasi_kullanicinin_altinda(client, db, iki_kisi):
    """Yetkiler ARTIK musterinin altinda degil, kullanicinin altinda."""
    yonetici, kisi, ws = iki_kisi()
    _giris(client, yonetici)

    sayfa = client.get(f"/panel/kullanicilar/{kisi.id}")
    assert sayfa.status_code == 200
    assert "Yetkiler" in sayfa.text
    assert "Marka bilgilerini düzenle" in sayfa.text
    assert "Hazır paket" in sayfa.text

    # Musterinin altinda boyle bir sayfa KALMADI.
    assert client.get(f"/panel/musteri/{ws.id}/yetkiler").status_code == 404


def test_menude_musteri_altinda_yetkiler_yok(client, db, iki_kisi):
    yonetici, _kisi, ws = iki_kisi()
    _giris(client, yonetici)
    sayfa = client.get(f"/panel/musteri/{ws.id}")
    assert sayfa.status_code == 200
    assert f"/panel/musteri/{ws.id}/yetkiler" not in sayfa.text


def test_panelden_yetki_degistirilebiliyor(client, db, iki_kisi):
    yonetici, kisi, _ws = iki_kisi()
    _giris(client, yonetici)

    yanit = client.post(
        f"/panel/kullanicilar/{kisi.id}/yetkiler",
        data={"izin": sorted(PAKET_VARSAYILANI[PermissionPackage.VIEWER] | {"icerik.onayla"})},
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    db.expire_all()
    assert izin_var_mi(db, kisi, "icerik.onayla") is True


def test_panelden_paket_degistirilebiliyor(client, db, iki_kisi):
    yonetici, kisi, _ws = iki_kisi()
    _giris(client, yonetici)

    yanit = client.post(
        f"/panel/kullanicilar/{kisi.id}/paket",
        data={"paket": "strategist"}, follow_redirects=False,
    )
    assert yanit.status_code == 303
    db.expire_all()
    assert db.get(type(kisi), kisi.id).permission_package is PermissionPackage.STRATEGIST


def test_sistem_yoneticisi_olmayan_yetki_sayfasina_giremiyor(client, db, iki_kisi):
    _yonetici, kisi, _ws = iki_kisi()
    _giris(client, kisi)
    # Kullanicilar bolumu sistem yoneticisine ozeldir.
    assert client.get(f"/panel/kullanicilar/{kisi.id}").status_code == 404
    assert client.post(
        f"/panel/kullanicilar/{kisi.id}/yetkiler", data={"izin": []},
    ).status_code == 404


# --- Gercekten uygulaniyor mu? -----------------------------------------------

def _izni_kaldir(client, db, yonetici, kisi, izin: str) -> None:
    _giris(client, yonetici)
    kalan = sorted(PAKET_VARSAYILANI[kisi.permission_package] - {izin})
    yanit = client.post(
        f"/panel/kullanicilar/{kisi.id}/yetkiler",
        data={"izin": kalan}, follow_redirects=False,
    )
    assert yanit.status_code == 303
    db.expire_all()
    assert izin_var_mi(db, kisi, izin) is False
    client.post("/panel/cikis")


@pytest.mark.parametrize(
    ("izin", "yol"),
    [("hesap.gor", "hesaplar"), ("ekip.gor", "ekip"), ("takvim.gor", "takvim")],
)
def test_gorme_izni_kaldirilinca_sayfa_acilmiyor(client, db, iki_kisi, izin, yol):
    yonetici, kisi, ws = iki_kisi()

    # Once ACILIYOR: testin bir sey olctugunu kanitlar.
    _giris(client, kisi)
    assert client.get(f"/panel/musteri/{ws.id}/{yol}").status_code == 200
    client.post("/panel/cikis")

    _izni_kaldir(client, db, yonetici, kisi, izin)

    # Artik 404: 403 degil, cunku sayfanin VARLIGI bile bilgi sizdirir.
    _giris(client, kisi)
    assert client.get(f"/panel/musteri/{ws.id}/{yol}").status_code == 404


def test_onay_izni_kaldirilinca_onay_verilemiyor(client, db, iki_kisi, rapor_olustur):
    """Onay, yetki sisteminin en kritik kapisi."""
    yonetici, kisi, ws = iki_kisi(PermissionPackage.ADMIN)
    rapor = rapor_olustur(ws, durum=ContentStatus.CLIENT_REVIEW)
    db.commit()

    _izni_kaldir(client, db, yonetici, kisi, "rapor.onayla")

    _giris(client, kisi)
    client.post(
        f"/panel/musteri/{ws.id}/rapor/{rapor.id}/karar",
        data={"target": "approved", "comment": ""}, follow_redirects=False,
    )
    db.expire_all()
    assert db.get(Report, rapor.id).status is ContentStatus.CLIENT_REVIEW


def test_verilen_onay_izni_gercekten_aciyor(client, db, iki_kisi, rapor_olustur):
    """Izin vermek de calismali; yoksa ayar tek yonlu olurdu."""
    yonetici, kisi, ws = iki_kisi(PermissionPackage.STRATEGIST)
    rapor = rapor_olustur(ws, durum=ContentStatus.CLIENT_REVIEW)
    db.commit()
    assert izin_var_mi(db, kisi, "rapor.onayla") is False

    _giris(client, yonetici)
    client.post(
        f"/panel/kullanicilar/{kisi.id}/yetkiler",
        data={"izin": sorted(PAKET_VARSAYILANI[PermissionPackage.STRATEGIST] | {"rapor.onayla"})},
    )
    client.post("/panel/cikis")

    _giris(client, kisi)
    client.post(
        f"/panel/musteri/{ws.id}/rapor/{rapor.id}/karar",
        data={"target": "approved", "comment": ""}, follow_redirects=False,
    )
    db.expire_all()
    assert db.get(Report, rapor.id).status is ContentStatus.APPROVED


def test_menu_acilamayan_sayfayi_gostermiyor(client, db, iki_kisi):
    yonetici, kisi, ws = iki_kisi()

    _giris(client, kisi)
    once = client.get(f"/panel/musteri/{ws.id}")
    assert f"/panel/musteri/{ws.id}/takvim" in once.text
    client.post("/panel/cikis")

    _izni_kaldir(client, db, yonetici, kisi, "takvim.gor")

    _giris(client, kisi)
    sonra = client.get(f"/panel/musteri/{ws.id}")
    assert f"/panel/musteri/{ws.id}/takvim" not in sonra.text
    # Menude gizlemek GUVENLIK DEGILDIR; adres elle yazilinca da kapali.
    assert client.get(f"/panel/musteri/{ws.id}/takvim").status_code == 404


def test_icerik_uret_izni_api_ucunda_da_uygulaniyor(
    client, db, make_user, make_workspace, add_member, auth_headers
):
    """AI uretimi PARA HARCATIR; izin kontrolu API ucunda da olmali."""
    kisi = make_user(password=SIFRE)
    kisi.permission_package = PermissionPackage.STRATEGIST
    ws = make_workspace(name="AI Izni")
    add_member(ws, kisi)
    db.commit()

    govde = {
        "brand_id": str(uuid.uuid4()),
        "platforms": ["instagram"],
        "brief": "Baklava tanitimi icin kisa video",
    }
    yol = f"/api/v1/workspaces/{ws.id}/ai/content-scripts"

    # Izin varken yetki kapisi GECILIR (marka uydurma oldugu icin 404).
    assert client.post(yol, json=govde, headers=auth_headers(kisi)).status_code == 404

    izinleri_yaz(
        db, kisi, set(PAKET_VARSAYILANI[PermissionPackage.STRATEGIST] - {"icerik.uret"})
    )
    db.commit()

    sonra = client.post(yol, json=govde, headers=auth_headers(kisi))
    assert sonra.status_code == 403
    assert "icerik.uret" in sonra.json()["detail"]


def test_her_izin_bir_yerde_gercekten_kontrol_ediliyor():
    """Katalogda olup HICBIR YERDE kontrol edilmeyen izin olmamali.

    Boyle bir izin, panelde acilip kapatilabilen ama hicbir sey yapmayan
    bir dugme demektir.
    """
    kok = pathlib.Path(__file__).resolve().parent.parent / "app"
    kaynak = ""
    for dosya in kok.rglob("*.py"):
        if dosya.name == "yetkiler.py":
            continue
        kaynak += dosya.read_text(encoding="utf-8")

    kontrolsuz = sorted(i for i in IZIN_ANAHTARLARI if f'"{i}"' not in kaynak)
    assert kontrolsuz == [], (
        "Bu izinler panelde gorunuyor ama hicbir yerde uygulanmiyor: "
        + ", ".join(kontrolsuz)
    )


# --- Yetkiler ekrani GORUNUR olmali ------------------------------------------
#
# Yetkiler yalnizca "Kullanicilar -> kisiye tikla -> asagi kaydir"
# yolundan ulasilabiliyordu. Menude "Yetkiler" diye bir sey yoktu; bu
# yuzden ozellik VAR olmasina ragmen YOK sanildi.
#
# Gorunmeyen bir ozellik, olmayan bir ozelliktir.

def test_menude_yetkiler_baglantisi_var(client, db, iki_kisi):
    yonetici, _kisi, _ws = iki_kisi()
    _giris(client, yonetici)
    sayfa = client.get("/panel")
    assert '/panel/yetkiler' in sayfa.text


def test_yetkiler_ekrani_herkesi_listeliyor(client, db, iki_kisi):
    yonetici, kisi, _ws = iki_kisi()
    _giris(client, yonetici)

    sayfa = client.get("/panel/yetkiler")
    assert sayfa.status_code == 200
    assert kisi.email in sayfa.text
    assert "Kategoriler ne yapabilir?" in sayfa.text


def test_kategori_ekrandan_degistirilebiliyor(client, db, iki_kisi):
    yonetici, kisi, _ws = iki_kisi(PermissionPackage.VIEWER)
    _giris(client, yonetici)

    yanit = client.post(
        "/panel/yetkiler/paket",
        data={"user_id": str(kisi.id), "paket": "strategist"},
    )
    assert yanit.status_code == 200
    db.expire_all()
    assert db.get(type(kisi), kisi.id).permission_package is PermissionPackage.STRATEGIST


def test_ozellestirilmis_kisi_isaretleniyor(client, db, iki_kisi):
    """'Bu kisi neden farkli?' sorusu tabloyu terk etmeden gorulmeli."""
    yonetici, kisi, _ws = iki_kisi(PermissionPackage.VIEWER)
    izinleri_yaz(db, kisi, set(PAKET_VARSAYILANI[PermissionPackage.VIEWER]) | {"icerik.onayla"})
    db.commit()

    _giris(client, yonetici)
    sayfa = client.get("/panel/yetkiler")
    assert "özelleştirilmiş" in sayfa.text


def test_sistem_yoneticisinin_kategorisi_degistirilemiyor(client, db, iki_kisi):
    yonetici, _kisi, _ws = iki_kisi()
    _giris(client, yonetici)

    yanit = client.post(
        "/panel/yetkiler/paket",
        data={"user_id": str(yonetici.id), "paket": "viewer"},
    )
    assert yanit.status_code == 400
    db.expire_all()
    assert db.get(type(yonetici), yonetici.id).is_superuser is True


def test_yetkiler_ekrani_sistem_yoneticisine_ozel(client, db, iki_kisi):
    _yonetici, kisi, _ws = iki_kisi()
    _giris(client, kisi)
    assert client.get("/panel/yetkiler").status_code == 404
    assert client.post(
        "/panel/yetkiler/paket",
        data={"user_id": str(kisi.id), "paket": "admin"},
    ).status_code == 404
