"""Ayrintili yetki sistemi.

Korunan kurallar:
- Ozellestirme yapilmamissa varsayilan roller AYNEN calisir
- SAHIP kisitlanamaz; aksi halde musteri yonetilemez hale gelir
- Kimse kendi rolunun yetkisini degistiremez
- Ayar yalnizca O MUSTERIYI etkiler
- Tanimsiz izin asla verilmez
"""

from __future__ import annotations

import datetime as dt
import pathlib
import uuid

import pytest
from sqlalchemy import select

from app.models.enums import ContentStatus, ReportPeriod, WorkspaceRole
from app.models.reporting import Report
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
    assert "İçeriği onayla veya arşivle" in yanit.text
    assert "Raporu müşteriye sun veya reddet" in yanit.text
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


# --- Once HIC uygulanmayan izinler -------------------------------------------
#
# Bu izinler katalogda vardi, panelde acilip kapatilabiliyordu ama HICBIR
# YERDE kontrol edilmiyordu. Yani kullanici izni kapatiyor, sayfa yine
# aciliyordu. Asagidaki testler her birinin GERCEKTEN uygulandigini
# gosterir; biri tekrar sessizce kopdugunda test duser.

def _izni_kaldir(client, db, sahip, ws, rol: WorkspaceRole, izin: str) -> None:
    """Sahip olarak girip bir rolden tek bir izni kaldirir."""
    _giris(client, sahip)
    yanit = client.post(
        f"/panel/musteri/{ws.id}/yetkiler/kaydet",
        data={"rol": rol.value, "izin": sorted(VARSAYILAN[rol] - {izin})},
    )
    assert yanit.status_code in (200, 303)
    db.expire_all()
    assert izin_var_mi(db, ws.id, rol, izin) is False
    client.post("/panel/cikis")


@pytest.fixture
def iki_kisi(client, db, make_user, make_workspace, add_member):
    """Sahip (ayari yapan) + izleyici (kisitlanan)."""
    def _kur(rol=WorkspaceRole.VIEWER):
        sahip = make_user(password=SIFRE)
        kisi = make_user(password=SIFRE)
        ws = make_workspace(name="Uygulama Kontrolu")
        add_member(ws, sahip, WorkspaceRole.OWNER)
        add_member(ws, kisi, rol)
        db.commit()
        return sahip, kisi, ws

    return _kur


@pytest.mark.parametrize(
    ("izin", "yol"),
    [
        ("hesap.gor", "hesaplar"),
        ("ekip.gor", "ekip"),
        ("takvim.gor", "takvim"),
    ],
)
def test_gorme_izni_kaldirilinca_sayfa_acilmiyor(client, db, iki_kisi, izin, yol):
    sahip, kisi, ws = iki_kisi()

    # Once ACILIYOR: testin bir sey olcttugunu kanitlar.
    _giris(client, kisi)
    assert client.get(f"/panel/musteri/{ws.id}/{yol}").status_code == 200
    client.post("/panel/cikis")

    _izni_kaldir(client, db, sahip, ws, WorkspaceRole.VIEWER, izin)

    # Artik 404: 403 degil, cunku sayfanin VARLIGI bile bilgi sizdirir.
    _giris(client, kisi)
    assert client.get(f"/panel/musteri/{ws.id}/{yol}").status_code == 404


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


def test_rapor_gor_izni_kaldirilinca_rapor_acilmiyor(
    client, db, iki_kisi, rapor_olustur
):
    sahip, kisi, ws = iki_kisi()
    rapor = rapor_olustur(ws)
    db.commit()

    _giris(client, kisi)
    assert client.get(f"/panel/musteri/{ws.id}/rapor/{rapor.id}").status_code == 200
    client.post("/panel/cikis")

    _izni_kaldir(client, db, sahip, ws, WorkspaceRole.VIEWER, "rapor.gor")

    _giris(client, kisi)
    assert client.get(f"/panel/musteri/{ws.id}/rapor/{rapor.id}").status_code == 404


