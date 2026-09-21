"""Kampanya sayfasi.

Kampanya bir markaya baglidir; marka yoksa kampanya da olusturulamaz.
Tarih mantigi ve calisma alani izolasyonu ayrica test edilir.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app.models.brand import Brand, Campaign
from app.models.enums import WorkspaceRole

SIFRE = "GucluSifre123!"


def _giris(client, kullanici):
    assert client.post(
        "/panel/giris", data={"email": kullanici.email, "password": SIFRE},
        follow_redirects=False,
    ).status_code == 303


@pytest.fixture
def ortam(client, db, make_user, make_workspace, add_member):
    def _kur(rol=WorkspaceRole.OWNER, marka=True):
        kullanici = make_user(password=SIFRE)
        ws = make_workspace(name="Deneme Musterisi")
        add_member(ws, kullanici, rol)
        if marka:
            db.add(Brand(workspace_id=ws.id, name="Deneme Markasi"))
            db.flush()
        _giris(client, kullanici)
        return kullanici, ws

    return _kur


def test_sayfa_aciliyor(client, ortam):
    _, ws = ortam()
    yanit = client.get(f"/panel/musteri/{ws.id}/kampanya")
    assert yanit.status_code == 200
    assert "Kampanyalar" in yanit.text


def test_marka_yoksa_once_marka_isteniyor(client, ortam):
    """Kampanya markaya bagli; marka yokken form gosterilmemeli."""
    _, ws = ortam(marka=False)
    yanit = client.get(f"/panel/musteri/{ws.id}/kampanya")

    assert "marka bilgilerini" in yanit.text
    assert "Kampanya oluştur" not in yanit.text


def test_marka_yokken_kampanya_olusturulamiyor(client, db, ortam):
    _, ws = ortam(marka=False)
    yanit = client.post(f"/panel/musteri/{ws.id}/kampanya", data={"ad": "Ramazan"})

    assert yanit.status_code == 400
    assert db.execute(select(Campaign)).scalars().all() == []


def test_kampanya_olusturuluyor(client, db, ortam):
    _, ws = ortam()

    yanit = client.post(
        f"/panel/musteri/{ws.id}/kampanya",
        data={"ad": "Ramazan 2026", "hedef": "Rezervasyon artisi",
              "baslangic": "2026-02-18", "bitis": "2026-03-19"},
    )

    assert yanit.status_code == 200
    k = db.execute(select(Campaign)).scalars().one()
    assert k.name == "Ramazan 2026"
    assert k.objective == "Rezervasyon artisi"
    assert k.starts_on == dt.date(2026, 2, 18)
    assert k.ends_on == dt.date(2026, 3, 19)
    assert k.workspace_id == ws.id


def test_tarihsiz_kampanya_olusturulabiliyor(client, db, ortam):
    _, ws = ortam()
    yanit = client.post(
        f"/panel/musteri/{ws.id}/kampanya",
        data={"ad": "Surekli", "baslangic": "", "bitis": ""},
    )
    assert yanit.status_code == 200
    k = db.execute(select(Campaign)).scalars().one()
    assert k.starts_on is None and k.ends_on is None


def test_bitis_baslangictan_once_olamaz(client, db, ortam):
    """Sessizce kabul edilirse raporlama anlamsiz sonuc uretir."""
    _, ws = ortam()

    yanit = client.post(
        f"/panel/musteri/{ws.id}/kampanya",
        data={"ad": "Hatali", "baslangic": "2026-03-19", "bitis": "2026-02-18"},
    )

    assert yanit.status_code == 400
    assert "Bitiş tarihi başlangıçtan önce olamaz." in yanit.text
    assert db.execute(select(Campaign)).scalars().all() == []


def test_ayni_gun_baslayip_biten_kampanya_kabul_ediliyor(client, db, ortam):
    _, ws = ortam()
    yanit = client.post(
        f"/panel/musteri/{ws.id}/kampanya",
        data={"ad": "Tek gun", "baslangic": "2026-03-01", "bitis": "2026-03-01"},
    )
    assert yanit.status_code == 200
    assert db.execute(select(Campaign)).scalars().one().name == "Tek gun"


def test_bozuk_tarih_gormezden_geliniyor(client, db, ortam):
    """Tarayici disindan gelen bozuk tarih kampanyayi engellememelidir."""
    _, ws = ortam()
    yanit = client.post(
        f"/panel/musteri/{ws.id}/kampanya",
        data={"ad": "Bozuk tarih", "baslangic": "abc", "bitis": "2026-13-45"},
    )
    assert yanit.status_code == 200
    k = db.execute(select(Campaign)).scalars().one()
    assert k.starts_on is None and k.ends_on is None


def test_kisa_ad_reddediliyor(client, db, ortam):
    _, ws = ortam()
    yanit = client.post(f"/panel/musteri/{ws.id}/kampanya", data={"ad": " x "})
    assert yanit.status_code == 400
    assert db.execute(select(Campaign)).scalars().all() == []


def test_editor_kampanya_olusturamiyor(client, db, ortam):
    _, ws = ortam(rol=WorkspaceRole.EDITOR)
    yanit = client.post(f"/panel/musteri/{ws.id}/kampanya", data={"ad": "Izinsiz"})
    assert yanit.status_code == 403
    assert db.execute(select(Campaign)).scalars().all() == []


def test_kampanya_silinebiliyor(client, db, ortam):
    _, ws = ortam()
    client.post(f"/panel/musteri/{ws.id}/kampanya", data={"ad": "Silinecek"})
    k = db.execute(select(Campaign)).scalars().one()

    yanit = client.post(
        f"/panel/musteri/{ws.id}/kampanya/sil", data={"kampanya_id": str(k.id)}
    )

    assert yanit.status_code == 200
    assert db.execute(select(Campaign)).scalars().all() == []


def test_baska_musterinin_kampanyasi_silinemiyor(
    client, db, ortam, make_workspace
):
    """IZOLASYON: kimligi bilinse bile baska musterinin kaydi silinemez."""
    _, benim = ortam()
    baskasinin = make_workspace(name="Baskasinin")
    marka = Brand(workspace_id=baskasinin.id, name="Onlarin Markasi")
    db.add(marka)
    db.flush()
    gizli = Campaign(workspace_id=baskasinin.id, brand_id=marka.id, name="Gizli Kampanya")
    db.add(gizli)
    db.flush()

    yanit = client.post(
        f"/panel/musteri/{benim.id}/kampanya/sil", data={"kampanya_id": str(gizli.id)}
    )

    assert yanit.status_code == 404
    assert db.get(Campaign, gizli.id) is not None


def test_uye_olunmayan_musteri_404(client, make_user, make_workspace):
    kullanici = make_user(password=SIFRE)
    baskasinin = make_workspace(name="Baskasinin")
    _giris(client, kullanici)

    assert client.get(f"/panel/musteri/{baskasinin.id}/kampanya").status_code == 404
    assert client.post(
        f"/panel/musteri/{baskasinin.id}/kampanya", data={"ad": "X"}
    ).status_code == 404
