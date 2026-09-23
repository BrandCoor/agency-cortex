"""Ayrintili yetki sistemi.

ONCEDEN: bes sabit rol vardi ve "kim neyi yapabilir" koda gomuluydu.
Kullanici bir rolun neyi yapip yapamayacagini degistiremiyordu.

SIMDI: her is ayri bir IZIN. Her musteri icin, her rolun hangi izinlere
sahip oldugu panelden ayarlanabilir.

IKI KURAL DEGISMEZ:
1. SAHIP her seyi yapar. Sahibin izni kisitlanamaz; aksi halde musteri
   yonetilemez hale gelir ve kurtarmak icin sunucuya girmek gerekirdi.
2. Ozellestirme YAPILMAMISSA varsayilan roller aynen calisir. Yetki
   sistemi acilmasi gereken bir sey degil; zaten calisiyor.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import WorkspaceRole
from app.models.yetki import RoleGrant


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
    Izin("yetki.duzenle", "Ekip", "Yetki ayarlarını düzenle",
         "Bu sayfadaki izinleri değiştirir. Dikkatli verin."),
)

IZIN_ANAHTARLARI = frozenset(i.anahtar for i in IZINLER)
IZIN_SOZLUGU = {i.anahtar: i for i in IZINLER}

#: Panelde gosterilecek grup sirasi.
GRUPLAR = tuple(dict.fromkeys(i.grup for i in IZINLER))


# VARSAYILAN DAGILIM
#
# Bugunku davranisin BIREBIR ayni kalmasi icin hazirlandi: hicbir
# ozellestirme yapilmadiginda sistem eskisi gibi calisir.
VARSAYILAN: dict[WorkspaceRole, frozenset[str]] = {
    WorkspaceRole.OWNER: IZIN_ANAHTARLARI,
    WorkspaceRole.ADMIN: IZIN_ANAHTARLARI,
    WorkspaceRole.STRATEGIST: frozenset({
        "marka.duzenle", "kampanya.yonet", "hesap.gor",
        "icerik.uret", "icerik.duzenle", "icerik.onaya_sun",
        "takvim.gor", "takvim.planla",
        "rapor.gor", "rapor.hazirla", "rapor.sun",
        "otomasyon.calistir", "ekip.gor",
    }),
    WorkspaceRole.EDITOR: frozenset({
        "hesap.gor", "icerik.duzenle", "takvim.gor",
        "rapor.gor", "rapor.hazirla", "ekip.gor",
    }),
    WorkspaceRole.VIEWER: frozenset({
        "hesap.gor", "takvim.gor", "rapor.gor", "ekip.gor",
    }),
}

#: Sahibin izinleri KISITLANAMAZ. Aksi halde musteri yonetilemez hale
#: gelir ve duzeltmek icin sunucuya girmek gerekirdi.
KISITLANAMAZ_ROL = WorkspaceRole.OWNER


class YetkiHatasi(Exception):
    """Yetki ayarinda kurala takilan islem."""


def _ozellestirmeler(db: Session, workspace_id: uuid.UUID) -> dict[tuple[str, str], bool]:
    satirlar = db.execute(
        select(RoleGrant).where(RoleGrant.workspace_id == workspace_id)
    ).scalars().all()
    return {(s.role.value, s.permission): s.allowed for s in satirlar}


def rol_izinleri(
    db: Session, workspace_id: uuid.UUID, rol: WorkspaceRole
) -> frozenset[str]:
    """Bir rolun bu musterideki GECERLI izinleri."""
    if rol is KISITLANAMAZ_ROL:
        return IZIN_ANAHTARLARI

    temel = set(VARSAYILAN.get(rol, frozenset()))
    for (rol_degeri, izin), acik in _ozellestirmeler(db, workspace_id).items():
        if rol_degeri != rol.value or izin not in IZIN_ANAHTARLARI:
            continue
        if acik:
            temel.add(izin)
        else:
            temel.discard(izin)
    return frozenset(temel)


def izin_var_mi(
    db: Session, workspace_id: uuid.UUID, rol: WorkspaceRole, izin: str
) -> bool:
    """Bu rol, bu musteride bu isi yapabilir mi?"""
    if izin not in IZIN_ANAHTARLARI:
        # Tanimsiz izin ASLA verilmez: yazim hatasi sessizce kapi acmasin.
        raise YetkiHatasi(f"Tanımsız izin: {izin}")
    return izin in rol_izinleri(db, workspace_id, rol)


def izinleri_yaz(
    db: Session,
    workspace_id: uuid.UUID,
    rol: WorkspaceRole,
    izinler: set[str],
) -> None:
    """Bir rolun izinlerini YENIDEN yazar.

    Varsayilanla ayni olan satirlar SAKLANMAZ: boylece varsayilan
    degistiginde ozellestirilmemis roller yeni varsayilani alir.
    """
    if rol is KISITLANAMAZ_ROL:
        raise YetkiHatasi(
            "Sahip rolünün izinleri kısıtlanamaz. Müşteriyi yönetebilecek "
            "en az bir rol her zaman kalmalıdır."
        )

    bilinmeyen = izinler - IZIN_ANAHTARLARI
    if bilinmeyen:
        raise YetkiHatasi(f"Tanımsız izin: {', '.join(sorted(bilinmeyen))}")

    varsayilan = VARSAYILAN.get(rol, frozenset())
    mevcut = {
        s.permission: s
        for s in db.execute(
            select(RoleGrant).where(
                RoleGrant.workspace_id == workspace_id,
                RoleGrant.role == rol,
            )
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
            db.add(RoleGrant(
                workspace_id=workspace_id, role=rol,
                permission=izin, allowed=istenen,
            ))
    db.flush()


def varsayilana_don(db: Session, workspace_id: uuid.UUID, rol: WorkspaceRole) -> None:
    """Bu rolun ozellestirmelerini siler."""
    for satir in db.execute(
        select(RoleGrant).where(
            RoleGrant.workspace_id == workspace_id,
            RoleGrant.role == rol,
        )
    ).scalars().all():
        db.delete(satir)
    db.flush()


def matris(db: Session, workspace_id: uuid.UUID) -> list[dict]:
    """Panel icin: her izin x her rol tablosu."""
    roller = list(WorkspaceRole)
    gecerli = {r: rol_izinleri(db, workspace_id, r) for r in roller}
    ozel = _ozellestirmeler(db, workspace_id)

    satirlar = []
    for izin in IZINLER:
        satirlar.append({
            "anahtar": izin.anahtar,
            "grup": izin.grup,
            "ad": izin.ad,
            "aciklama": izin.aciklama,
            "roller": [
                {
                    "rol": r.value,
                    "var": izin.anahtar in gecerli[r],
                    "kilitli": r is KISITLANAMAZ_ROL,
                    "ozellestirilmis": (r.value, izin.anahtar) in ozel,
                }
                for r in roller
            ],
        })
    return satirlar