def test_onay_izni_kaldirilinca_onay_verilemiyor(client, db, iki_kisi, rapor_olustur):
    """Onay, yetki sisteminin en kritik kapisi.

    ONCEDEN bu kontrol koda gomulu ROLE bakiyordu; panelden yapilan ayarin
    hicbir etkisi yoktu.
    """
    sahip, yonetici, ws = iki_kisi(WorkspaceRole.ADMIN)
    rapor = rapor_olustur(ws, durum=ContentStatus.CLIENT_REVIEW)
    db.commit()

    _izni_kaldir(client, db, sahip, ws, WorkspaceRole.ADMIN, "rapor.onayla")

    _giris(client, yonetici)
    yanit = client.post(
        f"/panel/musteri/{ws.id}/rapor/{rapor.id}/karar",
        data={"target": "approved", "comment": ""},
        follow_redirects=False,
    )
    # Yonlendirme icinde hata tasinir; ASIL kanit raporun durumudur.
    assert yanit.status_code == 303
    db.expire_all()
    assert db.get(Report, rapor.id).status is ContentStatus.CLIENT_REVIEW


def test_verilen_onay_izni_gercekten_aciyor(client, db, iki_kisi, rapor_olustur):
    """Izin vermek de calismali; yoksa ayar tek yonlu olurdu."""
    sahip, stratejist, ws = iki_kisi(WorkspaceRole.STRATEGIST)
    rapor = rapor_olustur(ws, durum=ContentStatus.CLIENT_REVIEW)
    db.commit()

    # Stratejist varsayilan olarak rapor ONAYLAYAMAZ.
    assert izin_var_mi(db, ws.id, WorkspaceRole.STRATEGIST, "rapor.onayla") is False

    _giris(client, sahip)
    client.post(
        f"/panel/musteri/{ws.id}/yetkiler/kaydet",
        data={
            "rol": "strategist",
            "izin": sorted(VARSAYILAN[WorkspaceRole.STRATEGIST] | {"rapor.onayla"}),
        },
    )
    client.post("/panel/cikis")

    _giris(client, stratejist)
    client.post(
        f"/panel/musteri/{ws.id}/rapor/{rapor.id}/karar",
        data={"target": "approved", "comment": ""},
        follow_redirects=False,
    )
    db.expire_all()
    assert db.get(Report, rapor.id).status is ContentStatus.APPROVED


def test_dugme_gorunmuyorsa_sunucu_da_reddediyor(client, db, iki_kisi, rapor_olustur):
    """Panelde gizlenen secenek, ELLE gonderildiginde de reddedilmeli."""
    sahip, yonetici, ws = iki_kisi(WorkspaceRole.ADMIN)
    rapor = rapor_olustur(ws, durum=ContentStatus.CLIENT_REVIEW)
    db.commit()

    _izni_kaldir(client, db, sahip, ws, WorkspaceRole.ADMIN, "rapor.onayla")

    _giris(client, yonetici)
    sayfa = client.get(f"/panel/musteri/{ws.id}/rapor/{rapor.id}")
    assert sayfa.status_code == 200
    # Secenek listede YOK...
    assert 'value="approved"' not in sayfa.text
    # ...ve elle gonderilse de gecmiyor (yukaridaki test bunu kanitliyor).


def test_icerik_uret_izni_api_ucunda_da_uygulaniyor(
    client, db, make_user, make_workspace, add_member, auth_headers
):
    """AI uretimi PARA HARCATIR; izin kontrolu API ucunda da olmali.

    Bu uc daha once sabit bir ROL bekliyordu. Panelden 'içerik ürettir'
    iznini kapatmak, bu ucu HIC etkilemiyordu.
    """
    stratejist = make_user(password=SIFRE)
    ws = make_workspace(name="AI Izni")
    add_member(ws, stratejist, WorkspaceRole.STRATEGIST)
    db.commit()

    govde = {
        "brand_id": str(uuid.uuid4()),
        "platforms": ["instagram"],
        "brief": "Baklava tanitimi icin kisa video",
    }
    yol = f"/api/v1/workspaces/{ws.id}/ai/content-scripts"

    # Izin varken: yetki kapisi GECILIR. (Marka uydurma oldugu icin 404;
    # onemli olan 403 OLMAMASI.)
    ilk = client.post(yol, json=govde, headers=auth_headers(stratejist))
    assert ilk.status_code == 404

    izinleri_yaz(
        db, ws.id, WorkspaceRole.STRATEGIST,
        set(VARSAYILAN[WorkspaceRole.STRATEGIST] - {"icerik.uret"}),
    )
    db.commit()

    sonra = client.post(yol, json=govde, headers=auth_headers(stratejist))
    assert sonra.status_code == 403
    assert "icerik.uret" in sonra.json()["detail"]


