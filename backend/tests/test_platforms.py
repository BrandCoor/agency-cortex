"""Platform adaptoru testleri.

Ana fikir: Bir adaptor yapamadigi isi "yapiyormus gibi" gostermemelidir.
"""

from __future__ import annotations

import pytest

from app.models.enums import Platform
from app.platforms.base import (
    Capability,
    CapabilityNotSupported,
    PlatformNotImplemented,
    PublishingDisabled,
)
from app.platforms.fake import FakeInstagramAdapter
from app.platforms.meta import MetaAdapter, MetaConfigurationIncomplete
from app.platforms.registry import get_adapter, platform_status


def test_gelistirme_modunda_sahte_adaptor_gelir():
    assert isinstance(get_adapter(Platform.INSTAGRAM, mode="fake"), FakeInstagramAdapter)


def test_canli_modda_gercek_adaptor_gelir():
    assert isinstance(get_adapter(Platform.INSTAGRAM, mode="live"), MetaAdapter)


@pytest.mark.parametrize(
    "platform",
    [Platform.TIKTOK, Platform.YOUTUBE, Platform.LINKEDIN, Platform.X, Platform.PINTEREST],
)
def test_gelistirilmemis_platformlar_acik_hata_verir(platform):
    """Sessizce bos sonuc donmek yerine acikca 'yok' demeli."""
    adapter = get_adapter(platform)
    assert adapter.capabilities == frozenset()
    with pytest.raises(PlatformNotImplemented):
        adapter.authorize(state="s", redirect_uri="https://ornek.com")
    assert adapter.health_check().ok is False


def test_meta_adaptoru_ayarsizken_hazir_gorunmez():
    """Meta ayarlari doldurulmadan adaptor 'calisiyor' dememeli.

    Adaptorun akisi yazildi, ancak Meta'ya ozgu adresler ve izin adlari
    ayarlardan gelir. Ayar eksikken hicbir yetenek bildirilmez.
    Ayrintili testler: tests/test_meta_oauth.py
    """
    adapter = MetaAdapter()
    assert adapter.capabilities == frozenset()
    assert adapter.health_check().ok is False
    with pytest.raises(MetaConfigurationIncomplete):
        adapter.authorize(state="s", redirect_uri="https://ornek.com")


def test_platform_durumu_durustce_raporlanir():
    rows = {r["platform"]: r for r in platform_status()}
    # Gelistirilmemis platformlar available=False olmali.
    for name in ("tiktok", "youtube", "linkedin", "x", "pinterest"):
        assert rows[name]["available"] is False
        assert rows[name]["capabilities"] == []


def test_desteklenmeyen_is_acik_hata_verir():
    adapter = FakeInstagramAdapter()
    assert not adapter.supports(Capability.PUBLISH_DRAFT)


def test_yayinlama_kilidi_calisir():
    """Ilk surumde yayin KAPALI. Kilit adaptorun icinde, atlanamaz."""
    adapter = FakeInstagramAdapter()
    with pytest.raises(PublishingDisabled):
        adapter.publish_draft_if_enabled(
            access_token="t", account_external_id="a", payload={}
        )


def test_kilit_acilsa_bile_yetenek_yoksa_yayin_yapilamaz(monkeypatch):
    """Guvenlik katmanlari birbirini yedekler: kilit acilsa bile
    adaptor bu isi desteklemedigi icin yayin gerceklesmez."""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "feature_publishing_enabled", True)

    adapter = FakeInstagramAdapter()
    with pytest.raises(CapabilityNotSupported):
        adapter.publish_draft_if_enabled(
            access_token="t", account_external_id="a", payload={}
        )


# --- Sahte adaptorun kendi davranisi ---

def test_sahte_adaptor_icerik_listeler():
    adapter = FakeInstagramAdapter()
    items = adapter.list_media(access_token="t", account_external_id="hesap1", limit=5)
    assert len(items) == 5
    assert len({i.external_id for i in items}) == 5


def test_sahte_veri_her_calistirmada_ayni():
    """Testlerin guvenilir olmasi icin sahte veri rastgele olmamali."""
    a = FakeInstagramAdapter().fetch_media_metrics(access_token="t", media_external_id="m1")
    b = FakeInstagramAdapter().fetch_media_metrics(access_token="t", media_external_id="m1")
    assert [(p.metric_name, p.value) for p in a] == [(p.metric_name, p.value) for p in b]


def test_farkli_icerik_farkli_deger_uretir():
    a = FakeInstagramAdapter().fetch_media_metrics(access_token="t", media_external_id="m1")
    b = FakeInstagramAdapter().fetch_media_metrics(access_token="t", media_external_id="m2")
    assert [p.value for p in a] != [p.value for p in b]


def test_sahte_hesap_profesyonel_isaretlenir():
    """Kisisel hesaba profesyonel hesap gibi davranilmamali."""
    _, profile = FakeInstagramAdapter().callback(code="abc", redirect_uri="https://ornek.com")
    assert profile.is_professional is True


def test_token_nesnesi_degerlerini_gizler():
    """Anahtar kazara loglanirsa bile icerigi gorunmemeli."""
    tokens, _ = FakeInstagramAdapter().callback(code="abc", redirect_uri="https://ornek.com")
    metin = repr(tokens)
    assert tokens.access_token not in metin
    assert "***" in metin
