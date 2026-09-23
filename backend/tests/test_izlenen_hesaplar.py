"""Izlenen hesaplar: BAGLI hesaptan ayri bir kavram.

Korunan kurallar:
- Bagli hesap ile izlenen hesap AYRI listelerdir; karistirilmaz
- Zaten bagli olan hesap ayrica izlemeye alinamaz
- Kullanici adi '@' veya tam baglanti olarak yazilabilir
- Veri cekilemiyorsa SEBEBI yazilir; sessiz basarisizlik olmaz
- Baska musterinin kaydi gorunmez ve silinemez
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.enums import PermissionPackage, Platform
from app.models.izlenen import IzlemeTuru, TrackedAccount
from app.models.social import SocialAccount
from app.services.izlenen_hesaplar import (
    VERI_KAYNAGI_YOK,
    IzlemeHatasi,
    ekle,
    kaldir,
    kullanici_adi_ayikla,
    listele,
)

SIFRE = "GucluSifre123!"


def _giris(client, kullanici):
    yanit = client.post(
        "/panel/giris", data={"email": kullanici.email, "password": SIFRE},
        follow_redirects=False,
    )
    assert yanit.status_code == 303


@pytest.fixture
def ortam(client, db, make_user, make_workspace, add_member):
    def _kur(paket=PermissionPackage.ADMIN):
        kullanici = make_user(password=SIFRE)
        kullanici.permission_package = paket
        ws = make_workspace(name="Izleme Musterisi")
        add_member(ws, kullanici)
        db.commit()
        _giris(client, kullanici)
        return kullanici, ws

    return _kur


# --- Kullanici adi ayiklama ---------------------------------------------------

@pytest.mark.parametrize(
    ("yazilan", "beklenen"),
    [
        ("markaadi", "markaadi"),
        ("@MarkaAdi", "markaadi"),
        ("https://instagram.com/markaadi", "markaadi"),
        ("https://www.instagram.com/markaadi/", "markaadi"),
        ("instagram.com/markaadi?hl=tr", "markaadi"),
        ("  @marka.adi  ", "marka.adi"),
    ],
)
def test_kullanici_adi_ayiklaniyor(yazilan, beklenen):
    """Kullanici bazen '@ad', bazen tam baglanti yapistirir; ikisi de gecerli."""
    assert kullanici_adi_ayikla(yazilan) == beklenen


@pytest.mark.parametrize("yazilan", ["", "   ", "boşluk lu", "çok#garip"])
def test_anlasilmayan_ad_reddediliyor(yazilan):
    with pytest.raises(IzlemeHatasi):
        kullanici_adi_ayikla(yazilan)


# --- Ekleme / kaldirma --------------------------------------------------------

def test_hesap_izlemeye_alinabiliyor(db, make_workspace):
    ws = make_workspace(name="Izleme")
    db.flush()
    kayit = ekle(
        db, workspace_id=ws.id, platform=Platform.INSTAGRAM,
        ham_ad="@RakipMarka", tur=IzlemeTuru.RAKIP,
    )
    assert kayit.username == "rakipmarka"
    assert kayit.tur is IzlemeTuru.RAKIP
    # Veri cekilemiyorsa SEBEBI yazili olmali.
    assert kayit.veri_durumu == VERI_KAYNAGI_YOK


def test_ayni_hesap_iki_kez_izlenemiyor(db, make_workspace):
    ws = make_workspace(name="Izleme")
    db.flush()
    ekle(db, workspace_id=ws.id, platform=Platform.INSTAGRAM,
         ham_ad="rakip", tur=IzlemeTuru.RAKIP)
    with pytest.raises(IzlemeHatasi):
        ekle(db, workspace_id=ws.id, platform=Platform.INSTAGRAM,
             ham_ad="@rakip", tur=IzlemeTuru.RAKIP)


def test_zaten_bagli_hesap_izlemeye_alinamiyor(db, make_workspace):
    """Ayni hesap iki listede olsaydi hangi veri gecerli belirsizlesirdi."""
    ws = make_workspace(name="Izleme")
    db.flush()
    db.add(SocialAccount(
        workspace_id=ws.id, platform=Platform.INSTAGRAM,
        external_id="123", username="bizimmarka",
    ))
    db.flush()

    with pytest.raises(IzlemeHatasi) as hata:
        ekle(db, workspace_id=ws.id, platform=Platform.INSTAGRAM,
             ham_ad="@bizimmarka", tur=IzlemeTuru.KENDI)
    assert "zaten BAĞLI" in str(hata.value)


def test_ayni_ad_farkli_musteride_izlenebiliyor(db, make_workspace):
    a = make_workspace(name="A")
    b = make_workspace(name="B")
    db.flush()
    ekle(db, workspace_id=a.id, platform=Platform.INSTAGRAM,
         ham_ad="rakip", tur=IzlemeTuru.RAKIP)
    ekle(db, workspace_id=b.id, platform=Platform.INSTAGRAM,
         ham_ad="rakip", tur=IzlemeTuru.RAKIP)
    assert len(listele(db, a.id)) == 1
    assert len(listele(db, b.id)) == 1


def test_baska_musterinin_kaydi_silinemiyor(db, make_workspace):
    a = make_workspace(name="A")
    b = make_workspace(name="B")
    db.flush()
    kayit = ekle(db, workspace_id=a.id, platform=Platform.INSTAGRAM,
                 ham_ad="rakip", tur=IzlemeTuru.RAKIP)
    with pytest.raises(IzlemeHatasi):
        kaldir(db, workspace_id=b.id, kayit_id=kayit.id)
    assert db.get(TrackedAccount, kayit.id) is not None


# --- Panel --------------------------------------------------------------------

def test_panelde_iki_liste_ayri_gosteriliyor(client, ortam):
    _, ws = ortam()
    sayfa = client.get(f"/panel/musteri/{ws.id}/hesaplar")
    assert sayfa.status_code == 200
    assert "İzlenen hesaplar" in sayfa.text
    assert "Bağlamak ile izlemek aynı şey değildir" in sayfa.text


def test_panelden_izlemeye_eklenebiliyor(client, db, ortam):
    _, ws = ortam()
    yanit = client.post(
        f"/panel/musteri/{ws.id}/hesaplar/izle",
        data={
            "platform": "instagram",
            "kullanici_adi": "https://instagram.com/rakipmarka/",
            "tur": "rakip",
            "notlar": "Aynı sektör",
        },
    )
    assert yanit.status_code == 200
    kayit = db.execute(
        select(TrackedAccount).where(TrackedAccount.workspace_id == ws.id)
    ).scalar_one()
    assert kayit.username == "rakipmarka"
    assert kayit.notlar == "Aynı sektör"


def test_panelden_izlemeden_cikarilabiliyor(client, db, ortam):
    _, ws = ortam()
    kayit = ekle(db, workspace_id=ws.id, platform=Platform.INSTAGRAM,
                 ham_ad="cikacak", tur=IzlemeTuru.RAKIP)
    db.commit()

    yanit = client.post(
        f"/panel/musteri/{ws.id}/hesaplar/izleme-kaldir",
        data={"kayit_id": str(kayit.id)},
    )
    assert yanit.status_code == 200
    assert listele(db, ws.id) == []


def test_izin_yoksa_izlemeye_eklenemiyor(client, db, ortam):
    """Izleyicinin 'hesap.izle' izni yok; sunucu reddetmeli."""
    _, ws = ortam(PermissionPackage.VIEWER)
    yanit = client.post(
        f"/panel/musteri/{ws.id}/hesaplar/izle",
        data={"platform": "instagram", "kullanici_adi": "rakip", "tur": "rakip"},
    )
    assert yanit.status_code == 403
    assert listele(db, ws.id) == []


def test_panelde_veri_cekilmedigi_acikca_yaziyor(client, db, ortam):
    """'Yakinda' denmez; neyin CALISMADIGI yazilir."""
    _, ws = ortam()
    ekle(db, workspace_id=ws.id, platform=Platform.INSTAGRAM,
         ham_ad="rakip", tur=IzlemeTuru.RAKIP)
    db.commit()

    sayfa = client.get(f"/panel/musteri/{ws.id}/hesaplar")
    assert "otomatik veri çekilmiyor" in sayfa.text


# --- Teshis -------------------------------------------------------------------

def test_baglanti_teshisi_gosteriliyor(client, ortam):
    """Kullanici Instagram'in hata sayfasina duserse elinde bilgi olsun."""
    _, ws = ortam()
    sayfa = client.get(f"/panel/musteri/{ws.id}/hesaplar")
    assert sayfa.status_code == 200
    assert "Bağlantı ayarları (teşhis)" in sayfa.text
    assert "İzin adresi" in sayfa.text
    assert "Invalid platform app" in sayfa.text


def test_teshiste_gizli_anahtar_yok(client, db, ortam, monkeypatch):
    """App Secret ekranda ASLA gorunmemeli."""
    from app.platforms import meta_ayar as ayar_modulu

    gercek = ayar_modulu.meta_ayarlarini_oku

    def _sahte():
        a = gercek()
        object.__setattr__(a, "app_secret", "COK-GIZLI-DEGER-12345")
        return a

    monkeypatch.setattr(ayar_modulu, "meta_ayarlarini_oku", _sahte)
    monkeypatch.setattr("app.panel.routes.meta_ayarlarini_oku", _sahte)

    _, ws = ortam()
    sayfa = client.get(f"/panel/musteri/{ws.id}/hesaplar")
    assert "COK-GIZLI-DEGER-12345" not in sayfa.text
