"""Kullanici yonetiminin is kurallari.

Kurallar burada, sayfa kodunda DEGIL. Ayni kurallarin API'den de gecmesi
gerekir; iki yerde ayri ayri yazilirsa biri unutulur.

KILITLENME KORUMASI (en onemlisi): sistemde en az bir etkin sistem
yoneticisi HER ZAMAN kalmalidir. Son yoneticiyi silmek, pasiflestirmek
veya yetkisini almak engellenir - aksi halde panele kimse giremez ve
kurtarma yalnizca sunucuya SSH ile baglanarak yapilabilir.
"""

from __future__ import annotations

import re
import secrets
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.identity import User, WorkspaceMember

# Bicim denetimi kasten gevsek: gecerli e-posta adreslerinin tam kumesi
# karmasiktir ve fazla siki bir desen gercek adresleri reddeder.
EPOSTA_DESENI = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MAKSIMUM_AD_UZUNLUGU = 200
MAKSIMUM_EPOSTA_UZUNLUGU = 320


class KullaniciHatasi(Exception):
    """Kullanici yonetiminde kurala takilan islem."""


def eposta_duzelt(ham: str) -> str:
    """E-postayi kayit icin normallestirir.

    Bastaki/sondaki bosluk silinir ve kucuk harfe cevrilir: "Ali@X.com" ile
    "ali@x.com" ayni hesaptir, iki kayit acilmamalidir.
    """
    eposta = (ham or "").strip().lower()
    if not eposta:
        raise KullaniciHatasi("E-posta boş olamaz.")
    if len(eposta) > MAKSIMUM_EPOSTA_UZUNLUGU:
        raise KullaniciHatasi("E-posta çok uzun.")
    if not EPOSTA_DESENI.match(eposta):
        raise KullaniciHatasi("E-posta biçimi geçersiz. Örnek: ad@ornek.com")
    return eposta


def ad_duzelt(ham: str) -> str:
    ad = " ".join((ham or "").split())
    if not ad:
        raise KullaniciHatasi("Ad soyad boş olamaz.")
    if len(ad) > MAKSIMUM_AD_UZUNLUGU:
        raise KullaniciHatasi("Ad soyad çok uzun.")
    return ad


def etkin_yonetici_sayisi(db: Session, *, haric: uuid.UUID | None = None) -> int:
    """Kac etkin sistem yoneticisi var? `haric` verilen kisi sayilmaz."""
    sorgu = select(func.count()).select_from(User).where(
        User.is_superuser.is_(True), User.is_active.is_(True)
    )
    if haric is not None:
        sorgu = sorgu.where(User.id != haric)
    return db.execute(sorgu).scalar_one()


def _son_yonetici_mi(db: Session, hedef: User) -> bool:
    """Bu kisi gidersek yonetici kalmiyor mu?"""
    if not (hedef.is_superuser and hedef.is_active):
        return False
    return etkin_yonetici_sayisi(db, haric=hedef.id) == 0


def kullanici_olustur(
    db: Session,
    *,
    email: str,
    full_name: str,
    is_superuser: bool = False,
) -> User:
    """Yeni kullanici acar.

    SIFRE BURADA BELIRLENMEZ. Hesap, kimsenin bilmedigi rastgele bir deger
    ile kilitli acilir; kullanici sifresini tek kullanimlik bagla KENDISI
    belirler. Boylece sifre hic aktarilmaz ve yoneticinin eline gecmez.
    """
    eposta = eposta_duzelt(email)
    ad = ad_duzelt(full_name)

    mevcut = db.execute(select(User).where(User.email == eposta)).scalar_one_or_none()
    if mevcut is not None:
        raise KullaniciHatasi("Bu e-posta ile kayıtlı bir kullanıcı zaten var.")

    kullanici = User(
        email=eposta,
        full_name=ad,
        # Kimsenin bilmedigi deger: bu haliyle giris YAPILAMAZ.
        password_hash=hash_password(secrets.token_urlsafe(48)),
        is_active=True,
        is_superuser=is_superuser,
    )
    db.add(kullanici)
    db.flush()
    return kullanici


def kullanici_guncelle(
    db: Session,
    hedef: User,
    *,
    duzenleyen: User,
    full_name: str | None = None,
    is_active: bool | None = None,
    is_superuser: bool | None = None,
) -> list[str]:
    """Kullaniciyi gunceller. Doner: degisen alanlarin adlari.

    Degerler DONMEZ, yalnizca alan adlari doner; denetim kaydina yazilacak
    olan budur.
    """
    degisenler: list[str] = []

    if full_name is not None:
        yeni_ad = ad_duzelt(full_name)
        if yeni_ad != hedef.full_name:
            hedef.full_name = yeni_ad
            degisenler.append("full_name")

    if is_active is not None and is_active != hedef.is_active:
        if not is_active:
            if hedef.id == duzenleyen.id:
                raise KullaniciHatasi("Kendi hesabınızı pasifleştiremezsiniz.")
            if _son_yonetici_mi(db, hedef):
                raise KullaniciHatasi(
                    "Bu kişi sistemdeki son etkin yöneticidir. "
                    "Pasifleştirilirse panele kimse giremez."
                )
        hedef.is_active = is_active
        degisenler.append("is_active")

    if is_superuser is not None and is_superuser != hedef.is_superuser:
        if not duzenleyen.is_superuser:
            raise KullaniciHatasi("Yönetici yetkisini yalnızca bir yönetici verebilir.")
        if not is_superuser:
            if hedef.id == duzenleyen.id:
                raise KullaniciHatasi(
                    "Kendi yönetici yetkinizi alamazsınız. "
                    "Bunu sizden başka bir yönetici yapmalıdır."
                )
            if _son_yonetici_mi(db, hedef):
                raise KullaniciHatasi(
                    "Bu kişi sistemdeki son etkin yöneticidir. "
                    "Yetkisi alınırsa panele kimse giremez."
                )
        hedef.is_superuser = is_superuser
        degisenler.append("is_superuser")

    return degisenler


def kullanici_sil(db: Session, hedef: User, *, silen: User) -> None:
    """Kullaniciyi kalici olarak siler.

    Uyelikleri de silinir (veritabani CASCADE). Urettigi icerik ve denetim
    kayitlari SILINMEZ; o kayitlarda kisi alani bosa duser.
    """
    if hedef.id == silen.id:
        raise KullaniciHatasi("Kendi hesabınızı silemezsiniz.")
    if _son_yonetici_mi(db, hedef):
        raise KullaniciHatasi(
            "Bu kişi sistemdeki son etkin yöneticidir. Silinirse panele kimse giremez."
        )
    db.delete(hedef)


def uyelik_ozeti(db: Session, user_id: uuid.UUID) -> int:
    """Kullanicinin kac musteride yetkisi var?"""
    return db.execute(
        select(func.count()).select_from(WorkspaceMember).where(
            WorkspaceMember.user_id == user_id
        )
    ).scalar_one()
