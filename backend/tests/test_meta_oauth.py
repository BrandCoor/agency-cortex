"""Meta OAuth ve webhook kabul testleri.

Bu testler, Meta rehberindeki kabul kriterlerini karsilar. Gercek Meta
hesabi OLMADAN calisirlar.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import pytest

from app.models.enums import WorkspaceRole
from app.platforms.base import PlatformError
from app.platforms.meta import MetaAdapter, MetaConfigurationIncomplete
from app.platforms.meta_ayar import MetaAyarlari
from app.services.oauth_state import StateError, consume_state, create_state
from app.services.webhook_guard import record_event, verify_signature, verify_token_matches

# ---------------------------------------------------------------------------
# 1. Ayar eksikken acik ve anlasilir hata
# ---------------------------------------------------------------------------

def test_ayar_eksikken_adaptor_hazir_gorunmez():
    adapter = MetaAdapter()
    assert adapter.is_configured is False
    assert adapter.capabilities == frozenset()
    assert adapter.health_check().ok is False


def test_ayar_eksikken_acik_hata_verir():
    adapter = MetaAdapter()
    with pytest.raises(MetaConfigurationIncomplete) as exc:
        adapter.authorize(state="s", redirect_uri="https://ornek.com/cb")
    # Hata mesaji hangi ayarlarin eksik oldugunu ACIKCA soylemeli.
    assert "META_APP_ID" in str(exc.value)
    assert "docs/platforms/meta.md" in str(exc.value)


def _dolu_ayar(**degisiklik) -> MetaAyarlari:
    varsayilan = dict(
        app_id="123", app_secret="gizli", redirect_uri="https://x/cb",
        api_version="vXX.0", authorize_url="https://ornek/authorize",
        token_url="https://ornek/token", graph_base_url="https://ornek/graph",
        scopes=["izin_a", "izin_b"],
    )
    varsayilan.update(degisiklik)
    return MetaAyarlari(**varsayilan)


def test_ayarlar_tamamlaninca_yetenekler_acilir():
    """Ayarlar doldurulunca adaptor calisir hale gelir; kod degismez."""
    adapter = MetaAdapter(ayarlar=_dolu_ayar())

    assert adapter.is_configured is True
    assert adapter.health_check().ok is True
    assert len(adapter.capabilities) == 5
    # Ilk surumde YAZMA yetenekleri acilmaz.
    from app.platforms.base import Capability

    assert Capability.PUBLISH_DRAFT not in adapter.capabilities
    assert Capability.FETCH_COMMENTS not in adapter.capabilities


def test_izin_adresi_ayarlardan_uretilir():
    dolu = _dolu_ayar(
        app_id="app123",
        redirect_uri="https://agencycortex.tech/api/v1/oauth/meta/callback",
    )
    adapter = MetaAdapter(ayarlar=dolu)

    istek = adapter.authorize(state="abc123", redirect_uri=dolu.redirect_uri)
    assert istek.url.startswith("https://ornek/authorize?")
    assert "client_id=app123" in istek.url
    assert "state=abc123" in istek.url
    assert "izin_a" in istek.url
    # Gizli anahtar izin adresine ASLA konulmaz.
    assert "gizli" not in istek.url


def test_bos_kod_reddedilir():
    adapter = MetaAdapter(ayarlar=_dolu_ayar())
    with pytest.raises(PlatformError):
        adapter.callback(code="", redirect_uri="https://x/cb")


# ---------------------------------------------------------------------------
# 2-5. State uretimi, dogrulamasi ve tek kullanimlik olmasi
# ---------------------------------------------------------------------------

def test_state_uretilir_ve_dogrulanir():
    ws_id, user_id = uuid.uuid4(), uuid.uuid4()
    state = create_state(
        workspace_id=ws_id, user_id=user_id, platform="instagram",
        redirect_uri="https://ornek/cb",
    )
    assert len(state) > 20  # tahmin edilemez olmali

    payload = consume_state(state)
    assert payload.workspace_id == ws_id
    assert payload.user_id == user_id


def test_state_tek_kullanimliktir():
    """Ayni geri donus ikinci kez islenememeli (replay korumasi)."""
    state = create_state(
        workspace_id=uuid.uuid4(), user_id=uuid.uuid4(),
        platform="instagram", redirect_uri="https://ornek/cb",
    )
    consume_state(state)

    with pytest.raises(StateError):
        consume_state(state)


def test_bilinmeyen_state_reddedilir():
    with pytest.raises(StateError):
        consume_state("bu-state-hic-uretilmedi")


def test_bos_state_reddedilir():
    with pytest.raises(StateError):
        consume_state("")


def test_her_state_benzersizdir():
    olusturulan = {
        create_state(
            workspace_id=uuid.uuid4(), user_id=uuid.uuid4(),
            platform="instagram", redirect_uri="https://ornek/cb",
        )
        for _ in range(20)
    }
    assert len(olusturulan) == 20


# ---------------------------------------------------------------------------
# 14-15. Webhook imzasi ve tekrar korumasi
# ---------------------------------------------------------------------------

def _imzala(govde: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), govde, hashlib.sha256).hexdigest()


def test_dogru_imza_kabul_edilir():
    govde = b'{"object":"instagram"}'
    assert verify_signature(
        payload=govde, header_value=_imzala(govde, "sir"), app_secret="sir"
    )


def test_yanlis_secret_ile_imza_reddedilir():
    govde = b'{"object":"instagram"}'
    assert not verify_signature(
        payload=govde, header_value=_imzala(govde, "yanlis"), app_secret="sir"
    )


def test_govde_degistirilirse_imza_gecersizlesir():
    imza = _imzala(b'{"tutar":100}', "sir")
    assert not verify_signature(
        payload=b'{"tutar":999}', header_value=imza, app_secret="sir"
    )


def test_imza_basligi_yoksa_reddedilir():
    assert not verify_signature(payload=b"{}", header_value=None, app_secret="sir")


def test_yanlis_algoritma_reddedilir():
    assert not verify_signature(
        payload=b"{}", header_value="sha1=abcdef", app_secret="sir"
    )


def test_secret_bossa_reddedilir():
    """Secret ayarlanmamissa imza dogrulanmis SAYILMAZ."""
    govde = b"{}"
    assert not verify_signature(
        payload=govde, header_value=_imzala(govde, ""), app_secret=""
    )


def test_verify_token_karsilastirmasi():
    assert verify_token_matches(sent="dogru", expected="dogru")
    assert not verify_token_matches(sent="yanlis", expected="dogru")
    assert not verify_token_matches(sent=None, expected="dogru")
    assert not verify_token_matches(sent="dogru", expected="")


def test_ayni_webhook_iki_kez_islenmez(db):
    """Meta ayni bildirimi tekrar gonderirse ikinci kez islenmemeli."""
    payload = {"object": "instagram", "entry": [{"id": "1", "time": 100}]}

    _, yeni_1 = record_event(
        db, provider="meta", external_event_id="1:100",
        payload=payload, signature_valid=True,
    )
    db.flush()
    _, yeni_2 = record_event(
        db, provider="meta", external_event_id="1:100",
        payload=payload, signature_valid=True,
    )

    assert yeni_1 is True
    assert yeni_2 is False, "Ayni olay iki kez islendi"


def test_farkli_olaylar_ayri_islenir(db):
    _, y1 = record_event(
        db, provider="meta", external_event_id="1:100", payload={}, signature_valid=True
    )
    db.flush()
    _, y2 = record_event(
        db, provider="meta", external_event_id="1:200", payload={}, signature_valid=True
    )
    assert y1 is True and y2 is True


# ---------------------------------------------------------------------------
# Uc seviyesi testleri
# ---------------------------------------------------------------------------

def test_webhook_yanlis_verify_token_reddedilir(client):
    r = client.get(
        "/api/v1/webhooks/meta",
        params={"hub.mode": "subscribe", "hub.challenge": "1234",
                "hub.verify_token": "yanlis-token"},
    )
    assert r.status_code == 403


def test_webhook_imzasiz_post_reddedilir(client):
    r = client.post("/api/v1/webhooks/meta", json={"object": "instagram"})
    assert r.status_code == 401


def test_webhook_sahte_imza_reddedilir(client):
    govde = json.dumps({"object": "instagram"}).encode()
    r = client.post(
        "/api/v1/webhooks/meta",
        content=govde,
        headers={"x-hub-signature-256": "sha256=" + "0" * 64,
                 "content-type": "application/json"},
    )
    assert r.status_code == 401


def test_ayar_eksikken_baglama_akisi_baslatilmaz(
    client, auth_headers, make_user, make_workspace, add_member
):
    """META_REDIRECT_URI yoksa sistem 'calisiyormus gibi' yapmamali."""
    user = make_user(email="baglama@ajans.com")
    ws = make_workspace(name="Baglama Testi")
    add_member(ws, user, WorkspaceRole.OWNER)

    r = client.post(
        f"/api/v1/oauth/instagram/authorize/{ws.id}", headers=auth_headers(user)
    )
    assert r.status_code == 503
    assert "META_REDIRECT_URI" in r.json()["detail"]


def test_callback_eksik_parametreyle_panele_donuyor(client):
    """400 + ham JSON DEGIL: tarayiciya okunabilir bir sayfa."""
    r = client.get("/api/v1/oauth/meta/callback", follow_redirects=False)
    assert r.status_code == 303
    assert "/panel" in r.headers["location"]


def test_callback_statesiz_hatada_sebebi_gosteriyor(client):
    """State yoksa HANGI musteri oldugunu bilemeyiz - ama bu, ham JSON
    gostermenin gerekcesi degildir. Musteri listesine, Meta'nin kendi
    mesajiyla birlikte doneriz."""
    from urllib.parse import parse_qs, urlparse

    r = client.get(
        "/api/v1/oauth/meta/callback",
        params={"error": "access_denied", "error_description": "Kullanici izin vermedi"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    sorgu = parse_qs(urlparse(r.headers["location"]).query)
    assert "Kullanici izin vermedi" in sorgu["hata"][0]


def test_callback_kullanici_reddederse_panele_donuyor(client, make_user, make_workspace):
    """Bu uca TARAYICI gelir; ekranda ham JSON hatasi gorunmemeli."""
    user = make_user()
    ws = make_workspace(name="Reddedilen")
    state = create_state(
        workspace_id=ws.id, user_id=user.id, platform="instagram",
        redirect_uri="https://ornek/cb",
    )

    r = client.get(
        "/api/v1/oauth/meta/callback",
        params={
            "state": state,
            "error": "access_denied",
            "error_description": "Kullanici izin vermedi",
        },
        follow_redirects=False,
    )

    assert r.status_code == 303
    hedef = r.headers["location"]
    assert hedef.startswith(f"/panel/musteri/{ws.id}/hesaplar")
    assert "hata=" in hedef

    # State TUKETILDI: ayni donus ikinci kez islenemez.
    with pytest.raises(StateError):
        consume_state(state)


def test_callback_gecersiz_state_panele_donuyor(client):
    """Suresi dolmus veya kullanilmis state NORMAL kullanimda da olur
    (geri tusu, sayfa yenileme); ham JSON gosterilmez."""
    r = client.get(
        "/api/v1/oauth/meta/callback",
        params={"code": "abc", "state": "uydurma-state"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "hata=" in r.headers["location"]


def test_yetkisiz_kullanici_hesap_baglayamaz(
    client, auth_headers, make_user, make_workspace, add_member
):
    """Hesap baglamak en az yonetici yetkisi gerektirir."""
    user = make_user(email="izleyici@ajans.com")
    ws = make_workspace(name="Yetki Testi")
    add_member(ws, user, WorkspaceRole.VIEWER)

    r = client.post(
        f"/api/v1/oauth/instagram/authorize/{ws.id}", headers=auth_headers(user)
    )
    assert r.status_code == 403


def test_baska_musterinin_hesabi_baglanamaz(
    client, auth_headers, make_user, make_workspace, add_member
):
    ayse = make_user(email="a@ajans.com")
    ws_a = make_workspace(name="A")
    ws_b = make_workspace(name="B")
    add_member(ws_a, ayse, WorkspaceRole.OWNER)

    r = client.post(
        f"/api/v1/oauth/instagram/authorize/{ws_b.id}", headers=auth_headers(ayse)
    )
    assert r.status_code == 404


# --- Donus ekraninda HAM JSON gorunmez ---------------------------------------
#
# Bu uca TARAYICI gelir (Meta yonlendirir). Ekranda {"detail": ...} gormek
# kullaniciya hicbir sey anlatmaz ve sistemi bozuk gosterir.
#
# 23 Eylul'de kullanici tam bunu gordu:
#   {"detail": "Eksik parametre: 'state' zorunludur."}
# Fonksiyonun kendi aciklamasi "ham hata JSON'u gorunmez" diyordu; ilk
# satiri ise tam olarak onu yapiyordu.

CALLBACK = "/api/v1/oauth/meta/callback"


def test_statesiz_donus_ham_json_gostermiyor(client):
    yanit = client.get(CALLBACK, follow_redirects=False)

    assert yanit.status_code == 303
    assert "/panel" in yanit.headers["location"]
    assert "detail" not in yanit.text


def test_statesiz_donusun_sebebi_yaziyor(client):
    yanit = client.get(CALLBACK, follow_redirects=False)
    from urllib.parse import parse_qs, urlparse

    sorgu = parse_qs(urlparse(yanit.headers["location"]).query)
    assert "hata" in sorgu
    assert "tanınmadı" in sorgu["hata"][0]


def test_statesiz_hatada_metanin_mesaji_aynen_gecer(client):
    """Meta'nin kendi mesaji en degerli bilgi; gizlenmemeli."""
    yanit = client.get(
        CALLBACK,
        params={"error": "access_denied", "error_description": "Invalid platform app"},
        follow_redirects=False,
    )
    from urllib.parse import parse_qs, urlparse

    sorgu = parse_qs(urlparse(yanit.headers["location"]).query)
    assert "Invalid platform app" in sorgu["hata"][0]


def test_gecersiz_state_ham_json_gostermiyor(client):
    yanit = client.get(
        CALLBACK, params={"state": "boyle-bir-state-yok"}, follow_redirects=False
    )
    assert yanit.status_code == 303
    assert "detail" not in yanit.text
    assert "hata=" in yanit.headers["location"]


def test_panel_hatayi_gercekten_gosteriyor(client, db, make_user):
    """Mesaj adrese konsa da sayfa okumuyorsa SESSIZCE kaybolurdu."""
    from app.panel.auth import COOKIE_NAME  # noqa: F401

    kullanici = make_user(password="GucluSifre123!")
    db.commit()
    client.post(
        "/panel/giris",
        data={"email": kullanici.email, "password": "GucluSifre123!"},
        follow_redirects=False,
    )

    sayfa = client.get("/panel", params={"hata": "Deneme mesaji 42"})
    assert sayfa.status_code == 200
    assert "Deneme mesaji 42" in sayfa.text
