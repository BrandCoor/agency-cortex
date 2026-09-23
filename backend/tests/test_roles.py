"""Rol ve yetki testleri."""

from __future__ import annotations

import pytest

from app.models.enums import WorkspaceRole


def test_rol_siralamasi_dogru():
    assert WorkspaceRole.OWNER.covers(WorkspaceRole.ADMIN)
    assert WorkspaceRole.ADMIN.covers(WorkspaceRole.EDITOR)
    assert WorkspaceRole.STRATEGIST.covers(WorkspaceRole.VIEWER)
    assert not WorkspaceRole.VIEWER.covers(WorkspaceRole.EDITOR)
    assert not WorkspaceRole.EDITOR.covers(WorkspaceRole.ADMIN)
    # Her rol kendi seviyesini karsilar.
    for role in WorkspaceRole:
        assert role.covers(role)


@pytest.fixture
def musteri_ve_uyeler(make_user, make_workspace, add_member):
    ws = make_workspace(name="Rol Testi")
    users = {}
    for role in WorkspaceRole:
        u = make_user(email=f"{role.value}@ajans.com")
        add_member(ws, u, role)
        users[role] = u
    return ws, users


@pytest.mark.parametrize("role", [WorkspaceRole.VIEWER, WorkspaceRole.EDITOR, WorkspaceRole.STRATEGIST])
def test_yetersiz_rol_uye_ekleyemez(client, auth_headers, musteri_ve_uyeler, make_user, role):
    ws, users = musteri_ve_uyeler
    yeni = make_user(email="yeni@ajans.com")

    r = client.post(
        f"/api/v1/workspaces/{ws.id}/members",
        headers=auth_headers(users[role]),
        json={"email": yeni.email, "role": "viewer"},
    )
    assert r.status_code == 403


@pytest.mark.parametrize("role", [WorkspaceRole.ADMIN, WorkspaceRole.OWNER])
def test_yonetici_ve_sahip_uye_ekleyebilir(client, auth_headers, musteri_ve_uyeler, make_user, role):
    ws, users = musteri_ve_uyeler
    yeni = make_user(email=f"eklenen-{role.value}@ajans.com")

    r = client.post(
        f"/api/v1/workspaces/{ws.id}/members",
        headers=auth_headers(users[role]),
        json={"email": yeni.email},
    )
    # Uyelik artik YETKI TASIMAZ; yalnizca erisimi belirler.
    assert r.status_code == 201
    assert r.json()["user_id"] == str(yeni.id)


def test_her_rol_musteriyi_okuyabilir(client, auth_headers, musteri_ve_uyeler):
    ws, users = musteri_ve_uyeler
    for role, user in users.items():
        r = client.get(f"/api/v1/workspaces/{ws.id}", headers=auth_headers(user))
        assert r.status_code == 200, f"{role.value} okuyamadi"


def test_ayni_kullanici_iki_kez_uye_olamaz(client, auth_headers, musteri_ve_uyeler):
    ws, users = musteri_ve_uyeler
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/members",
        headers=auth_headers(users[WorkspaceRole.OWNER]),
        json={"email": users[WorkspaceRole.VIEWER].email},
    )
    assert r.status_code == 409


def test_son_sahip_cikarilamaz(client, auth_headers, db, make_user, make_workspace, add_member):
    """Sahipsiz kalan bir calisma alani yonetilemez hale gelir."""
    ws = make_workspace(name="Tek Sahip")
    sahip = make_user(email="teksahip@ajans.com")
    member = add_member(ws, sahip, WorkspaceRole.OWNER)

    r = client.delete(
        f"/api/v1/workspaces/{ws.id}/members/{member.id}", headers=auth_headers(sahip)
    )
    assert r.status_code == 409


def test_baska_musterinin_uyesi_silinemez(
    client, auth_headers, make_user, make_workspace, add_member
):
    """Uye kimligi dogru olsa bile, baska calisma alanindan silinemez."""
    ws_a = make_workspace(name="A")
    ws_b = make_workspace(name="B")
    ayse = make_user(email="a-sahip@ajans.com")
    bora = make_user(email="b-sahip@ajans.com")
    add_member(ws_a, ayse, WorkspaceRole.OWNER)
    bora_uyelik = add_member(ws_b, bora, WorkspaceRole.OWNER)

    # Ayse kendi calisma alaninda sahip; Bora'nin uyeligini silmeyi deniyor.
    r = client.delete(
        f"/api/v1/workspaces/{ws_a.id}/members/{bora_uyelik.id}", headers=auth_headers(ayse)
    )
    assert r.status_code == 404
