"""Kullanici yonetimi testleri.

Korunan kurallar:
- Sayfa yalnizca sistem yoneticisine acik; baskasina 404 (403 degil)
- Sifre yonetici tarafindan BELIRLENMEZ; tek kullanimlik bagla kisi belirler
- Yeni hesap, bag kullanilana kadar giris YAPAMAZ
- Sistemde en az bir etkin yonetici her zaman kalir (kilitlenme korumasi)
- Kimse kendi hesabini silemez, kendi yetkisini alamaz
- Her degisiklik denetim kaydina yazilir; degerler kayda GIRMEZ
"""

from __future__ import annotations

from sqlalchemy import select

from app.models.identity import User
from app.models.ops import AuditLog
from app.panel.auth import COOKIE_NAME
from app.services.sifre_sifirlama import jeton_gecerli_mi

SIFRE = "GucluSifre123!"


def _giris(client, kullanici, sifre=SIFRE):
    yanit = client.post(
        "/panel/giris", data={"email": kullanici.email, "password": sifre},
        follow_redirects=False,
    )
    assert yanit.status_code == 303, yanit.text[:300]
    return yanit.cookies.get(COOKIE_NAME)


def _yonetici(db, make_user):
    """Sistem yoneticisi uretir.

    `db.commit()` sart: hata yollari `db.rollback()` cagiriyor ve yalnizca
    flush edilmis kayitlar geri alinirdi. (Testin dis islemi yine de test
    sonunda tamamen geri aliniyor.)
    """
    k = make_user(password=SIFRE)
    k.is_superuser = True
    db.commit()
    return k


# --- Erisim -----------------------------------------------------------------

def test_sayfa_yalnizca_sistem_yoneticisine_acik(client, db, make_user):
    normal = make_user(password=SIFRE)
    _giris(client, normal)
    yanit = client.get("/panel/kullanicilar")
    # 403 degil 404: boyle bir sayfanin varligi bile ele verilmez.
    assert yanit.status_code == 404


def test_giris_yapmadan_girise_yonlendirir(client):
    yanit = client.get("/panel/kullanicilar", follow_redirects=False)
    assert yanit.status_code == 303
    assert yanit.headers["location"] == "/panel/giris"


def test_yonetici_listeyi_goruyor(client, db, make_user):
    yonetici = _yonetici(db, make_user)
    baskasi = make_user()
    _giris(client, yonetici)

    yanit = client.get("/panel/kullanicilar")
    assert yanit.status_code == 200
    assert baskasi.email in yanit.text
    assert yonetici.email in yanit.text


# --- Hesap acma -------------------------------------------------------------

def test_yeni_hesap_aciliyor_ve_bag_bir_kez_gosteriliyor(client, db, make_user):
    yonetici = _yonetici(db, make_user)
    _giris(client, yonetici)

    yanit = client.post(
        "/panel/kullanicilar/ekle",
        data={"ad": "Ayşe Yılmaz", "email": "  Ayse@Ornek.COM  "},
    )
    assert yanit.status_code == 200
    assert "/panel/sifre-belirle?jeton=" in yanit.text

    yeni = db.execute(
        select(User).where(User.email == "ayse@ornek.com")
    ).scalar_one()
    assert yeni.full_name == "Ayşe Yılmaz"
    assert yeni.is_active is True
    assert yeni.is_superuser is False

    # Sayfa yenilendiginde bag ARTIK GORUNMEZ.
    tekrar = client.get("/panel/kullanicilar")
    assert "/panel/sifre-belirle?jeton=" not in tekrar.text


def test_yeni_hesap_bag_kullanilmadan_giris_yapamaz(client, db, make_user):
    """Hesap kimsenin bilmedigi bir degerle kilitli acilir."""
    yonetici = _yonetici(db, make_user)
    _giris(client, yonetici)
    client.post(
        "/panel/kullanicilar/ekle", data={"ad": "Kilitli", "email": "kilitli@ornek.com"}
    )
    client.post("/panel/cikis")

    for deneme in ("", " ", SIFRE, "123456"):
        yanit = client.post(
            "/panel/giris", data={"email": "kilitli@ornek.com", "password": deneme}
        )
        assert yanit.status_code == 401


