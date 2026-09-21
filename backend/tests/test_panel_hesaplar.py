"""Bagli hesaplar sayfasi.

EN ONEMLI KURAL: "Bagla" dugmesi yalnizca platform GERCEKTEN hazirsa
gosterilmeli. Hazir olmayan platformda calismayan bir dugme gostermek,
kullaniciya olmayan bir yetenek varmis gibi sunmaktir.
"""

from __future__ import annotations

import pytest

from app.models.enums import Platform, WorkspaceRole
from app.models.social import SocialAccount

SIFRE = "GucluSifre123!"


def _giris(client, kullanici):
    assert client.post(
        "/panel/giris", data={"email": kullanici.email, "password": SIFRE},
        follow_redirects=False,
    ).status_code == 303


@pytest.fixture
def ortam(client, db, make_user, make_workspace, add_member):
    def _kur(rol=WorkspaceRole.OWNER):
        kullanici = make_user(password=SIFRE)
        ws = make_workspace(name="Deneme Musterisi")
        add_member(ws, kullanici, rol)
        _giris(client, kullanici)
        return kullanici, ws

    return _kur


def test_sayfa_aciliyor(client, ortam):
    _, ws = ortam()
    yanit = client.get(f"/panel/musteri/{ws.id}/hesaplar")
    assert yanit.status_code == 200
    assert "Bağlı hesaplar" in yanit.text


def test_hesap_yokken_acikca_soyluyor(client, ortam):
    _, ws = ortam()
    yanit = client.get(f"/panel/musteri/{ws.id}/hesaplar")
    assert "Henüz bağlı hesap yok." in yanit.text


def test_bagli_hesap_gosteriliyor(client, db, ortam):
    _, ws = ortam()
    db.add(SocialAccount(
        workspace_id=ws.id, platform=Platform.INSTAGRAM,
        external_id="123", username="taha_usta", display_name="Taha Usta",
        is_professional=True,
    ))
    db.flush()

    yanit = client.get(f"/panel/musteri/{ws.id}/hesaplar")

    assert "taha_usta" in yanit.text
    assert "profesyonel hesap" in yanit.text
    # Hic veri cekilmediyse bu acikca yazmali.
    assert "henüz hiç veri çekilmedi" in yanit.text


def test_sahte_modda_bagla_dugmesi_gosterilmiyor(client, ortam):
    """Sahte saglayici ile gercek hesap baglanamaz; dugme gosterilmemeli."""
    _, ws = ortam()
    yanit = client.get(f"/panel/musteri/{ws.id}/hesaplar")

    assert "sahte sağlayıcı ile çalışıyor" in yanit.text
    assert "hesaplar/baglan" not in yanit.text  # bağla formu hiç yok


def test_sahte_modda_baglanma_istegi_reddediliyor(client, ortam):
    """Dugme gorunmese de istek elle gonderilebilir; sunucu reddetmeli."""
    _, ws = ortam()

    yanit = client.post(
        f"/panel/musteri/{ws.id}/hesaplar/baglan", data={"platform": "instagram"},
        follow_redirects=False,
    )

    assert yanit.status_code == 409
    assert "sahte sağlayıcı" in yanit.text


def test_canli_modda_eksik_meta_ayarlari_yaziliyor(client, ortam, monkeypatch):
    """URETIMDEKI DURUM: canli modda Meta sabitleri eksik oldugu icin
    platform hazir degil. Sayfa NEDEN hazir olmadigini ve hangi ayarlarin
    eksik oldugunu acikca yazmali; calismayan dugme gostermemeli."""
    from app.core.config import get_settings
    from app.panel import routes

    ayarlar = get_settings()
    monkeypatch.setattr(ayarlar, "platform_mode", "live", raising=False)
    monkeypatch.setattr(routes, "_sahte_platform_modu", lambda: False)

    _, ws = ortam()
    yanit = client.get(f"/panel/musteri/{ws.id}/hesaplar")

    assert "henüz bağlanamıyor" in yanit.text
    assert "Neden bağlanamıyor" in yanit.text
    assert "META_" in yanit.text
    assert "hesaplar/baglan" not in yanit.text  # bağla formu hiç yok


def test_canli_modda_hazir_olmayan_platforma_istek_reddediliyor(
    client, ortam, monkeypatch
):
    from app.core.config import get_settings
    from app.panel import routes

    monkeypatch.setattr(get_settings(), "platform_mode", "live", raising=False)
    monkeypatch.setattr(routes, "_sahte_platform_modu", lambda: False)

    _, ws = ortam()
    yanit = client.post(
        f"/panel/musteri/{ws.id}/hesaplar/baglan", data={"platform": "instagram"},
        follow_redirects=False,
    )

    assert yanit.status_code == 409
    assert "henüz bağlanamıyor" in yanit.text


def test_gecersiz_platform_reddediliyor(client, ortam):
    _, ws = ortam()
    yanit = client.post(
        f"/panel/musteri/{ws.id}/hesaplar/baglan", data={"platform": "uydurma"},
        follow_redirects=False,
    )
    assert yanit.status_code == 400


def test_stratejist_hesap_baglayamiyor(client, ortam):
    _, ws = ortam(rol=WorkspaceRole.STRATEGIST)
    yanit = client.post(
        f"/panel/musteri/{ws.id}/hesaplar/baglan", data={"platform": "instagram"},
        follow_redirects=False,
    )
    assert yanit.status_code == 403


def test_izleyiciye_bagla_formu_gosterilmiyor(client, ortam):
    _, ws = ortam(rol=WorkspaceRole.VIEWER)
    yanit = client.get(f"/panel/musteri/{ws.id}/hesaplar")
    assert yanit.status_code == 200
    assert "hesaplar/baglan" not in yanit.text


def test_baska_musterinin_hesaplari_gorunmuyor(client, db, ortam, make_workspace):
    """Izolasyon: baska musterinin hesabi bu sayfada gorunmemeli."""
    _, benim = ortam()
    baskasinin = make_workspace(name="Baskasinin")
    db.add(SocialAccount(
        workspace_id=baskasinin.id, platform=Platform.INSTAGRAM,
        external_id="999", username="gizli_hesap",
    ))
    db.flush()

    yanit = client.get(f"/panel/musteri/{benim.id}/hesaplar")

    assert "gizli_hesap" not in yanit.text


def test_uye_olunmayan_musteri_404(client, make_user, make_workspace):
    kullanici = make_user(password=SIFRE)
    baskasinin = make_workspace(name="Baskasinin")
    _giris(client, kullanici)

    assert client.get(f"/panel/musteri/{baskasinin.id}/hesaplar").status_code == 404
    assert client.post(
        f"/panel/musteri/{baskasinin.id}/hesaplar/baglan", data={"platform": "instagram"}
    ).status_code == 404


def test_oturumsuz_erisim_girise_yonlendiriyor(client, make_workspace):
    ws = make_workspace()
    yanit = client.get(f"/panel/musteri/{ws.id}/hesaplar", follow_redirects=False)
    assert yanit.status_code == 303
    assert yanit.headers["location"] == "/panel/giris"
