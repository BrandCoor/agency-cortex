"""Saglik kontrolu uclarinin testleri."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import __version__
from app.main import app

client = TestClient(app)


def test_healthz_her_zaman_ok_doner():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_version_yayin_kilidini_bildirir():
    r = client.get("/version")
    assert r.status_code == 200
    body = r.json()
    # Sabit bir metin yerine paketin KENDI surumu ile karsilastiriliyor;
    # aksi halde surum yukseltildiginde bu test, gercek bir hata olmadigi
    # halde patlardi.
    assert body["version"] == __version__
    # Ilk surumde yayin KAPALI olmali. Bu test kilidin kazara acilmasini yakalar.
    assert body["publishing_enabled"] is False


def test_readyz_bagimlilik_yoksa_503_doner(monkeypatch):
    """Veritabani erisilemezse sistem 'hazir' demez."""
    monkeypatch.setattr("app.api.health.check_database", lambda: (False, "baglanti yok"))
    monkeypatch.setattr("app.api.health.check_redis", lambda: (True, None))

    r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json()["status"] == "not_ready"
    assert r.json()["checks"]["database"]["ok"] is False


def test_readyz_her_sey_calisirken_200_doner(monkeypatch):
    monkeypatch.setattr("app.api.health.check_database", lambda: (True, None))
    monkeypatch.setattr("app.api.health.check_redis", lambda: (True, None))

    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_her_yanitta_istek_kimligi_bulunur():
    r = client.get("/healthz")
    assert r.headers.get("x-request-id")