def test_bag_gercekten_calisiyor_ve_tek_kullanimlik(client, db, make_user):
    yonetici = _yonetici(db, make_user)
    _giris(client, yonetici)
    yanit = client.post(
        "/panel/kullanicilar/ekle", data={"ad": "Yeni Kisi", "email": "yeni@ornek.com"}
    )
    jeton = yanit.text.split("/panel/sifre-belirle?jeton=")[1].split("<")[0].strip()
    assert jeton_gecerli_mi(jeton)
    client.post("/panel/cikis")

    yeni_sifre = "BenimSifrem2026!"
    belirle = client.post(
        "/panel/sifre-belirle",
        data={"jeton": jeton, "yeni": yeni_sifre, "yeni_tekrar": yeni_sifre},
        follow_redirects=False,
    )
    assert belirle.status_code in (200, 303), belirle.text[:300]
    assert not jeton_gecerli_mi(jeton)

    kullanici = db.execute(
        select(User).where(User.email == "yeni@ornek.com")
    ).scalar_one()
    db.refresh(kullanici)
    assert _giris(client, kullanici, yeni_sifre)


def test_ayni_eposta_ikinci_kez_acilamaz(client, db, make_user):
    yonetici = _yonetici(db, make_user)
    mevcut = make_user(email="var@ornek.com")
    _giris(client, yonetici)

    yanit = client.post(
        "/panel/kullanicilar/ekle", data={"ad": "Kopya", "email": "VAR@ornek.com"}
    )
    assert yanit.status_code == 400
    assert "zaten var" in yanit.text
    assert mevcut.full_name != "Kopya"


def test_bozuk_eposta_reddediliyor(client, db, make_user):
    yonetici = _yonetici(db, make_user)
    _giris(client, yonetici)
    yanit = client.post(
        "/panel/kullanicilar/ekle", data={"ad": "Bozuk", "email": "ad-ornek.com"}
    )
    assert yanit.status_code == 400
    assert "biçimi geçersiz" in yanit.text


# --- Kilitlenme korumasi ----------------------------------------------------

def test_son_yonetici_silinemez(client, db, make_user):
    yonetici = _yonetici(db, make_user)
    ikinci = _yonetici(db, make_user)
    _giris(client, yonetici)

    yanit = client.post(
        "/panel/kullanicilar/sil", data={"user_id": str(ikinci.id)}
    )
    assert yanit.status_code == 200  # iki yonetici varken silinebilir
    assert db.get(User, ikinci.id) is None

    # Artik tek yonetici kaldi: kendini silemez.
    kendi = client.post(
        "/panel/kullanicilar/sil", data={"user_id": str(yonetici.id)}
    )
    assert kendi.status_code == 400
    assert "Kendi hesabınızı silemezsiniz" in kendi.text
    assert db.get(User, yonetici.id) is not None


def test_son_yonetici_pasiflestirilemez(client, db, make_user):
    yonetici = _yonetici(db, make_user)
    ikinci = _yonetici(db, make_user)
    _giris(client, yonetici)

    yanit = client.post(
        "/panel/kullanicilar/duzenle",
        data={"user_id": str(ikinci.id), "ad": ikinci.full_name},  # etkin isaretli degil
    )
    assert yanit.status_code == 200
    db.refresh(ikinci)
    assert ikinci.is_active is False

    # Simdi tek etkin yonetici kaldi; onun da yetkisi alinamaz.
    db.refresh(yonetici)
    assert yonetici.is_active is True


def test_tek_yoneticinin_yetkisi_alinamaz(client, db, make_user):
    yonetici = _yonetici(db, make_user)
    yardimci = _yonetici(db, make_user)
    _giris(client, yardimci)

    # yonetici'nin sistem yoneticiligini al: hala yardimci var, gecmeli.
    ilk = client.post(
        "/panel/kullanicilar/duzenle",
        data={"user_id": str(yonetici.id), "ad": yonetici.full_name, "etkin": "1"},
    )
    assert ilk.status_code == 200
    db.refresh(yonetici)
    assert yonetici.is_superuser is False

    # Artik tek yonetici yardimci; kendi yetkisini alamaz.
    kendi = client.post(
        "/panel/kullanicilar/duzenle",
        data={"user_id": str(yardimci.id), "ad": yardimci.full_name, "etkin": "1"},
    )
    assert kendi.status_code == 400
    assert "Kendi yönetici yetkinizi alamazsınız" in kendi.text
    db.refresh(yardimci)
    assert yardimci.is_superuser is True


