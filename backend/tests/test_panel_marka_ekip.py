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

def test_ekip_sayfasi_uyeleri_gosteriyor(client, ortam):
    kullanici, ws = ortam()
    yanit = client.get(f"/panel/musteri/{ws.id}/ekip")
    assert yanit.status_code == 200
    assert kullanici.email in yanit.text


def test_ekibe_kisi_eklenebiliyor(client, db, ortam, make_user):
    _, ws = ortam()
    yeni = make_user(email="editor@ornek.com")

    yanit = client.post(
        f"/panel/musteri/{ws.id}/ekip/ekle",
        data={"email": "Editor@Ornek.com", "rol": "editor"},
    )

    assert yanit.status_code == 200
    uyelik = db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == ws.id, WorkspaceMember.user_id == yeni.id
        )
    ).scalars().one()
    assert uyelik.role == WorkspaceRole.EDITOR


def test_olmayan_kullanici_eklenemiyor(client, ortam):
    _, ws = ortam()
    yanit = client.post(
        f"/panel/musteri/{ws.id}/ekip/ekle",
        data={"email": "yok@ornek.com", "rol": "editor"},
    )
    assert yanit.status_code == 404
    assert "kayıtlı bir kullanıcı yok" in yanit.text


def test_ayni_kisi_iki_kez_eklenemiyor(client, ortam, make_user):
    _, ws = ortam()
    make_user(email="editor@ornek.com")
    veri = {"email": "editor@ornek.com", "rol": "editor"}

    assert client.post(f"/panel/musteri/{ws.id}/ekip/ekle", data=veri).status_code == 200
    ikinci = client.post(f"/panel/musteri/{ws.id}/ekip/ekle", data=veri)
    assert ikinci.status_code == 409
    assert "zaten ekipte" in ikinci.text


def test_kendinden_yuksek_yetki_verilemiyor(client, db, ortam, make_user):
    """Yonetici, birini sahip yapip kendini asamaz."""
    _, ws = ortam(rol=WorkspaceRole.ADMIN)
    make_user(email="hedef@ornek.com")

    yanit = client.post(
        f"/panel/musteri/{ws.id}/ekip/ekle",
        data={"email": "hedef@ornek.com", "rol": "owner"},
    )

    assert yanit.status_code == 403
    assert "yüksek bir yetki veremezsiniz" in yanit.text


def test_stratejist_ekip_yonetemiyor(client, ortam, make_user):
    _, ws = ortam(rol=WorkspaceRole.STRATEGIST)
    make_user(email="hedef@ornek.com")

    yanit = client.post(
        f"/panel/musteri/{ws.id}/ekip/ekle",
        data={"email": "hedef@ornek.com", "rol": "viewer"},
    )
    assert yanit.status_code == 403


def test_kisi_ekipten_cikarilabiliyor(client, db, ortam, make_user, add_member):
    _, ws = ortam()
    hedef = make_user(email="cikacak@ornek.com")
    add_member(ws, hedef, WorkspaceRole.EDITOR)

    yanit = client.post(
        f"/panel/musteri/{ws.id}/ekip/cikar", data={"user_id": str(hedef.id)}
    )

    assert yanit.status_code == 200
    assert db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == ws.id, WorkspaceMember.user_id == hedef.id
        )
    ).scalars().all() == []


def test_kendini_cikaramiyor(client, db, ortam):
    kullanici, ws = ortam()

    yanit = client.post(
        f"/panel/musteri/{ws.id}/ekip/cikar", data={"user_id": str(kullanici.id)}
    )

    assert yanit.status_code == 400
    assert db.execute(
        select(WorkspaceMember).where(WorkspaceMember.user_id == kullanici.id)
    ).scalars().all() != []


def test_kendinden_yuksek_yetkili_cikarilamiyor(client, db, ortam, make_user, add_member):
    _, ws = ortam(rol=WorkspaceRole.ADMIN)
    sahip = make_user(email="sahip@ornek.com")
    add_member(ws, sahip, WorkspaceRole.OWNER)

    yanit = client.post(
        f"/panel/musteri/{ws.id}/ekip/cikar", data={"user_id": str(sahip.id)}
    )

    assert yanit.status_code == 403
    assert db.execute(
        select(WorkspaceMember).where(WorkspaceMember.user_id == sahip.id)
    ).scalars().all() != []


def test_uye_olunmayan_musterinin_ekibi_404(client, make_user, make_workspace):
    kullanici = make_user(password=SIFRE)
    baskasinin = make_workspace(name="Baskasinin")
    _giris(client, kullanici)

    assert client.get(f"/panel/musteri/{baskasinin.id}/ekip").status_code == 404
    assert client.post(
        f"/panel/musteri/{baskasinin.id}/ekip/ekle",
        data={"email": "x@y.com", "rol": "viewer"},
    ).status_code == 404
