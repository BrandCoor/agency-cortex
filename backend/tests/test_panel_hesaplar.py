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
    assert "profesyonel" in yanit.text
    # Hic veri cekilmediyse bu acikca yazmali.
    assert "henüz hiç veri çekilmedi" in yanit.text


def test_meta_kurulmadan_bagla_dugmesi_gosterilmiyor(client, ortam):
    """Meta uygulamasi tanimli degilken gercek hesap baglanamaz.

    Calismayacak bir dugme gostermek yerine NE YAPILACAGI yaziliyor.
    """
    _, ws = ortam()
    yanit = client.get(f"/panel/musteri/{ws.id}/hesaplar")

    assert "hesaplar/baglan" not in yanit.text  # bağla formu hiç yok
    assert "Meta uygulaması tanımlanmalı" in yanit.text
    # Platform "baglanabilir" diye GOSTERILMEMELI; sahte adaptor
    # saglikli der ama gercek hesap baglayamaz.
    assert "bağlanabilir" not in yanit.text
    assert "henüz bağlanamıyor" in yanit.text
    # Normal kullaniciya ayar adlari degil, ne yapacagi soylenir.
    assert "sistem yöneticisinden" in yanit.text


def test_yonetici_hangi_ayarin_eksik_oldugunu_goruyor(client, db, ortam):
    kullanici, ws = ortam()
    kullanici.is_superuser = True
    db.flush()

    yanit = client.get(f"/panel/musteri/{ws.id}/hesaplar")
    assert "META_APP_ID" in yanit.text
    assert "META_APP_SECRET" in yanit.text


def test_donus_adresi_alan_adindan_uretiliyor(client, db, ortam, monkeypatch):
    """Meta'ya girilecek adres BIREBIR ayni olmali.

    Kullanicinin elle yazmasi yerine alan adindan uretilip kopyalanabilir
    sekilde gosteriliyor; bir harf farki baglantiyi bozardi.
    """
    from app.core.config import Settings
    from app.platforms import meta_ayar

    monkeypatch.setattr(
        meta_ayar, "get_settings",
        lambda: Settings(public_domain="ornek-ajans.test"),
    )

    kullanici, ws = ortam()
    kullanici.is_superuser = True
    db.flush()

    yanit = client.get(f"/panel/musteri/{ws.id}/hesaplar")
    assert "https://ornek-ajans.test/api/v1/oauth/meta/callback" in yanit.text


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


# --- Panelden girilen Meta bilgileri gercekten devreye giriyor mu? ----------
#
# ONCEDEN CALISMIYORDU: adaptor yalnizca ortam degiskenlerine bakiyordu.
# Kullanici anahtarlari panele giriyor, hicbir sey degismiyordu.

@pytest.fixture
def meta_kurulu(db, monkeypatch):
    """Meta uygulama bilgilerini PANEL AYARI olarak tanimlar.

    Kullanicinin girmesi gereken yalnizca iki deger var: uygulama kimligi
    ve gizli anahtar. Donus adresi alan adindan URETILIR.
    """
    from app.core.config import Settings
    from app.platforms import meta_ayar
    from app.services.sistem_ayarlari import deger_yaz

    def _kur(app_id="app-123", app_secret="gizli-anahtar"):
        monkeypatch.setattr(
            meta_ayar, "get_settings",
            lambda: Settings(public_domain="ornek-ajans.test"),
        )
        deger_yaz(db, "META_APP_ID", app_id, user_id=None)
        deger_yaz(db, "META_APP_SECRET", app_secret, user_id=None)
        db.flush()

    return _kur


def test_panelden_girilen_meta_bilgileri_baglantiyi_aciyor(client, db, ortam, meta_kurulu):
    """Anahtarlar panele girilince gercek baglanti acilmali."""
    kullanici, ws = ortam()
    meta_kurulu()

    yanit = client.get(f"/panel/musteri/{ws.id}/hesaplar")
    assert yanit.status_code == 200
    # Artik sahte mod yok; gercek baglanti dugmesi gorunuyor.
    assert "hesaplar/baglan" in yanit.text
    assert "Meta uygulaması tanımlanmalı" not in yanit.text


def test_bagla_dugmesi_meta_izin_ekranina_goturuyor(client, db, ortam, meta_kurulu):
    """DUGME GERCEKTEN CALISMALI.

    Onceden panel, POST ve Bearer bekleyen bir API ucuna GET olarak
    yonlendiriyordu; dugme hicbir zaman calismamisti.
    """
    kullanici, ws = ortam()
    meta_kurulu()

    yanit = client.post(
        f"/panel/musteri/{ws.id}/hesaplar/baglan",
        data={"platform": "instagram"}, follow_redirects=False,
    )

    assert yanit.status_code == 303
    hedef = yanit.headers["location"]
    # Meta'nin izin ekranina gidilmeli.
    assert hedef.startswith("https://www.instagram.com/oauth/authorize?")
    assert "client_id=app-123" in hedef
    assert "state=" in hedef
    # GIZLI ANAHTAR izin adresine ASLA konulmaz.
    assert "gizli-anahtar" not in hedef
    # Yayinlama/yorum izni ISTENMEZ.
    assert "publish" not in hedef


def test_meta_kuruluyken_de_stratejist_hesap_baglayamiyor(
    client, db, ortam, meta_kurulu
):
    kullanici, ws = ortam(WorkspaceRole.STRATEGIST)
    meta_kurulu()

    yanit = client.post(
        f"/panel/musteri/{ws.id}/hesaplar/baglan",
        data={"platform": "instagram"}, follow_redirects=False,
    )
    assert yanit.status_code == 403


def test_uye_olunmayan_musteride_hesap_baglanamiyor(
    client, db, make_user, make_workspace, meta_kurulu
):
    kullanici = make_user(password=SIFRE)
    baskasi = make_workspace(name="Baskasinin Musterisi")
    db.commit()
    meta_kurulu()
    _giris(client, kullanici)

    yanit = client.post(
        f"/panel/musteri/{baskasi.id}/hesaplar/baglan",
        data={"platform": "instagram"}, follow_redirects=False,
    )
    assert yanit.status_code == 404