def test_kendini_pasiflestiremez(client, db, make_user):
    yonetici = _yonetici(db, make_user)
    _yonetici(db, make_user)  # ikinci yonetici var, kilitlenme korumasi devreye girmez
    _giris(client, yonetici)

    yanit = client.post(
        "/panel/kullanicilar/duzenle",
        data={"user_id": str(yonetici.id), "ad": yonetici.full_name, "yonetici": "1"},
    )
    assert yanit.status_code == 400
    assert "Kendi hesabınızı pasifleştiremezsiniz" in yanit.text
    db.refresh(yonetici)
    assert yonetici.is_active is True


# --- Silme ve denetim -------------------------------------------------------

def test_normal_kullanici_silinebiliyor(client, db, make_user):
    yonetici = _yonetici(db, make_user)
    hedef = make_user(email="gidecek@ornek.com")
    _giris(client, yonetici)

    yanit = client.post("/panel/kullanicilar/sil", data={"user_id": str(hedef.id)})
    assert yanit.status_code == 200
    assert db.get(User, hedef.id) is None


def test_degisiklikler_denetime_yaziliyor_ama_degerler_yazilmiyor(client, db, make_user):
    yonetici = _yonetici(db, make_user)
    _giris(client, yonetici)
    client.post(
        "/panel/kullanicilar/ekle", data={"ad": "Denetim", "email": "denetim@ornek.com"}
    )

    kayitlar = db.execute(
        select(AuditLog).where(AuditLog.action == "kullanici.olustur")
    ).scalars().all()
    assert len(kayitlar) == 1
    assert kayitlar[0].actor_user_id == yonetici.id
    assert kayitlar[0].details["email"] == "denetim@ornek.com"
    # Sifre veya jeton HICBIR SEKILDE kayda girmez.
    metin = str(kayitlar[0].details)
    assert "jeton" not in metin and "sifre" not in metin and "password" not in metin


def test_sifre_bagi_uretmek_denetime_yaziliyor_ama_bag_yazilmiyor(client, db, make_user):
    yonetici = _yonetici(db, make_user)
    hedef = make_user(email="bagli@ornek.com")
    _giris(client, yonetici)

    yanit = client.post("/panel/kullanicilar/bag", data={"user_id": str(hedef.id)})
    assert yanit.status_code == 200
    assert "/panel/sifre-belirle?jeton=" in yanit.text

    kayit = db.execute(
        select(AuditLog).where(AuditLog.action == "kullanici.sifre_bagi")
    ).scalar_one()
    assert "jeton" not in str(kayit.details)


def test_pasif_hesap_icin_bag_uretilmiyor(client, db, make_user):
    yonetici = _yonetici(db, make_user)
    hedef = make_user(email="pasif@ornek.com")
    hedef.is_active = False
    db.flush()
    _giris(client, yonetici)

    yanit = client.post("/panel/kullanicilar/bag", data={"user_id": str(hedef.id)})
    assert yanit.status_code == 400
    assert "Pasif hesap" in yanit.text


def test_kullanici_detayi_musteri_yetkilerini_gosteriyor(
    client, db, make_user, make_workspace, add_member
):
    from app.models.enums import WorkspaceRole

    yonetici = _yonetici(db, make_user)
    hedef = make_user(email="detay@ornek.com")
    ws = make_workspace(name="Detay Müşterisi")
    add_member(ws, hedef, WorkspaceRole.EDITOR)
    _giris(client, yonetici)

    yanit = client.get(f"/panel/kullanicilar/{hedef.id}")
    assert yanit.status_code == 200
    assert "Detay Müşterisi" in yanit.text
    assert "Editör" in yanit.text
