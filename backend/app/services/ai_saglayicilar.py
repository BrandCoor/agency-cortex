"""Yapay zeka saglayicilarinin ve gorev dagiliminin yonetimi.

IKI KURAL BU DOSYANIN TAMAMINI BELIRLER:

1. SINANMAMIS SAGLAYICI GOREVE ATANMAZ.
   "Etkin" isaretlemek yetmez; son sinamanin BASARILI olmasi gerekir.
   Aksi halde panelde hazir gorunen bir saglayici, ilk gercek iste
   anlasilmaz bir hatayla cokerdi.

2. ANAHTARLAR BURADA DURMAZ.
   Gizli degerler sifreli ayar tablosunda (sistem_ayarlari) tutulur.
   Bu dosya yalnizca hangi ayardan okunacagini bilir.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.base import AIProvider, AIProviderError
from app.ai.claude import ClaudeProvider
from app.ai.gemini import GeminiProvider
from app.ai.manus import ManusProvider
from app.ai.openai_uyumlu import OpenAIUyumluProvider
from app.core.logging_config import get_logger
from app.models.ai_saglayici import AISaglayici, GorevAtamasi, SaglayiciTuru
from app.services.sistem_ayarlari import OZEL_AI_ONEKI, deger_oku, deger_sil, deger_yaz

log = get_logger("ai_saglayicilar")


class SaglayiciHatasi(Exception):
    """Kullaniciya gosterilecek saglayici hatasi."""


@dataclass(frozen=True)
class GorevTanimi:
    """Bir AI gorev turunun panelde nasil anlatildigi."""

    kod: str
    ad: str
    aciklama: str
    varsayilan: str


#: Panelde gosterilen AI gorev turleri.
#
# BURADA YALNIZCA GERCEKTEN CALISAN ISLER DURUR.
#
# Once bu listede uc is daha vardi: "stratejik yorum", "marka dili
# denetimi" ve "toplu siniflandirma". Uculu de hicbir kod tarafindan
# CAGRILMIYORDU: panelde secilebiliyor, saglayici atanabiliyordu ama
# hicbir zaman calismiyorlardi. Bir ayari degistirip hicbir sey
# olmamasi, ayarin bozuk oldugunu dusundurur.
#
# `tests/test_ai_gorev_butunlugu.py` bu listenin koddaki gercek
# cagrilarla ayni kalmasini dogrular; listeye calismayan bir is
# eklenemez.
GOREVLER: tuple[GorevTanimi, ...] = (
    GorevTanimi(
        "content_script", "İçerik senaryosu",
        "Paylaşım fikri ve senaryo metni üretir (WF-03).", "claude",
    ),
    GorevTanimi(
        "trend_research", "Trend araştırması",
        "Sektörde öne çıkan konuları araştırır (WF-02).", "manus",
    ),
    GorevTanimi(
        "competitor_research", "Rakip araştırması",
        "İzlenen rakip hesapların hareketlerini araştırır (WF-06).", "manus",
    ),
    GorevTanimi(
        "competitor_discovery", "Rakip keşfi",
        "Marka bilgisinden yola çıkarak aday rakip hesapları bulur (WF-07).",
        "manus",
    ),
)

GOREV_KODLARI = {g.kod for g in GOREVLER}

#: Kurulumda olusturulan saglayicilar. Silinemezler; kapatilabilirler.
YERLESIKLER: tuple[dict, ...] = (
    {
        "anahtar": "claude", "ad": "Claude (Anthropic)",
        "tur": SaglayiciTuru.ANTHROPIC, "anahtar_ayari": "ANTHROPIC_API_KEY",
    },
    {
        "anahtar": "gemini", "ad": "Gemini (Google)",
        "tur": SaglayiciTuru.GEMINI, "anahtar_ayari": "GEMINI_API_KEY",
    },
    {
        "anahtar": "manus", "ad": "Manus",
        "tur": SaglayiciTuru.MANUS, "anahtar_ayari": "MANUS_API_KEY",
    },
)

ANAHTAR_BICIMI = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")


# --- Kurulum -----------------------------------------------------------------

def varsayilanlari_kur(db: Session) -> None:
    """Yerlesik saglayicilari ve varsayilan gorev dagilimini olusturur.

    Tekrar calistirilabilir: var olani DEGISTIRMEZ. Aksi halde her
    kurulumda kullanicinin yaptigi secimler geri alinirdi.
    """
    mevcut = {s.anahtar for s in db.execute(select(AISaglayici)).scalars()}
    for tanim in YERLESIKLER:
        if tanim["anahtar"] in mevcut:
            continue
        db.add(AISaglayici(
            anahtar=tanim["anahtar"], ad=tanim["ad"], tur=tanim["tur"],
            anahtar_ayari=tanim["anahtar_ayari"], yerlesik=True, etkin=False,
        ))

    atanmis = {a.gorev_turu for a in db.execute(select(GorevAtamasi)).scalars()}
    for gorev in GOREVLER:
        if gorev.kod not in atanmis:
            db.add(GorevAtamasi(
                gorev_turu=gorev.kod, saglayici_anahtari=gorev.varsayilan
            ))
    db.flush()


# --- Okuma -------------------------------------------------------------------

def listele(db: Session) -> list[AISaglayici]:
    return list(db.execute(
        select(AISaglayici).order_by(AISaglayici.yerlesik.desc(), AISaglayici.ad)
    ).scalars())


def getir(db: Session, anahtar: str) -> AISaglayici | None:
    return db.execute(
        select(AISaglayici).where(AISaglayici.anahtar == anahtar)
    ).scalar_one_or_none()


def atamalar(db: Session) -> dict[str, str]:
    """Gorev turu -> saglayici anahtari."""
    return {
        a.gorev_turu: a.saglayici_anahtari
        for a in db.execute(select(GorevAtamasi)).scalars()
    }


def kullanilabilir_saglayicilar(db: Session) -> list[AISaglayici]:
    """Bir goreve ATANABILECEK saglayicilar: etkin VE sinamasi basarili."""
    return [s for s in listele(db) if s.kullanilabilir]


# --- Saglayici ornegi --------------------------------------------------------

def ornek_olustur(db: Session, saglayici: AISaglayici) -> AIProvider:
    """Kayittan calisan bir saglayici nesnesi uretir."""
    anahtar_degeri = (
        deger_oku(db, saglayici.anahtar_ayari) if saglayici.anahtar_ayari else None
    )
    if saglayici.tur is SaglayiciTuru.ANTHROPIC:
        return ClaudeProvider(api_key=anahtar_degeri)
    if saglayici.tur is SaglayiciTuru.GEMINI:
        return GeminiProvider(api_key=anahtar_degeri, model=saglayici.model or None)
    if saglayici.tur is SaglayiciTuru.MANUS:
        return ManusProvider(api_key=anahtar_degeri)
    if saglayici.tur is SaglayiciTuru.OPENAI_UYUMLU:
        return OpenAIUyumluProvider(
            anahtar_adi=saglayici.anahtar,
            taban_url=saglayici.taban_url or "",
            model=saglayici.model or "",
            api_key=anahtar_degeri,
        )
    raise SaglayiciHatasi(f"Bilinmeyen sağlayıcı türü: {saglayici.tur}")


# --- Degistirme --------------------------------------------------------------

def etkinlik_ayarla(db: Session, anahtar: str, etkin: bool) -> AISaglayici:
    saglayici = getir(db, anahtar)
    if saglayici is None:
        raise SaglayiciHatasi("Sağlayıcı bulunamadı.")
    saglayici.etkin = etkin
    db.flush()
    log.info("ai_saglayici_etkinlik", anahtar=anahtar, etkin=etkin)
    return saglayici


def sina(db: Session, anahtar: str) -> tuple[bool, str]:
    """GERCEK bir cagri yapar ve sonucu kaydeder.

    Sonuc kaydedilir cunku "bu saglayici calisiyor mu?" sorusunun cevabi
    panelde her an gorunmelidir; her sayfa acilisinda para harcayan bir
    cagri yapmak dogru olmazdi.
    """
    saglayici = getir(db, anahtar)
    if saglayici is None:
        raise SaglayiciHatasi("Sağlayıcı bulunamadı.")

    try:
        calisan = ornek_olustur(db, saglayici)
        basarili, mesaj = calisan.health_check()
    except AIProviderError as hata:
        basarili, mesaj = False, str(hata)
    except Exception as hata:  # noqa: BLE001 - beklenmeyen hata da GORUNMELI
        log.warning("ai_sinama_beklenmedik", anahtar=anahtar, hata=str(hata))
        basarili, mesaj = False, f"Beklenmeyen hata: {hata}"

    saglayici.son_sinama_zamani = datetime.now(UTC)
    saglayici.son_sinama_basarili = basarili
    saglayici.son_sinama_mesaji = (mesaj or "")[:1000]
    db.flush()
    log.info("ai_saglayici_sinandi", anahtar=anahtar, basarili=basarili)
    return basarili, saglayici.son_sinama_mesaji


def ozel_ekle(
    db: Session, *, anahtar: str, ad: str, taban_url: str, model: str,
    api_anahtari: str, user_id: uuid.UUID | None,
) -> AISaglayici:
    """"OpenAI uyumlu" yeni bir saglayici ekler."""
    anahtar = (anahtar or "").strip().lower()
    if not ANAHTAR_BICIMI.match(anahtar):
        raise SaglayiciHatasi(
            "Kısa ad yalnızca küçük harf, rakam ve tire içerebilir "
            "(3-40 karakter). Örnek: yerel-model"
        )
    if getir(db, anahtar) is not None:
        raise SaglayiciHatasi(f"'{anahtar}' kısa adı zaten kullanılıyor.")

    taban_url = (taban_url or "").strip()
    if not taban_url.startswith("https://"):
        # http:// kabul edilseydi API anahtari ag uzerinde ACIK giderdi.
        raise SaglayiciHatasi("Taban adres https:// ile başlamalıdır.")
    if not (model or "").strip():
        raise SaglayiciHatasi("Model adı boş olamaz.")
    if not (api_anahtari or "").strip():
        raise SaglayiciHatasi("API anahtarı boş olamaz.")

    ayar_adi = f"{OZEL_AI_ONEKI}{anahtar.upper().replace('-', '_')}"
    deger_yaz(db, ayar_adi, api_anahtari, user_id=user_id)

    saglayici = AISaglayici(
        anahtar=anahtar, ad=(ad or anahtar).strip()[:120],
        tur=SaglayiciTuru.OPENAI_UYUMLU, taban_url=taban_url.rstrip("/"),
        model=model.strip(), anahtar_ayari=ayar_adi, yerlesik=False, etkin=False,
    )
    db.add(saglayici)
    db.flush()
    log.info("ai_saglayici_eklendi", anahtar=anahtar)
    return saglayici


def sil(db: Session, anahtar: str) -> None:
    """Kullanicinin ekledigi bir saglayiciyi kaldirir."""
    saglayici = getir(db, anahtar)
    if saglayici is None:
        raise SaglayiciHatasi("Sağlayıcı bulunamadı.")
    if saglayici.yerlesik:
        raise SaglayiciHatasi(
            "Yerleşik sağlayıcılar silinemez; kapatabilirsiniz."
        )

    kullanan = [g for g, s in atamalar(db).items() if s == anahtar]
    if kullanan:
        adlar = ", ".join(
            next(x.ad for x in GOREVLER if x.kod == k) for k in kullanan
        )
        raise SaglayiciHatasi(
            f"Bu sağlayıcı şu görevlerde kullanılıyor: {adlar}. "
            "Önce başka bir sağlayıcı atayın."
        )

    if saglayici.anahtar_ayari:
        deger_sil(db, saglayici.anahtar_ayari)
    db.delete(saglayici)
    db.flush()
    log.info("ai_saglayici_silindi", anahtar=anahtar)


def atama_yap(db: Session, gorev_turu: str, saglayici_anahtari: str) -> None:
    """Bir gorevi bir saglayiciya atar."""
    if gorev_turu not in GOREV_KODLARI:
        raise SaglayiciHatasi(f"Bilinmeyen görev türü: {gorev_turu}")

    saglayici = getir(db, saglayici_anahtari)
    if saglayici is None:
        raise SaglayiciHatasi("Sağlayıcı bulunamadı.")
    if not saglayici.kullanilabilir:
        # Bu kontrol UI'da da var ama BURADA olmasi sart: form disindan
        # gonderilen bir istek de ayni kurala takilmali.
        raise SaglayiciHatasi(
            f"'{saglayici.ad}' henüz kullanılamaz. Önce açın ve "
            "\"Bağlantıyı sına\" ile çalıştığını doğrulayın."
        )

    kayit = db.execute(
        select(GorevAtamasi).where(GorevAtamasi.gorev_turu == gorev_turu)
    ).scalar_one_or_none()
    if kayit is None:
        db.add(GorevAtamasi(
            gorev_turu=gorev_turu, saglayici_anahtari=saglayici_anahtari
        ))
    else:
        kayit.saglayici_anahtari = saglayici_anahtari
    db.flush()
    log.info("ai_gorev_atandi", gorev=gorev_turu, saglayici=saglayici_anahtari)
