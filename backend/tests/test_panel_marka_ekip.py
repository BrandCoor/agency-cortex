"""Marka bilgileri ve ekip yonetimi sayfalari.

Bu iki sayfa daha once yoktu; ajans sahibi marka bilgisi girmek veya ekibine
kisi eklemek icin bana bagimliydi. Yetki sinirlari sunucuda test edilir -
formun kapali gorunmesi tek basina koruma degildir.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.brand import Brand, BrandGuideline
from app.models.enums import WorkspaceRole
from app.models.identity import WorkspaceMember

SIFRE = "GucluSifre123!"


def _giris(client, kullanici):
    yanit = client.post(
        "/panel/giris", data={"email": kullanici.email, "password": SIFRE},
        follow_redirects=False,
    )
    assert yanit.status_code == 303


@pytest.fixture
def ortam(client, db, make_user, make_workspace, add_member):
    def _kur(rol=WorkspaceRole.OWNER):
        kullanici = make_user(password=SIFRE)
        ws = make_workspace(name="Deneme Musterisi")
        add_member(ws, kullanici, rol)
        _giris(client, kullanici)
        return kullanici, ws

    return _kur


# --- Marka bilgileri ---------------------------------------------------------

def test_marka_sayfasi_aciliyor(client, ortam):
    _, ws = ortam()
    yanit = client.get(f"/panel/musteri/{ws.id}/marka")
    assert yanit.status_code == 200
    assert "Marka bilgileri" in yanit.text


def test_marka_kaydediliyor(client, db, ortam):
    _, ws = ortam()

    yanit = client.post(
        f"/panel/musteri/{ws.id}/marka",
        data={
            "ad": "Taha Usta", "sektor": "Restoran", "site": "https://ornek.com",
            "aciklama": "Gaziantep mutfagi", "ton": "Samimi",
            "kitle": "25-45 yas", "yasakli": "dünyanın en iyisi\nbir numara",
            "tercih": "ustalikla", "notlar": "Ramazan onemli",
        },
    )

    assert yanit.status_code == 200
    assert "Marka bilgileri kaydedildi." in yanit.text

    marka = db.execute(select(Brand).where(Brand.workspace_id == ws.id)).scalars().one()
    assert marka.name == "Taha Usta"
    assert marka.sector == "Restoran"

    kilavuz = db.execute(
        select(BrandGuideline).where(BrandGuideline.brand_id == marka.id)
    ).scalars().one()
    # Her satir ayri bir ifade olmali.
    assert kilavuz.forbidden_phrases == ["dünyanın en iyisi", "bir numara"]
    assert kilavuz.preferred_phrases == ["ustalikla"]
    assert kilavuz.target_audience == "25-45 yas"


def test_marka_iki_kez_kaydedilince_cogalmiyor(client, db, ortam):
    """Ikinci kayit yeni marka/kilavuz yaratmamali, mevcutu guncellemeli."""
    _, ws = ortam()
    for ad in ["Ilk Ad", "Ikinci Ad"]:
        client.post(f"/panel/musteri/{ws.id}/marka", data={"ad": ad, "yasakli": ""})

    markalar = db.execute(select(Brand).where(Brand.workspace_id == ws.id)).scalars().all()
    assert len(markalar) == 1
    assert markalar[0].name == "Ikinci Ad"
    kilavuzlar = db.execute(
        select(BrandGuideline).where(BrandGuideline.workspace_id == ws.id)
    ).scalars().all()
    assert len(kilavuzlar) == 1


def test_izleyici_marka_degistiremiyor(client, db, ortam):
    """Formun kapali gorunmesi yetmez; sunucu da reddetmeli."""
    _, ws = ortam(rol=WorkspaceRole.VIEWER)

    yanit = client.post(f"/panel/musteri/{ws.id}/marka", data={"ad": "Izinsiz", "yasakli": ""})

    assert yanit.status_code == 403
    assert db.execute(select(Brand).where(Brand.workspace_id == ws.id)).scalars().all() == []


def test_uye_olunmayan_musterinin_markasi_404(client, make_user, make_workspace):
    kullanici = make_user(password=SIFRE)
    baskasinin = make_workspace(name="Baskasinin")
    _giris(client, kullanici)

    assert client.get(f"/panel/musteri/{baskasinin.id}/marka").status_code == 404
    assert client.post(
        f"/panel/musteri/{baskasinin.id}/marka", data={"ad": "X", "yasakli": ""}
    ).status_code == 404


# --- Ekip --------------------------------------------------------------------
#
# Ekip sayfasi ATAMA yapar, YETKI VERMEZ. Rol secimi kaldirildi: bir
# kisinin neyi yapabilecegi kendi hesabinda tanimlidir (Kullanicilar).

def test_ekip_sayfasi_uyeleri_gosteriyor(client, ortam):
    kullanici, ws = ortam()
    yanit = client.get(f"/panel/musteri/{ws.id}/ekip")
    assert yanit.status_code == 200
    assert kullanici.email in yanit.text


def test_ekip_sayfasinda_rol_secimi_yok(client, ortam):
    """Rol secmek yaniltirdi: yetki musteriye gore degismiyor."""
    _, ws = ortam()
    yanit = client.get(f"/panel/musteri/{ws.id}/ekip")
    assert 'name="rol"' not in yanit.text
    assert "yetki vermez" in yanit.text


def test_ekibe_kisi_atanabiliyor(client, db, ortam, make_user):
    _, ws = ortam()
    yeni = make_user(email="yeni@ajans.com")
    db.commit()

    yanit = client.post(
        f"/panel/musteri/{ws.id}/ekip/ekle", data={"email": "yeni@ajans.com"}
    )
    assert yanit.status_code == 200
    uyelik = db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == ws.id,
            WorkspaceMember.user_id == yeni.id,
        )
    ).scalar_one_or_none()
    assert uyelik is not None


def test_olmayan_kullanici_atanamiyor(client, ortam):
    _, ws = ortam()
    yanit = client.post(
        f"/panel/musteri/{ws.id}/ekip/ekle", data={"email": "yok@ajans.com"}
    )
    assert yanit.status_code == 404
    assert "kayıtlı bir kullanıcı yok" in yanit.text


def test_ayni_kisi_iki_kez_atanamiyor(client, db, ortam, make_user):
    _, ws = ortam()
    make_user(email="tekrar@ajans.com")
    db.commit()
    client.post(f"/panel/musteri/{ws.id}/ekip/ekle", data={"email": "tekrar@ajans.com"})
    ikinci = client.post(
        f"/panel/musteri/{ws.id}/ekip/ekle", data={"email": "tekrar@ajans.com"}
    )
    assert ikinci.status_code == 409


def test_yetkisiz_kisi_ekip_yonetemiyor(client, db, ortam, make_user):
    """Izleyicinin 'ekip.yonet' izni yok; sunucu reddetmeli."""
    _, ws = ortam(WorkspaceRole.VIEWER)
    make_user(email="baskasi@ajans.com")
    db.commit()
    yanit = client.post(
        f"/panel/musteri/{ws.id}/ekip/ekle", data={"email": "baskasi@ajans.com"}
    )
    assert yanit.status_code == 403


def test_kisi_ekipten_cikarilabiliyor(client, db, ortam, make_user, add_member):
    _, ws = ortam()
    baskasi = make_user(email="cikacak@ajans.com")
    add_member(ws, baskasi, WorkspaceRole.EDITOR)
    db.commit()

    yanit = client.post(
        f"/panel/musteri/{ws.id}/ekip/cikar", data={"user_id": str(baskasi.id)}
    )
    assert yanit.status_code == 200
    kalan = db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == ws.id,
            WorkspaceMember.user_id == baskasi.id,
        )
    ).scalar_one_or_none()
    assert kalan is None


def test_kendini_cikaramiyor(client, db, ortam):
    """Kendini cikarmak o musteriye erisimi aninda keserdi."""
    kullanici, ws = ortam()
    yanit = client.post(
        f"/panel/musteri/{ws.id}/ekip/cikar", data={"user_id": str(kullanici.id)}
    )
    assert yanit.status_code == 400
    assert "Kendinizi çıkaramazsınız" in yanit.text


def test_uye_olunmayan_musterinin_ekibi_404(client, make_user, make_workspace):
    kullanici = make_user(password=SIFRE)
    baskasi = make_workspace(name="Baskasinin Musterisi")
    _giris(client, kullanici)
    assert client.get(f"/panel/musteri/{baskasi.id}/ekip").status_code == 404
