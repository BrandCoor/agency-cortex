"""Panel (tarayici arayuzu) testleri.

Panel, kullanicinin sistemi gordugu tek yerdir. Buradaki bir kopukluk
"calisiyor ama kimse goremiyor" durumuna yol acar; bu yuzden giris,
oturum, yetki sinirlari ve sifre degistirme ayri ayri test edilir.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.security import verify_password
from app.models.enums import WorkspaceRole
from app.panel.auth import COOKIE_NAME

SIFRE = "GucluSifre123!"


# --- Giris sayfasi -----------------------------------------------------------

def test_giris_sayfasi_formu_donuyor(client):
    """Ters vekil yapilandirmasi bu sayfanin varligina dayaniyor."""
    yanit = client.get("/panel/giris")
    assert yanit.status_code == 200
    assert 'action="/panel/giris"' in yanit.text
    assert 'name="email"' in yanit.text
    assert 'name="password"' in yanit.text


def test_dogru_bilgiyle_giris_cerez_veriyor(client, make_user):
    kullanici = make_user(password=SIFRE)
    yanit = client.post(
        "/panel/giris",
        data={"email": kullanici.email, "password": SIFRE},
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    assert yanit.headers["location"] == "/panel"
    cerez = yanit.cookies.get(COOKIE_NAME)
    assert cerez
    # Cerez JavaScript'e kapali olmali.
    assert "httponly" in yanit.headers["set-cookie"].lower()


def test_hatali_sifre_ayni_mesaji_veriyor(client, make_user):
    """Kullanicinin var olup olmadigi mesajdan anlasilmamali."""
    kullanici = make_user(password=SIFRE)

    yanlis_sifre = client.post(
        "/panel/giris", data={"email": kullanici.email, "password": "YanlisSifre123!"}
    )
    olmayan_hesap = client.post(
        "/panel/giris", data={"email": "yok@ornek.com", "password": SIFRE}
    )

    assert yanlis_sifre.status_code == 401
    assert olmayan_hesap.status_code == 401
    assert "E-posta veya şifre hatalı." in yanlis_sifre.text
    assert "E-posta veya şifre hatalı." in olmayan_hesap.text


def test_pasif_kullanici_giremiyor(client, db, make_user):
    kullanici = make_user(password=SIFRE)
    kullanici.is_active = False
    db.flush()

    yanit = client.post(
        "/panel/giris", data={"email": kullanici.email, "password": SIFRE}
    )
    assert yanit.status_code == 401


# --- Oturum gerektiren sayfalar ----------------------------------------------

def _giris_yap(client, kullanici) -> None:
    yanit = client.post(
        "/panel/giris",
        data={"email": kullanici.email, "password": SIFRE},
        follow_redirects=False,
    )
    assert yanit.status_code == 303


def test_oturumsuz_erisim_girise_yonlendiriyor(client):
    for yol in ["/panel", "/panel/sifre", f"/panel/musteri/{uuid.uuid4()}"]:
        yanit = client.get(yol, follow_redirects=False)
        assert yanit.status_code == 303, yol
        assert yanit.headers["location"] == "/panel/giris", yol


def test_musteri_listesi_yalnizca_uye_olunanlari_gosteriyor(
    client, make_user, make_workspace, add_member
):
    kullanici = make_user(password=SIFRE)
    benim = make_workspace(name="Benim Musterim")
    make_workspace(name="Baskasinin Musterisi")  # uye olunmayan musteri
    add_member(benim, kullanici, WorkspaceRole.OWNER)

    _giris_yap(client, kullanici)
    yanit = client.get("/panel")

    assert yanit.status_code == 200
    assert "Benim Musterim" in yanit.text
    assert "Baskasinin Musterisi" not in yanit.text


def test_uye_olunmayan_musteri_404_donuyor(client, make_user, make_workspace):
    """403 degil 404: 403, o musterinin var oldugunu ele verirdi."""
    kullanici = make_user(password=SIFRE)
    baskasinin = make_workspace(name="Baskasinin Musterisi")

    _giris_yap(client, kullanici)
    yanit = client.get(f"/panel/musteri/{baskasinin.id}")

    assert yanit.status_code == 404


def test_cikis_cerezi_siliyor(client, make_user):
    kullanici = make_user(password=SIFRE)
    _giris_yap(client, kullanici)

    yanit = client.post("/panel/cikis", follow_redirects=False)
    assert yanit.status_code == 303
    assert yanit.headers["location"] == "/panel/giris"

    sonraki = client.get("/panel", follow_redirects=False)
    assert sonraki.status_code == 303


# --- Sifre degistirme --------------------------------------------------------

def test_sifre_sayfasi_aciliyor(client, make_user):
    kullanici = make_user(password=SIFRE)
    _giris_yap(client, kullanici)

    yanit = client.get("/panel/sifre")
    assert yanit.status_code == 200
    assert 'name="mevcut"' in yanit.text


def test_sifre_degistirme_calisiyor(client, db, make_user):
    kullanici = make_user(password=SIFRE)
    _giris_yap(client, kullanici)
    yeni = "YepyeniSifre456!"

    yanit = client.post(
        "/panel/sifre",
        data={"mevcut": SIFRE, "yeni": yeni, "yeni_tekrar": yeni},
    )

    assert yanit.status_code == 200
    assert "Şifreniz değiştirildi." in yanit.text
    db.refresh(kullanici)
    assert verify_password(yeni, kullanici.password_hash)
    assert not verify_password(SIFRE, kullanici.password_hash)


def test_mevcut_sifre_yanlissa_degismiyor(client, db, make_user):
    """Cerezi calan biri sifreyi degistirip hesabi ele geciremesin."""
    kullanici = make_user(password=SIFRE)
    _giris_yap(client, kullanici)
    onceki_ozet = kullanici.password_hash

    yanit = client.post(
        "/panel/sifre",
        data={"mevcut": "YanlisSifre123!", "yeni": "YeniSifre4567!",
              "yeni_tekrar": "YeniSifre4567!"},
    )

    assert yanit.status_code == 401
    db.refresh(kullanici)
    assert kullanici.password_hash == onceki_ozet


def test_yeni_sifreler_tutmazsa_degismiyor(client, db, make_user):
    kullanici = make_user(password=SIFRE)
    _giris_yap(client, kullanici)
    onceki_ozet = kullanici.password_hash

    yanit = client.post(
        "/panel/sifre",
        data={"mevcut": SIFRE, "yeni": "YeniSifre4567!", "yeni_tekrar": "BaskaSifre789!"},
    )

    assert yanit.status_code == 400
    db.refresh(kullanici)
    assert kullanici.password_hash == onceki_ozet


def test_kisa_sifre_reddediliyor(client, db, make_user):
    kullanici = make_user(password=SIFRE)
    _giris_yap(client, kullanici)
    onceki_ozet = kullanici.password_hash

    yanit = client.post(
        "/panel/sifre", data={"mevcut": SIFRE, "yeni": "kisa1!", "yeni_tekrar": "kisa1!"}
    )

    assert yanit.status_code == 400
    db.refresh(kullanici)
    assert kullanici.password_hash == onceki_ozet


def test_ayni_sifre_reddediliyor(client, make_user):
    kullanici = make_user(password=SIFRE)
    _giris_yap(client, kullanici)

    yanit = client.post(
        "/panel/sifre", data={"mevcut": SIFRE, "yeni": SIFRE, "yeni_tekrar": SIFRE}
    )

    assert yanit.status_code == 400


def test_sifre_sayfasi_sifreyi_html_icine_yazmiyor(client, make_user):
    """Form yeniden cizilirken girilen sifre sayfaya dusmemeli."""
    kullanici = make_user(password=SIFRE)
    _giris_yap(client, kullanici)

    yanit = client.post(
        "/panel/sifre",
        data={"mevcut": "YanlisSifre123!", "yeni": "GizliYeni7890!",
              "yeni_tekrar": "GizliYeni7890!"},
    )

    assert "GizliYeni7890!" not in yanit.text
    assert "YanlisSifre123!" not in yanit.text


# --- Yeni musteri ekleme -----------------------------------------------------

def test_musteri_eklenebiliyor(client, db, make_user):
    kullanici = make_user(password=SIFRE)
    _giris_yap(client, kullanici)

    yanit = client.post(
        "/panel/musteri-ekle", data={"ad": "Gaziantepli Taha Usta"},
        follow_redirects=False,
    )

    assert yanit.status_code == 303
    assert yanit.headers["location"].startswith("/panel/musteri/")

    from app.models.identity import Workspace, WorkspaceMember
    ws = db.execute(select(Workspace)).scalars().one()
    assert ws.name == "Gaziantepli Taha Usta"
    # Turkce harfler ve bosluklar URL'ye uygun hale gelmeli.
    assert ws.slug.startswith("gaziantepli-taha-usta-")

    # Musteriyi olusturan kisi otomatik olarak ekibine atanir.
    # Uyelik YETKI TASIMAZ; ne yapabilecegi kendi hesabinda yazar.
    uyelik = db.execute(select(WorkspaceMember)).scalars().one()
    assert uyelik.user_id == kullanici.id


def test_ayni_isimli_iki_musteri_eklenebiliyor(client, db, make_user):
    """Kisa ad (slug) benzersiz; ayni isim ikinci kez eklenince cakismamali."""
    kullanici = make_user(password=SIFRE)
    _giris_yap(client, kullanici)

    for _ in range(2):
        yanit = client.post(
            "/panel/musteri-ekle", data={"ad": "Aynı İsim"}, follow_redirects=False
        )
        assert yanit.status_code == 303

    from app.models.identity import Workspace
    kisa_adlar = db.execute(select(Workspace.slug)).scalars().all()
    assert len(kisa_adlar) == 2
    assert len(set(kisa_adlar)) == 2


def test_kisa_ad_uretimi_turkce_harfleri_cevirir():
    from app.panel.routes import kisa_ad_uret

    uretilen = kisa_ad_uret("Çiğdem Şölen Öğüt")
    assert uretilen.startswith("cigdem-solen-ogut-")
    # Yalnizca kucuk harf, rakam ve tire kalmali.
    assert all(k.islower() or k.isdigit() or k == "-" for k in uretilen)


def test_bos_isimle_musteri_eklenmiyor(client, db, make_user):
    kullanici = make_user(password=SIFRE)
    _giris_yap(client, kullanici)

    yanit = client.post("/panel/musteri-ekle", data={"ad": " "})

    assert yanit.status_code == 200
    assert "Müşteri adı en az 2 karakter olmalı." in yanit.text
    from app.models.identity import Workspace
    assert db.execute(select(Workspace)).scalars().all() == []


def test_oturumsuz_musteri_eklenemiyor(client, db):
    yanit = client.post(
        "/panel/musteri-ekle", data={"ad": "Gizli Musteri"}, follow_redirects=False
    )
    assert yanit.status_code == 303
    assert yanit.headers["location"] == "/panel/giris"
    from app.models.identity import Workspace
    assert db.execute(select(Workspace)).scalars().all() == []
