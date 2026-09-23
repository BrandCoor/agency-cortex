"""Ayrintili yetki sistemi.

Korunan kurallar:
- Ozellestirme yapilmamissa varsayilan roller AYNEN calisir
- SAHIP kisitlanamaz; aksi halde musteri yonetilemez hale gelir
- Kimse kendi rolunun yetkisini degistiremez
- Ayar yalnizca O MUSTERIYI etkiler
- Tanimsiz izin asla verilmez
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.enums import WorkspaceRole
from app.models.yetki import RoleGrant
from app.panel.auth import COOKIE_NAME
from app.services.yetkiler import (
    IZIN_ANAHTARLARI,
    VARSAYILAN,
    YetkiHatasi,
    izin_var_mi,
    izinleri_yaz,
    rol_izinleri,
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
    def _kur(rol=WorkspaceRole.OWNER):
        kullanici = make_user(password=SIFRE)
        ws = make_workspace(name="Yetki Musterisi")
        add_member(ws, kullanici, rol)
        db.commit()
        _giris(client, kullanici)
        return kullanici, ws

    return _kur


# --- Varsayilanlar -----------------------------------------------------------

def test_ozellestirme_yoksa_varsayilanlar_geciyor(db, make_workspace):
    ws = make_workspace(name="Varsayilan")
    db.flush()

    assert rol_izinleri(db, ws.id, WorkspaceRole.VIEWER) == VARSAYILAN[WorkspaceRole.VIEWER]
    assert izin_var_mi(db, ws.id, WorkspaceRole.STRATEGIST, "icerik.uret") is True
    assert izin_var_mi(db, ws.id, WorkspaceRole.VIEWER, "icerik.uret") is False
    assert izin_var_mi(db, ws.id, WorkspaceRole.EDITOR, "icerik.onayla") is False


def test_sahip_her_zaman_her_seyi_yapabiliyor(db, make_workspace):
    ws = make_workspace(name="Sahip")
    db.flush()
    assert rol_izinleri(db, ws.id, WorkspaceRole.OWNER) == IZIN_ANAHTARLARI


def test_sahibin_izni_kisitlanamiyor(db, make_workspace):
    """Kisitlanabilseydi musteri yonetilemez hale gelirdi."""
    ws = make_workspace(name="Sahip Kilit")
    db.flush()

    with pytest.raises(YetkiHatasi) as hata:
        izinleri_yaz(db, ws.id, WorkspaceRole.OWNER, set())
    assert "kısıtlanamaz" in str(hata.value)
    assert rol_izinleri(db, ws.id, WorkspaceRole.OWNER) == IZIN_ANAHTARLARI


def test_tanimsiz_izin_verilmiyor(db, make_workspace):
    ws = make_workspace(name="Tanimsiz")
    db.flush()

    with pytest.raises(YetkiHatasi):
        izinleri_yaz(db, ws.id, WorkspaceRole.VIEWER, {"uydurma.izin"})
    with pytest.raises(YetkiHatasi):
        izin_var_mi(db, ws.id, WorkspaceRole.VIEWER, "uydurma.izin")


# --- Ozellestirme ------------------------------------------------------------

def test_izin_eklenebiliyor_ve_kaldirilabiliyor(db, make_workspace):
    ws = make_workspace(name="Ozel")
    db.flush()

    # Izleyiciye icerik duzenleme verelim.
    yeni = set(VARSAYILAN[WorkspaceRole.VIEWER]) | {"icerik.duzenle"}
    izinleri_yaz(db, ws.id, WorkspaceRole.VIEWER, yeni)
    assert izin_var_mi(db, ws.id, WorkspaceRole.VIEWER, "icerik.duzenle") is True

    # Stratejistten icerik uretmeyi alalim (para harcatan is).
    kisitli = set(VARSAYILAN[WorkspaceRole.STRATEGIST]) - {"icerik.uret"}
    izinleri_yaz(db, ws.id, WorkspaceRole.STRATEGIST, kisitli)
    assert izin_var_mi(db, ws.id, WorkspaceRole.STRATEGIST, "icerik.uret") is False


def test_varsayilanla_ayni_olan_satir_saklanmiyor(db, make_workspace):
    """Varsayilan degisirse ozellestirilmemis roller yeni varsayilani almali."""
    ws = make_workspace(name="Temiz")
    db.flush()

    izinleri_yaz(db, ws.id, WorkspaceRole.VIEWER, set(VARSAYILAN[WorkspaceRole.VIEWER]))
    assert db.execute(select(RoleGrant)).scalars().all() == []

    # Tek bir fark yazilinca YALNIZCA o satir olusur.
    izinleri_yaz(
        db, ws.id, WorkspaceRole.VIEWER,
        set(VARSAYILAN[WorkspaceRole.VIEWER]) | {"icerik.duzenle"},
    )
    satirlar = db.execute(select(RoleGrant)).scalars().all()
    assert len(satirlar) == 1
    assert satirlar[0].permission == "icerik.duzenle"
    assert satirlar[0].allowed is True


def test_varsayilana_donulebiliyor(db, make_workspace):
    ws = make_workspace(name="Geri Al")
    db.flush()

    izinleri_yaz(db, ws.id, WorkspaceRole.EDITOR, set())
    assert rol_izinleri(db, ws.id, WorkspaceRole.EDITOR) == frozenset()

    varsayilana_don(db, ws.id, WorkspaceRole.EDITOR)
    assert rol_izinleri(db, ws.id, WorkspaceRole.EDITOR) == VARSAYILAN[WorkspaceRole.EDITOR]


def test_ayar_yalnizca_o_musteriyi_etkiliyor(db, make_workspace):
    bir = make_workspace(name="Bir")
    iki = make_workspace(name="Iki")
    db.flush()

    izinleri_yaz(db, bir.id, WorkspaceRole.VIEWER, set())

    assert rol_izinleri(db, bir.id, WorkspaceRole.VIEWER) == frozenset()
    assert rol_izinleri(db, iki.id, WorkspaceRole.VIEWER) == VARSAYILAN[WorkspaceRole.VIEWER]


# --- Panel -------------------------------------------------------------------

def test_sayfa_aciliyor_ve_matrisi_gosteriyor(client, db, ortam):
    _, ws = ortam()
    yanit = client.get(f"/panel/musteri/{ws.id}/yetkiler")

    assert yanit.status_code == 200
    assert "Marka bilgilerini düzenle" in yanit.text
    assert "İçeriği onayla veya reddet" in yanit.text
    assert "Stratejist" in yanit.text


def test_uye_olunmayan_musterinin_yetkileri_gorunmuyor(
    client, db, make_user, make_workspace
):
    kullanici = make_user(password=SIFRE)
    baskasi = make_workspace(name="Baskasinin")
    db.commit()
    _giris(client, kullanici)

    yanit = client.get(f"/panel/musteri/{baskasi.id}/yetkiler")
    assert yanit.status_code == 404


def test_panelden_yetki_degistirilebiliyor(client, db, ortam):
    _, ws = ortam(WorkspaceRole.OWNER)

    yanit = client.post(
        f"/panel/musteri/{ws.id}/yetkiler/kaydet",
        data={"rol": "viewer", "izin": ["takvim.gor", "rapor.gor"]},
    )
    assert yanit.status_code == 200
    assert izin_var_mi(db, ws.id, WorkspaceRole.VIEWER, "takvim.gor") is True
    assert izin_var_mi(db, ws.id, WorkspaceRole.VIEWER, "hesap.gor") is False


def test_kendi_rolunun_yetkisi_degistirilemiyor(client, db, ortam):
    """Kendini kilitleyen bir degisiklik yapilamamali."""
    _, ws = ortam(WorkspaceRole.ADMIN)

    yanit = client.post(
        f"/panel/musteri/{ws.id}/yetkiler/kaydet",
        data={"rol": "admin", "izin": []},
    )
    assert yanit.status_code == 400
    assert "Kendi rolünüzün" in yanit.text
    assert izin_var_mi(db, ws.id, WorkspaceRole.ADMIN, "yetki.duzenle") is True


def test_sahip_rolu_panelden_de_kisitlanamiyor(client, db, ortam):
    _, ws = ortam(WorkspaceRole.ADMIN)

    yanit = client.post(
        f"/panel/musteri/{ws.id}/yetkiler/kaydet",
        data={"rol": "owner", "izin": []},
    )
    assert yanit.status_code == 400
    assert rol_izinleri(db, ws.id, WorkspaceRole.OWNER) == IZIN_ANAHTARLARI


def test_yetkisiz_kullanici_degistiremiyor(client, db, ortam):
    _, ws = ortam(WorkspaceRole.STRATEGIST)

    yanit = client.post(
        f"/panel/musteri/{ws.id}/yetkiler/kaydet",
        data={"rol": "viewer", "izin": []},
    )
    assert yanit.status_code == 403
    assert rol_izinleri(db, ws.id, WorkspaceRole.VIEWER) == VARSAYILAN[WorkspaceRole.VIEWER]


# --- Gercekten uygulaniyor mu? ----------------------------------------------

def test_kisitlanan_izin_gercekten_engelliyor(
    client, db, make_user, make_workspace, add_member
):
    """Ayar ekranda degisip sunucuda uygulanmazsa hicbir anlami olmaz."""
    sahip = make_user(password=SIFRE)
    stratejist = make_user(password=SIFRE)
    ws = make_workspace(name="Uygulama")
    add_member(ws, sahip, WorkspaceRole.OWNER)
    add_member(ws, stratejist, WorkspaceRole.STRATEGIST)
    db.commit()

    # Stratejist varsayilan olarak markayi duzenleyebilir.
    _giris(client, stratejist)
    ilk = client.post(
        f"/panel/musteri/{ws.id}/marka",
        data={"ad": "Deneme Marka", "sektor": "", "aciklama": "",
              "marka_dili": "", "hedef_kitle": "", "yasakli": "",
              "tercih": "", "notlar": ""},
    )
    assert ilk.status_code == 200
    client.post("/panel/cikis")

    # Sahip bu izni kaldirir.
    _giris(client, sahip)
    client.post(
        f"/panel/musteri/{ws.id}/yetkiler/kaydet",
        data={
            "rol": "strategist",
            "izin": sorted(VARSAYILAN[WorkspaceRole.STRATEGIST] - {"marka.duzenle"}),
        },
    )
    client.post("/panel/cikis")

    # Artik SUNUCU engelliyor.
    _giris(client, stratejist)
    sonra = client.post(
        f"/panel/musteri/{ws.id}/marka",
        data={"ad": "Yeni Ad", "sektor": "", "aciklama": "",
              "marka_dili": "", "hedef_kitle": "", "yasakli": "",
              "tercih": "", "notlar": ""},
    )
    assert sonra.status_code == 403


def test_verilen_izin_gercekten_aciyor(
    client, db, make_user, make_workspace, add_member
):
    sahip = make_user(password=SIFRE)
    izleyici = make_user(password=SIFRE)
    ws = make_workspace(name="Acma")
    add_member(ws, sahip, WorkspaceRole.OWNER)
    add_member(ws, izleyici, WorkspaceRole.VIEWER)
    db.commit()

    # Izleyici varsayilan olarak otomasyon ayari degistiremez.
    _giris(client, izleyici)
    ilk = client.post(
        "/panel/otomasyon/akis",
        data={"workspace_id": str(ws.id), "workflow_key": "wf04_haftalik_rapor",
              "acik": "1"},
    )
    assert ilk.status_code == 403
    client.post("/panel/cikis")

    # Sahip bu izni verir.
    _giris(client, sahip)
    client.post(
        f"/panel/musteri/{ws.id}/yetkiler/kaydet",
        data={
            "rol": "viewer",
            "izin": sorted(set(VARSAYILAN[WorkspaceRole.VIEWER]) | {"otomasyon.ayar"}),
        },
    )
    client.post("/panel/cikis")

    # Artik yapabiliyor.
    _giris(client, izleyici)
    sonra = client.post(
        "/panel/otomasyon/akis",
        data={"workspace_id": str(ws.id), "workflow_key": "wf04_haftalik_rapor",
              "acik": "1"},
    )
    assert sonra.status_code == 200
