"""Ayrintili yetki sistemi. Izinler KULLANICIYA aittir.

ONCEDEN: izinler (musteri, rol) ciftine bagliydi. Yetki ekrani her
musterinin altinda ayri ayri duruyordu; ayni kisi iki musteride iki
farkli yetkide olabiliyordu ve "bu kullanici neyi yapabilir?"
sorusunun TEK bir cevabi yoktu.

SIMDI: her kullanicinin kendi izin kumesi vardir. Musteri uyeligi
yalnizca ERISIMI belirler: uyelik varsa o musteri gorunur.

IKI KURAL:
1. SISTEM YONETICISI (is_superuser) her seyi yapar. Izni kisitlanamaz;
   aksi halde sistem yonetilemez hale gelir ve kurtarmak icin sunucuya
   girmek gerekirdi.
2. Ozellestirme yapilmamissa kullanicinin PAKETI gecerlidir. Paket
   yalnizca baslangic noktasidir; her izin tek tek degistirilebilir.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import PermissionPackage
from app.models.yetki import UserPermission


@dataclass(frozen=True)
class Izin:
    anahtar: str
    grup: str
    ad: str
    aciklama: str


# Izin katalogu. Panelde bu sirayla gosterilir.
IZINLER: tuple[Izin, ...] = (
    # --- Musteri bilgileri ---
    Izin("marka.duzenle", "Müşteri bilgileri", "Marka bilgilerini düzenle",
         "Marka adı, sektör, marka dili, hedef kitle, yasaklı ifadeler."),
    Izin("kampanya.yonet", "Müşteri bilgileri", "Kampanya ekle ve sil",
         "Dönemsel kampanyaları yönetir."),

    # --- Hesaplar ---
    Izin("hesap.bagla", "Sosyal hesaplar", "Sosyal medya hesabı bağla",
         "Instagram/Facebook hesabını bağlar. Hesabın verisine erişim açar."),
    Izin("hesap.gor", "Sosyal hesaplar", "Bağlı hesapları gör",
         "Hangi hesapların bağlı olduğunu ve son veri çekimini görür."),
    Izin("hesap.izle", "Sosyal hesaplar", "İzlenen hesapları yönet",
         "Rakip veya referans hesapları kullanıcı adıyla takip listesine "
         "ekler ve çıkarır. Hesaba erişim yetkisi İSTEMEZ."),

    # --- Icerik ---
    Izin("icerik.uret", "İçerik", "Yapay zekâ ile içerik ürettir",
         "Para harcatır: her üretim AI bütçesinden düşer."),
    Izin("icerik.duzenle", "İçerik", "İçeriği düzenle ve iç incelemeye gönder",
         "Taslağı değiştirir, iç incelemeye gönderir, incelemeden taslağa "
         "geri çeker."),
    Izin("icerik.onaya_sun", "İçerik", "Müşteri onayına sun veya reddet",
         "İçeriği müşteri incelemesine gönderir; uygun değilse reddeder."),
    Izin("icerik.onayla", "İçerik", "İçeriği onayla veya arşivle",
         "Son karardır. Onaylanmayan hiçbir şey takvime konulamaz."),

    # --- Takvim ---
    Izin("takvim.gor", "Takvim", "Yayın takvimini gör",
         "Planlanmış içerikleri görüntüler."),
    Izin("takvim.planla", "Takvim", "Takvime içerik yerleştir",
         "Yalnızca ONAYLANMIŞ içerik planlanabilir."),

    # --- Rapor ---
    Izin("rapor.gor", "Rapor", "Raporları gör", "Üretilmiş raporları okur."),
    Izin("rapor.hazirla", "Rapor", "Raporu iç incelemeye gönder",
         "Üretilen raporu ekip incelemesine alır, taslağa geri çeker."),
    Izin("rapor.sun", "Rapor", "Raporu müşteriye sun veya reddet",
         "Raporu müşteri incelemesine gönderir; uygun değilse reddeder."),
    Izin("rapor.onayla", "Rapor", "Raporu onayla veya arşivle",
         "Raporun müşteriye gösterilebilir hale gelmesini sağlar."),

    # --- Otomasyon ---
    Izin("otomasyon.ayar", "Otomasyon", "İş akışlarını aç/kapat",
         "Hangi otomasyonun bu müşteride çalışacağını belirler."),
    Izin("otomasyon.calistir", "Otomasyon", "İş akışını elle çalıştır",
         "Para harcatabilir: araştırma ve içerik akışları AI kullanır."),

    # --- Ekip ---
    Izin("ekip.gor", "Ekip", "Ekibi gör", "Kimin hangi yetkide olduğunu görür."),
    Izin("ekip.yonet", "Ekip", "Ekibi yönet",
         "Kişi ekler, çıkarır, yetkisini değiştirir."),
)

IZIN_ANAHTARLARI = frozenset(i.anahtar for i in IZINLER)
IZIN_SOZLUGU = {i.anahtar: i for i in IZINLER}

#: Panelde gosterilecek grup sirasi.
GRUPLAR = tuple(dict.fromkeys(i.grup for i in IZINLER))


# PAKET VARSAYILANLARI
#
# Bir paketin, hicbir ozellestirme yapilmamisken verdigi izinler.
# Eski rol tablosunun karsiligidir: kimsenin yetkisi bu gecisle
# artmadi veya azalmadi.
PAKET_VARSAYILANI: dict[PermissionPackage, frozenset[str]] = {
    PermissionPackage.ADMIN: IZIN_ANAHTARLARI,
    PermissionPackage.STRATEGIST: frozenset({
        "marka.duzenle", "kampanya.yonet", "hesap.gor", "hesap.izle",
        "icerik.uret", "icerik.duzenle", "icerik.onaya_sun",
        "takvim.gor", "takvim.planla",
        "rapor.gor", "rapor.hazirla", "rapor.sun",
        "otomasyon.calistir", "ekip.gor",
    }),
    PermissionPackage.EDITOR: frozenset({
        "hesap.gor", "icerik.duzenle", "takvim.gor",
        "rapor.gor", "rapor.hazirla", "ekip.gor",
    }),
    PermissionPackage.VIEWER: frozenset({
        "hesap.gor", "takvim.gor", "rapor.gor", "ekip.gor",
    }),
}

#: Paketlerin panelde gosterilecek adlari.
PAKET_ADLARI: dict[PermissionPackage, str] = {
    PermissionPackage.ADMIN: "Yönetici",
    PermissionPackage.STRATEGIST: "Stratejist",
    PermissionPackage.EDITOR: "Editör",
    PermissionPackage.VIEWER: "İzleyici",
}


class YetkiHatasi(Exception):
    """Yetki ayarinda kurala takilan islem."""


def _ozellestirmeler(db: Session, user_id: uuid.UUID) -> dict[str, bool]:
    satirlar = db.execute(
        select(UserPermission).where(UserPermission.user_id == user_id)
    ).scalars().all()
    return {s.permission: s.allowed for s in satirlar}


def kullanici_izinleri(db: Session, user) -> frozenset[str]:
    """Bu kullanicinin GECERLI izinleri."""
    # Sistem yoneticisi kisitlanamaz: kendini disari kilitleyen bir
    # sistem, duzeltmek icin sunucuya girmeyi gerektirirdi.
    if user.is_superuser:
        return IZIN_ANAHTARLARI

    temel = set(PAKET_VARSAYILANI.get(user.permission_package, frozenset()))
    for izin, acik in _ozellestirmeler(db, user.id).items():
        if izin not in IZIN_ANAHTARLARI:
            continue
        if acik:
            temel.add(izin)
        else:
            temel.discard(izin)
    return frozenset(temel)


def izin_var_mi(db: Session, user, izin: str) -> bool:
    """Bu kullanici bu isi yapabilir mi?"""
    if izin not in IZIN_ANAHTARLARI:
        # Tanimsiz izin ASLA verilmez: yazim hatasi sessizce kapi acmasin.
        raise YetkiHatasi(f"Tanımsız izin: {izin}")
    return izin in kullanici_izinleri(db, user)


def izinleri_yaz(db: Session, user, izinler: set[str]) -> None:
    """Bir kullanicinin izinlerini YENIDEN yazar.

    Paket varsayilaniyla ayni olan satirlar SAKLANMAZ: boylece bir
    paketin varsayilani ileride degisirse, ozellestirilmemis kullanicilar
    yeni varsayilani alir.
    """
    if user.is_superuser:
        raise YetkiHatasi(
            "Sistem yöneticisinin izinleri kısıtlanamaz. Sistemi "
            "yönetebilecek en az bir kişi her zaman kalmalıdır."
        )

    bilinmeyen = izinler - IZIN_ANAHTARLARI
    if bilinmeyen:
        raise YetkiHatasi(f"Tanımsız izin: {', '.join(sorted(bilinmeyen))}")

    varsayilan = PAKET_VARSAYILANI.get(user.permission_package, frozenset())
    mevcut = {
        s.permission: s
        for s in db.execute(
            select(UserPermission).where(UserPermission.user_id == user.id)
        ).scalars().all()
    }

    for izin in IZIN_ANAHTARLARI:
        istenen = izin in izinler
        if istenen == (izin in varsayilan):
            # Varsayilanla ayni: satir tutulmaz.
            if izin in mevcut:
                db.delete(mevcut[izin])
            continue

        if izin in mevcut:
            mevcut[izin].allowed = istenen
        else:
            db.add(UserPermission(
                user_id=user.id, permission=izin, allowed=istenen,
            ))
    db.flush()


def paketi_degistir(db: Session, user, paket: PermissionPackage) -> None:
    """Kullanicinin hazir paketini degistirir ve ozellestirmeleri siler.

    Ozellestirmeler NEDEN siliniyor: eski pakete gore yapilmis "sunu
    kapat" ayarlari yeni pakette anlamsiz, hatta tehlikeli olurdu.
    Paket secmek "temiz sayfa" demektir.
    """
    if user.is_superuser:
        raise YetkiHatasi("Sistem yöneticisinin paketi değiştirilemez.")
    user.permission_package = paket
    varsayilana_don(db, user)
    db.flush()


def varsayilana_don(db: Session, user) -> None:
    """Bu kullanicinin ozellestirmelerini siler; paket varsayilanina doner."""
    for satir in db.execute(
        select(UserPermission).where(UserPermission.user_id == user.id)
    ).scalars().all():
        db.delete(satir)
    db.flush()
