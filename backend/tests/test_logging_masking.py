"""Loglarda hassas verinin maskelendigini dogrular.

Bu testler guvenlik testidir: token veya sifre loga duserse musteri verisi
sizabilir.
"""

from __future__ import annotations

from app.core.logging_config import MASK, mask_sensitive


def test_token_ve_sifre_maskelenir():
    out = mask_sensitive(None, "", {"access_token": "gizli123", "password": "abc"})
    assert out["access_token"] == MASK
    assert out["password"] == MASK


def test_ic_ice_sozlukte_de_maskelenir():
    event = {"oauth": {"refresh_token": "r-123", "expires_in": 3600}}
    out = mask_sensitive(None, "", event)
    assert out["oauth"]["refresh_token"] == MASK
    assert out["oauth"]["expires_in"] == 3600  # hassas olmayan veri korunur


def test_liste_icindeki_sozlukler_de_maskelenir():
    event = {"accounts": [{"api_key": "k1"}, {"api_key": "k2"}]}
    out = mask_sensitive(None, "", event)
    assert all(a["api_key"] == MASK for a in out["accounts"])


def test_buyuk_kucuk_harf_farki_onemli_degil():
    out = mask_sensitive(None, "", {"Authorization": "Bearer xyz", "API_KEY": "k"})
    assert out["Authorization"] == MASK
    assert out["API_KEY"] == MASK


def test_normal_alanlar_degismez():
    event = {"workspace_id": 7, "path": "/healthz", "duration_ms": 1.5}
    assert mask_sensitive(None, "", event) == event
