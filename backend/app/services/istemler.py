"""Is akislarinin yapay zekaya verdigi sistem istemleri (prompt).

NEDEN BU DOSYA VAR
Istemler koda gomuluydu. "Trend arastirmasi daha cok bizim sektorumuze
baksin" demek, kod degisikligi ve yeniden kurulum gerektiriyordu. Oysa
istem metni URUN AYARIDIR: isini bilen bir insan okuyup duzeltebilmeli.

UC KURAL

1. KODDAKI METIN KAYBOLMAZ.
   Her yerlesik istemin koddaki hali VARSAYILAN olarak durur. Panelde
   "Varsayilana don" her zaman calisir; yanlis bir duzenleme sistemi
   kilitleyemez.

2. SURUM ARTAR.
   Uretilen her AI ciktisi hangi istem surumuyle uretildigini kaydeder.
   Surum artmasaydi "bu rapor neden boyle cikmis?" sorusunun cevabi
   kaybolurdu.

3. VERITABANI OKUNAMAZSA SISTEM DURMAZ.
   Okuma basarisiz olursa koddaki metne dusulur. Bir ayar tablosu
   yuzunden tum uretimi durdurmak dogru olmazdi; hata loglanir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models.istem import IstemSablonu

log = get_logger("istemler")


class IstemHatasi(Exception):
    """Kullaniciya gosterilecek istem hatasi."""


@dataclass(frozen=True)
class YerlesikIstem:
    kod: str
    ad: str
    akis: str
    aciklama: str
    metin: str


def _kod_metinleri() -> dict[str, str]:
    """Koddaki varsayilan istem metinleri.

    Ice aktarma FONKSIYON ICINDE yapilir: is_akislari bu dosyayi
    kullanacagi icin modul seviyesinde ice aktarim dairesel olurdu.
    """
    from app.services.content import SYSTEM_PROMPT
    from app.services.is_akislari import (
        RAKIP_KESFI_SISTEM_ISTEMI,
        RAKIP_SISTEM_ISTEMI,
        TREND_SISTEM_ISTEMI,
    )

    return {
        "content_script": SYSTEM_PROMPT,
        "trend_research": TREND_SISTEM_ISTEMI,
        "competitor_research": RAKIP_SISTEM_ISTEMI,
        "competitor_discovery": RAKIP_KESFI_SISTEM_ISTEMI,
    }


#: Panelde gosterilen yerlesik istemler. Metinleri kodda durur.
YERLESIK_TANIMLAR: tuple[tuple[str, str, str, str], ...] = (
    (
        "content_script", "İçerik senaryosu", "WF-03",
        "Paylaşım fikri ve platforma özel senaryo metni üretirken "
        "yapay zekâya verilen yönerge.",
    ),
    (
        "trend_research", "Trend araştırması", "WF-02",
        "Sektörde öne çıkan konuları araştırırken verilen yönerge.",
    ),
    (
        "competitor_research", "Rakip araştırması", "WF-06",
        "İzlenen rakip hesapların hareketlerini incelerken verilen yönerge.",
    ),
    (
        "competitor_discovery", "Rakip keşfi", "WF-07",
        "Marka bilgisinden yola çıkarak aday rakip hesapları bulurken "
        "verilen yönerge.",
    ),
)

YERLESIK_KODLAR = {t[0] for t in YERLESIK_TANIMLAR}
KOD_BICIMI = re.compile(r"^[a-z][a-z0-9_]{2,58}$")

#: Istem metni icin alt ve ust sinir.
#
# Alt sinir: uc kelimelik bir istem, modele hicbir sey anlatmaz ve
# ciktinin semaya uymamasina yol acar - kullanici sebebini anlamaz.
# Ust sinir: cok uzun istem her cagrida para yakar.
EN_AZ_UZUNLUK = 40
EN_COK_UZUNLUK = 20_000


def yerlesikler() -> list[YerlesikIstem]:
    metinler = _kod_metinleri()
    return [
        YerlesikIstem(kod=kod, ad=ad, akis=akis, aciklama=aciklama,
                      metin=metinler[kod])
        for kod, ad, akis, aciklama in YERLESIK_TANIMLAR
    ]


def varsayilanlari_kur(db: Session) -> None:
    """Yerlesik istemleri olusturur. Var olani DEGISTIRMEZ.

    Degistirseydi, her kurulum kullanicinin duzenlemelerini silerdi.
    """
    mevcut = {i.kod for i in db.execute(select(IstemSablonu)).scalars()}
    for tanim in yerlesikler():
        if tanim.kod in mevcut:
            continue
        db.add(IstemSablonu(
            kod=tanim.kod, ad=tanim.ad, akis=tanim.akis,
            aciklama=tanim.aciklama, metin=tanim.metin,
            surum=1, etkin=True, yerlesik=True,
        ))
    db.flush()


def listele(db: Session) -> list[IstemSablonu]:
    return list(db.execute(
        select(IstemSablonu).order_by(
            IstemSablonu.yerlesik.desc(), IstemSablonu.akis, IstemSablonu.ad
        )
    ).scalars())


def getir(db: Session, kod: str) -> IstemSablonu | None:
    return db.execute(
        select(IstemSablonu).where(IstemSablonu.kod == kod)
    ).scalar_one_or_none()


def metin_al(db: Session, kod: str) -> tuple[str, str]:
    """(istem metni, surum etiketi) doner.

    Panelde duzenlenmis metin varsa O kullanilir; yoksa koddaki
    varsayilana dusulur. Hicbir durumda bos istem donmez.
    """
    try:
        kayit = getir(db, kod)
    except Exception as hata:  # noqa: BLE001 - tablo okunamazsa koda duser
        log.warning("istem_okunamadi", kod=kod, hata=str(hata))
        kayit = None

    if kayit is not None and kayit.etkin and kayit.metin.strip():
        return kayit.metin, f"{kod}.v{kayit.surum}"

    varsayilan = _kod_metinleri().get(kod)
    if varsayilan is None:
        raise IstemHatasi(f"'{kod}' için tanımlı bir istem yok.")
    # "v0" bilerek: bu cikti PANELDEKI metinle degil, koddaki varsayilanla
    # uretilmistir. Ikisini ayni etiketle kaydetmek, sonradan "hangi metinle
    # uretilmis?" sorusunu cevapsiz birakirdi.
    return varsayilan, f"{kod}.v0"


def _dogrula(metin: str) -> str:
    metin = (metin or "").strip()
    if len(metin) < EN_AZ_UZUNLUK:
        raise IstemHatasi(
            f"İstem en az {EN_AZ_UZUNLUK} karakter olmalı. Çok kısa bir "
            "yönerge, modelin beklenen biçimde çıktı üretmemesine yol açar."
        )
    if len(metin) > EN_COK_UZUNLUK:
        raise IstemHatasi(
            f"İstem en fazla {EN_COK_UZUNLUK} karakter olabilir. Uzun istem "
            "her çağrıda ek maliyet demektir."
        )
    return metin


def guncelle(db: Session, kod: str, metin: str) -> IstemSablonu:
    """Metni degistirir ve SURUMU ARTIRIR."""
    kayit = getir(db, kod)
    if kayit is None:
        raise IstemHatasi("İstem bulunamadı.")
    yeni = _dogrula(metin)
    if yeni == kayit.metin:
        # Degismediyse surum artmamali; yoksa surum numarasi
        # "kac kez kaydete basildi" olurdu, "kac kez degisti" degil.
        return kayit
    kayit.metin = yeni
    kayit.surum += 1
    db.flush()
    log.info("istem_guncellendi", kod=kod, surum=kayit.surum)
    return kayit


def etkinlik_ayarla(db: Session, kod: str, etkin: bool) -> IstemSablonu:
    kayit = getir(db, kod)
    if kayit is None:
        raise IstemHatasi("İstem bulunamadı.")
    if kayit.yerlesik and not etkin:
        # Kapatilirsa koddaki varsayilana dusulur - yani istem yine
        # calisir. Kullanicinin "kapattim, artik kullanilmiyor"
        # sanmasi yanlis olurdu.
        raise IstemHatasi(
            "Yerleşik istemler kapatılamaz. Kapatılsaydı koddaki varsayılan "
            "metin kullanılmaya devam ederdi; \"kapattım\" demek yanıltıcı "
            "olurdu. Metni düzenleyin veya varsayılana döndürün."
        )
    kayit.etkin = etkin
    db.flush()
    return kayit


def varsayilana_don(db: Session, kod: str) -> IstemSablonu:
    """Koddaki metne geri doner. Surum yine ARTAR."""
    kayit = getir(db, kod)
    if kayit is None:
        raise IstemHatasi("İstem bulunamadı.")
    if not kayit.yerlesik:
        raise IstemHatasi(
            "Bu istemin kodda bir varsayılanı yok; sizin eklediğiniz bir istem."
        )
    varsayilan = _kod_metinleri()[kod]
    if varsayilan != kayit.metin:
        kayit.metin = varsayilan
        kayit.surum += 1
        db.flush()
        log.info("istem_varsayilana_dondu", kod=kod, surum=kayit.surum)
    return kayit


def ekle(db: Session, *, kod: str, ad: str, akis: str, aciklama: str,
         metin: str) -> IstemSablonu:
    """Kullanicinin kendi istemini ekler."""
    kod = (kod or "").strip().lower()
    if not KOD_BICIMI.match(kod):
        raise IstemHatasi(
            "Kod yalnızca küçük harf, rakam ve alt çizgi içerebilir "
            "(3-59 karakter). Örnek: kampanya_metni"
        )
    if getir(db, kod) is not None:
        raise IstemHatasi(f"'{kod}' kodu zaten kullanılıyor.")
    if not (ad or "").strip():
        raise IstemHatasi("Ad boş olamaz.")

    kayit = IstemSablonu(
        kod=kod, ad=ad.strip()[:160], akis=(akis or "").strip()[:20] or None,
        aciklama=(aciklama or "").strip(), metin=_dogrula(metin),
        surum=1, etkin=True, yerlesik=False,
    )
    db.add(kayit)
    db.flush()
    log.info("istem_eklendi", kod=kod)
    return kayit


def sil(db: Session, kod: str) -> None:
    kayit = getir(db, kod)
    if kayit is None:
        raise IstemHatasi("İstem bulunamadı.")
    if kayit.yerlesik:
        raise IstemHatasi(
            "Yerleşik istemler silinemez. Düzenleyebilir veya varsayılana "
            "döndürebilirsiniz."
        )
    db.delete(kayit)
    db.flush()
    log.info("istem_silindi", kod=kod)
