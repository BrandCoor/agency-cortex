"""MUSTERI IZOLASYONU TESTLERI.

Bu dosya sistemin en kritik guvenlik testidir. Bir ajans musterisinin
verisinin baska bir musteriye sizmasi, kabul edilemez bir hatadir.

Senaryo: Ayse "A Musterisi"nde, Bora "B Musterisi"nde calisiyor.
Bora, A Musterisi'nin hicbir verisine erisememelidir.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.enums import WorkspaceRole


@pytest.fixture
def iki_musteri(make_user, make_workspace, add_member):
    """Iki ayri musteri ve her birinde birer kullanici."""
    ayse = make_user(email="ayse@ajans.com")
    bora = make_user(email="bora@ajans.com")
    musteri_a = make_workspace(name="A Musterisi")
    musteri_b = make_workspace(name="B Musterisi")
    add_member(musteri_a, ayse, WorkspaceRole.OWNER)
    add_member(musteri_b, bora, WorkspaceRole.OWNER)
    return {"ayse": ayse, "bora": bora, "a": musteri_a, "b": musteri_b}


def test_kullanici_yalnizca_kendi_musterisini_listeler(client, auth_headers, iki_musteri):
    r = client.get("/api/v1/workspaces", headers=auth_headers(iki_musteri["bora"]))
    assert r.status_code == 200

    gorulen = [item["workspace"]["name"] for item in r.json()]
    assert gorulen == ["B Musterisi"]
    assert "A Musterisi" not in gorulen


def test_baska_musterinin_ayrintisi_gorulemez(client, auth_headers, iki_musteri):
    """Bora, A Musterisi'nin kimligini bilse bile erisemez."""
    r = client.get(
        f"/api/v1/workspaces/{iki_musteri['a'].id}",
        headers=auth_headers(iki_musteri["bora"]),
    )
    # 403 degil 404: "yetkiniz yok" demek, o musterinin VAR OLDUGUNU ele verir.
    assert r.status_code == 404


def test_baska_musterinin_uyeleri_gorulemez(client, auth_headers, iki_musteri):
    r = client.get(
        f"/api/v1/workspaces/{iki_musteri['a'].id}/members",
        headers=auth_headers(iki_musteri["bora"]),
    )
    assert r.status_code == 404


def test_baska_musteriye_uye_eklenemez(client, auth_headers, iki_musteri):
    r = client.post(
        f"/api/v1/workspaces/{iki_musteri['a'].id}/members",
        headers=auth_headers(iki_musteri["bora"]),
        json={"email": "bora@ajans.com", "role": "admin"},
    )
    assert r.status_code == 404


def test_var_olmayan_musteri_de_ayni_yaniti_verir(client, auth_headers, iki_musteri):
    """Var olan ama yetkisiz bir musteri ile hic var olmayan musteri
    AYNI yaniti vermelidir. Farkli yanit, musteri varliginin ele verilmesidir."""
    yetkisiz = client.get(
        f"/api/v1/workspaces/{iki_musteri['a'].id}",
        headers=auth_headers(iki_musteri["bora"]),
    )
    olmayan = client.get(
        f"/api/v1/workspaces/{uuid.uuid4()}",
        headers=auth_headers(iki_musteri["bora"]),
    )
    assert yetkisiz.status_code == olmayan.status_code == 404
    assert yetkisiz.json() == olmayan.json()


def test_sistem_yoneticisi_otomatik_erisim_kazanmaz(
    client, auth_headers, make_user, make_workspace, db
):
    """`is_superuser` olmak, musteri verisine erisim VERMEZ.

    Erisim yalnizca acik uyelikle olur. Bu, bir yonetici hesabinin ele
    gecirilmesi durumunda tum musteri verisinin acilmasini engeller.
    """
    yonetici = make_user(email="sistem@ajans.com")
    yonetici.is_superuser = True
    db.flush()
    musteri = make_workspace(name="Gizli Musteri")

    r = client.get(f"/api/v1/workspaces/{musteri.id}", headers=auth_headers(yonetici))
    assert r.status_code == 404


def test_oturumsuz_erisim_reddedilir(client, iki_musteri):
    assert client.get("/api/v1/workspaces").status_code == 401
    assert client.get(f"/api/v1/workspaces/{iki_musteri['a'].id}").status_code == 401


def test_gecersiz_oturum_anahtari_reddedilir(client, iki_musteri):
    r = client.get(
        "/api/v1/workspaces", headers={"Authorization": "Bearer uydurma-anahtar"}
    )
    assert r.status_code == 401


def test_uyelik_kaldirilinca_erisim_biter(client, auth_headers, iki_musteri, db):
    """Uyelik silindiginde kullanici aninda erisimini kaybeder."""
    from sqlalchemy import select

    from app.models.identity import WorkspaceMember

    ws_id = iki_musteri["b"].id
    assert client.get(
        f"/api/v1/workspaces/{ws_id}", headers=auth_headers(iki_musteri["bora"])
    ).status_code == 200

    member = db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == ws_id,
            WorkspaceMember.user_id == iki_musteri["bora"].id,
        )
    ).scalar_one()
    db.delete(member)
    db.flush()

    assert client.get(
        f"/api/v1/workspaces/{ws_id}", headers=auth_headers(iki_musteri["bora"])
    ).status_code == 404


def test_pasif_kullanici_giris_yapamaz(client, auth_headers, iki_musteri, db):
    iki_musteri["bora"].is_active = False
    db.flush()

    r = client.get("/api/v1/workspaces", headers=auth_headers(iki_musteri["bora"]))
    assert r.status_code == 401