def test_her_izin_bir_yerde_gercekten_kontrol_ediliyor():
    """Katalogda olup HICBIR YERDE kontrol edilmeyen izin olmamali.

    Boyle bir izin, panelde acilip kapatilabilen ama hicbir sey yapmayan
    bir dugme demektir. Bu test bir kez dustu: 19 iznin 8'i hicbir yerde
    kontrol edilmiyordu.
    """
    # Calisma dizinine BAGIMLI olmasin: test dosyasindan turetilir.
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


# --- Kenar menu ---------------------------------------------------------------

def test_menu_acilamayan_sayfayi_gostermiyor(client, db, iki_kisi):
    """Tiklayinca "Bulunamadı" veren baglanti, calismayan bir dugmedir."""
    sahip, izleyici, ws = iki_kisi()

    _giris(client, izleyici)
    once = client.get(f"/panel/musteri/{ws.id}")
    assert once.status_code == 200
    assert f"/panel/musteri/{ws.id}/takvim" in once.text
    # İzleyicide "Yetkiler" zaten olmamali (varsayilanda yetki.duzenle yok).
    assert f"/panel/musteri/{ws.id}/yetkiler" not in once.text
    client.post("/panel/cikis")

    _izni_kaldir(client, db, sahip, ws, WorkspaceRole.VIEWER, "takvim.gor")

    _giris(client, izleyici)
    sonra = client.get(f"/panel/musteri/{ws.id}")
    assert sonra.status_code == 200
    assert f"/panel/musteri/{ws.id}/takvim" not in sonra.text


def test_menude_gizlenen_sayfa_adres_yazilinca_da_acilmiyor(client, db, iki_kisi):
    """Menude gizlemek GUVENLIK DEGILDIR; kilit sayfanin kendisinde."""
    sahip, izleyici, ws = iki_kisi()
    _izni_kaldir(client, db, sahip, ws, WorkspaceRole.VIEWER, "takvim.gor")

    _giris(client, izleyici)
    assert client.get(f"/panel/musteri/{ws.id}/takvim").status_code == 404


def test_sahip_tum_sayfalarda_tum_menuyu_goruyor(client, db, iki_kisi, rapor_olustur):
    """Menu izinleri bir sayfada hazirlanmazsa o sayfada menu EKSIK gorunur.

    Bu test, izinlerin her musteri sayfasinda hazirlandigini dogrular.
    """
    sahip, _, ws = iki_kisi()
    rapor = rapor_olustur(ws)
    db.commit()
    _giris(client, sahip)

    sayfalar = [
        f"/panel/musteri/{ws.id}",
        f"/panel/musteri/{ws.id}/marka",
        f"/panel/musteri/{ws.id}/takvim",
        f"/panel/musteri/{ws.id}/kampanya",
        f"/panel/musteri/{ws.id}/hesaplar",
        f"/panel/musteri/{ws.id}/ekip",
        f"/panel/musteri/{ws.id}/yetkiler",
        f"/panel/musteri/{ws.id}/rapor/{rapor.id}",
    ]
    for yol in sayfalar:
        yanit = client.get(yol)
        assert yanit.status_code == 200, yol
        for beklenen in ("takvim", "hesaplar", "ekip", "yetkiler"):
            assert f"/panel/musteri/{ws.id}/{beklenen}" in yanit.text, (
                f"{yol} sayfasinda menude '{beklenen}' baglantisi eksik"
            )
