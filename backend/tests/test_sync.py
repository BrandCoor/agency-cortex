"""Veri senkronizasyonu testleri.

En kritik kural: AYNI IS IKI KEZ CALISIRSA SAYILAR SISMEMELI.
Bir is yarida kalip yeniden baslarsa, veya zamanlayici ayni isi tekrar
tetiklerse, musteri raporlarinda iki katina cikmis sahte rakamlar olusamaz.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models.enums import Platform
from app.models.social import (
    AccountMetrics,
    MediaMetricsNormalized,
    MediaMetricsRaw,
    PlatformMedia,
    SocialAccount,
)
from app.platforms.fake import FakeInstagramAdapter
from app.services.sync import payload_hash, sync_social_account
from app.services.token_store import load_tokens, save_tokens


@pytest.fixture
def hesap(db, make_workspace):
    """Sahte anahtari kayitli, senkronize edilmeye hazir bir hesap."""
    ws = make_workspace(name="Senkron Testi")
    account = SocialAccount(
        workspace_id=ws.id,
        platform=Platform.INSTAGRAM,
        external_id="ig_test_hesap_1",
        username="test_markasi",
        is_professional=True,
    )
    db.add(account)
    db.flush()

    adapter = FakeInstagramAdapter()
    tokens, _ = adapter.callback(code="deneme", redirect_uri="https://ornek.com")
    save_tokens(db, workspace_id=ws.id, social_account_id=account.id, tokens=tokens)
    db.flush()
    return account


def _say(db, model, workspace_id) -> int:
    return db.execute(
        select(func.count()).select_from(model).where(model.workspace_id == workspace_id)
    ).scalar_one()


def test_senkron_veri_ceker(db, hesap):
    result = sync_social_account(db, account=hesap, adapter=FakeInstagramAdapter(), media_limit=5)

    assert result.media_seen == 5
    assert result.media_created == 5
    assert result.metrics_written > 0
    assert result.errors == []
    assert _say(db, PlatformMedia, hesap.workspace_id) == 5


def test_iki_kez_calisinca_veri_katlanmaz(db, hesap):
    """SISTEMIN EN KRITIK TESTI.

    Ayni senkronizasyon iki kez calistirildiginda icerik ve olcum sayisi
    AYNI kalmali. Katlanirsa musteri raporlari yalan soyler.
    """
    ws_id = hesap.workspace_id
    adapter = FakeInstagramAdapter()

    sync_social_account(db, account=hesap, adapter=adapter, media_limit=5)
    db.flush()
    medya_1 = _say(db, PlatformMedia, ws_id)
    olcum_1 = _say(db, MediaMetricsNormalized, ws_id)
    ham_1 = _say(db, MediaMetricsRaw, ws_id)
    hesap_olcum_1 = _say(db, AccountMetrics, ws_id)

    # Ayni is tekrar calisiyor
    ikinci = sync_social_account(db, account=hesap, adapter=adapter, media_limit=5)
    db.flush()

    assert _say(db, PlatformMedia, ws_id) == medya_1
    assert _say(db, MediaMetricsNormalized, ws_id) == olcum_1
    assert _say(db, AccountMetrics, ws_id) == hesap_olcum_1
    # Ham veri de tekrar yazilmadi; ayni yanit oldugu tespit edildi.
    assert _say(db, MediaMetricsRaw, ws_id) == ham_1
    assert ikinci.media_created == 0
    assert ikinci.raw_skipped_duplicate > 0


def test_ucuncu_calistirma_da_guvenli(db, hesap):
    adapter = FakeInstagramAdapter()
    for _ in range(3):
        sync_social_account(db, account=hesap, adapter=adapter, media_limit=3)
        db.flush()
    assert _say(db, PlatformMedia, hesap.workspace_id) == 3


def test_ham_veri_saklanir_ve_normalize_veriye_baglidir(db, hesap):
    """Normalize veri her zaman ham veriye kadar izlenebilmeli."""
    sync_social_account(db, account=hesap, adapter=FakeInstagramAdapter(), media_limit=2)
    db.flush()

    olcumler = db.execute(
        select(MediaMetricsNormalized).where(
            MediaMetricsNormalized.workspace_id == hesap.workspace_id
        )
    ).scalars().all()

    assert olcumler
    for o in olcumler:
        assert o.raw_reference_id is not None, "Normalize olcum ham veriye bagli degil"


def test_anahtar_yoksa_senkron_sessizce_basarili_olmaz(db, make_workspace):
    """Anahtar yoksa 'sifir veri' degil, ACIK HATA donmeli.

    Aksi halde rapor 'erisim 0' der ve bu gercek bir sifir sanilir.
    """
    ws = make_workspace(name="Anahtarsiz")
    account = SocialAccount(
        workspace_id=ws.id, platform=Platform.INSTAGRAM, external_id="anahtarsiz_hesap"
    )
    db.add(account)
    db.flush()

    result = sync_social_account(db, account=account, adapter=FakeInstagramAdapter())

    assert result.errors, "Anahtar yokken hata bildirilmedi"
    assert result.media_seen == 0
    assert account.sync_error is not None


def test_senkron_baska_musteriye_veri_yazmaz(db, hesap, make_workspace):
    """Senkronizasyon yalnizca kendi calisma alanina yazmali."""
    diger = make_workspace(name="Ilgisiz Musteri")
    sync_social_account(db, account=hesap, adapter=FakeInstagramAdapter(), media_limit=4)
    db.flush()

    assert _say(db, PlatformMedia, diger.id) == 0
    assert _say(db, MediaMetricsNormalized, diger.id) == 0


def test_basarili_senkron_zamani_kaydedilir(db, hesap):
    assert hesap.last_synced_at is None
    sync_social_account(db, account=hesap, adapter=FakeInstagramAdapter(), media_limit=2)
    assert hesap.last_synced_at is not None
    assert hesap.sync_error is None


# --- Parmak izi ---

def test_ayni_icerik_ayni_parmak_izini_uretir():
    a = {"b": 2, "a": 1}
    b = {"a": 1, "b": 2}   # anahtar sirasi farkli, icerik ayni
    assert payload_hash(a) == payload_hash(b)


def test_farkli_icerik_farkli_parmak_izi_uretir():
    assert payload_hash({"a": 1}) != payload_hash({"a": 2})


# --- Sifreli anahtar saklama ---

def test_anahtar_veritabaninda_duz_metin_degil(db, hesap):
    from app.models.social import OAuthCredential

    cred = db.execute(
        select(OAuthCredential).where(OAuthCredential.social_account_id == hesap.id)
    ).scalar_one()

    tokens = load_tokens(db, workspace_id=hesap.workspace_id, social_account_id=hesap.id)
    assert tokens is not None
    # Sifreli metin, cozulmus anahtari icermemeli.
    assert tokens.access_token not in cred.access_token_encrypted


def test_anahtar_geri_cozulebilir(db, hesap):
    tokens = load_tokens(db, workspace_id=hesap.workspace_id, social_account_id=hesap.id)
    assert tokens is not None
    assert tokens.access_token.startswith("sahte-erisim-anahtari-")
    assert tokens.refresh_token is not None


def test_baska_musteri_anahtari_okuyamaz(db, hesap, make_workspace):
    """Calisma alani kimligi uyusmuyorsa anahtar donmemeli."""
    diger = make_workspace(name="Yabanci")
    assert load_tokens(db, workspace_id=diger.id, social_account_id=hesap.id) is None
