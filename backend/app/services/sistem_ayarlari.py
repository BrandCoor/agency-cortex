"""Panelden girilen sistem ayarlarini okur ve yazar.

TASARIM:
- Deger veritabaninda YALNIZCA sifreli durur (Fernet).
- Okuma sirasinda cozulur; cagiran taraf dogrudan kullanir.
- Panel tam degeri HICBIR ZAMAN geri gostermez; yalnizca "tanimli mi" ve
  son dort karakter gosterilir.
- Veritabaninda deger yoksa ortam degiskenine duser. Boylece sunucuda
  tanimli degerler calismaya devam eder.
"""

from __future__ import annotations

import os
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.core.security import decrypt_secret, encrypt_secret
from app.models.ops import SystemSetting

log = get_logger("sistem_ayarlari")


class AyarTanimi:
    """Panelde gosterilecek bir ayarin tanimi."""

    def __init__(
        self, anahtar: str, etiket: str, aciklama: str, *,
        gizli: bool = True, acar: str = "", grup: str = "Anahtarlar",
        dogrulama: str = "", ornek: str = "",
    ):
        self.anahtar = anahtar
        self.etiket = etiket
        self.aciklama = aciklama
        # gizli=False olanlar (surum, adres gibi) panelde acikca gosterilir.
        self.gizli = gizli
        # Bu ayar girilince sistemde NE calisir hale gelir.
        # Kullanici "girdim, ne oldu?" diye sormasin diye.
        self.acar = acar
        # Panelde hangi baslik altinda gosterilecek.
        self.grup = grup
        # Bicim dogrulamasi: "url", "surum", "kapsam" veya bos.
        self.dogrulama = dogrulama
        # Kullaniciya gosterilecek ornek deger.
        self.ornek = ornek


# Panelde gosterilen ayarlar. Sira, doldurma sirasini da anlatir.
AYARLAR: list[AyarTanimi] = [
    AyarTanimi(
        "ANTHROPIC_API_KEY", "Claude API anahtarı",
        "İçerik senaryolarını ve rapor yorumlarını üretir. "
        "console.anthropic.com → API Keys.",
        acar="WF-03 İçerik zekâsı iş akışı ve panelden içerik üretimi",
    ),
    AyarTanimi(
        "MANUS_API_KEY", "Manus API anahtarı",
        "Trend ve rakip araştırması yapar. manus.ai hesabınızdan alınır.",
        acar="WF-02 Trend araştırması iş akışı",
    ),
    AyarTanimi(
        "META_APP_ID", "Meta uygulama kimliği",
        "Müşterilerin Instagram hesaplarını bağlamak için. Tüm müşteriler "
        "için TEK uygulama yeterlidir. developers.facebook.com → uygulamanız "
        "→ App ID. Gizli değildir.",
        gizli=False,
        acar="Müşteri ekranındaki \"Instagram hesabı bağla\" düğmesi",
    ),
    AyarTanimi(
        "META_APP_SECRET", "Meta uygulama gizli anahtarı",
        "Yukarıdaki uygulamanın gizli anahtarı (App Secret).",
        acar="Müşteri ekranındaki \"Instagram hesabı bağla\" düğmesi "
             "ve WF-01 ile WF-05 iş akışları",
    ),
    AyarTanimi(
        "GEMINI_API_KEY", "Gemini API anahtarı",
        "Toplu sınıflandırma işlerinde kullanılır (ucuz ve hızlı model). "
        "aistudio.google.com → Get API key.",
        acar="Toplu sınıflandırma (bulk_classification) görevleri",
    ),

    # --- Meta bağlantı ayrıntıları ------------------------------------------
    #
    # BU ALANLAR BİLEREK GERİ GETİRİLDİ.
    #
    # Bir süre panelden kaldırılmışlardı: "kullanıcının dolduracağı değer
    # değil, doğrulanmış sabitler" diye. Bu YANLIŞTI. Meta bu değerleri
    # değiştirebiliyor ve resmî dokümana erişimi olan kişi kullanıcının
    # KENDİSİ. Alanları kaldırmak, kullanıcıyı geliştiriciye bağımlı
    # bırakıyordu: Instagram bağlama hata verdiğinde düzeltecek yer yoktu.
    #
    # Kaldırılma gerekçesi "yanlış değer sessizce bağlantıyı bozabilir"
    # idi. Bu risk, alanları gizleyerek değil, BİÇİM DOĞRULAMASI ve
    # "şu an hangi değer geçerli" göstergesiyle çözülür.
    AyarTanimi(
        "META_API_VERSION", "Meta Graph API sürümü",
        "Kullanılacak Graph API sürümü. Meta'nın sürüm sayfasından "
        "doğrulayın. Boş bırakılırsa sistemdeki varsayılan kullanılır.",
        gizli=False, grup="Meta bağlantı ayrıntıları",
        dogrulama="surum", ornek="v23.0",
        acar="Meta uçlarına yapılan tüm isteklerin sürümü",
    ),
    AyarTanimi(
        "META_AUTHORIZE_URL", "İzin ekranı adresi",
        "Kullanıcının yönlendirileceği izin adresi. "
        "\"Invalid platform app\" hatası alıyorsanız bu adres ile "
        "uygulama kimliğinin aynı ürüne ait olduğunu kontrol edin.",
        gizli=False, grup="Meta bağlantı ayrıntıları",
        dogrulama="url", ornek="https://www.instagram.com/oauth/authorize",
        acar="\"Instagram hesabı bağla\" düğmesinin gittiği adres",
    ),
    AyarTanimi(
        "META_TOKEN_URL", "Anahtar değişim adresi",
        "İzin kodunun erişim anahtarına çevrildiği uç.",
        gizli=False, grup="Meta bağlantı ayrıntıları",
        dogrulama="url", ornek="https://api.instagram.com/oauth/access_token",
        acar="İzin ekranından dönüşte hesabın bağlanması",
    ),
    AyarTanimi(
        "META_GRAPH_BASE_URL", "Veri uçlarının kök adresi",
        "Metrik ve profil verisinin çekildiği kök adres.",
        gizli=False, grup="Meta bağlantı ayrıntıları",
        dogrulama="url", ornek="https://graph.instagram.com/v23.0/",
        acar="WF-01 veri senkronu ve tüm metrik çekimleri",
    ),
    AyarTanimi(
        "META_SCOPES", "İstenecek izinler",
        "Virgülle ayrılmış izin adları. Yayın izni İSTENMEZ: bu sürümde "
        "sistem hiçbir şeyi kendisi paylaşmaz.",
        gizli=False, grup="Meta bağlantı ayrıntıları",
        dogrulama="kapsam",
        ornek="instagram_business_basic,instagram_business_manage_insights",
        acar="İzin ekranında hesap sahibinden istenen yetkiler",
    ),
]

#: Panelde gosterilecek grup sirasi.
AYAR_GRUPLARI = tuple(dict.fromkeys(a.grup for a in AYARLAR))

# GEMINI_API_KEY kaldirilmadi, ASAGIDA tanimli.
#
# ONCEDEN kaldirilmisti cunku Gemini saglayicisi yazilmamisti. Artik
# yazildi; anahtar girilince gercekten calisiyor.
KALDIRILAN_AYARLAR: frozenset[str] = frozenset()

AYAR_ANAHTARLARI = {a.anahtar for a in AYARLAR}


def deger_oku(db: Session, anahtar: str) -> str | None:
    """Ayari once veritabanindan, yoksa ortam degiskeninden okur."""
    kayit = db.execute(
        select(SystemSetting).where(SystemSetting.anahtar == anahtar)
    ).scalar_one_or_none()
    if kayit is not None:
        try:
            return decrypt_secret(kayit.sifreli_deger)
        except Exception:  # noqa: BLE001 - cozulemeyen deger yokmus gibi davranir
            # Sifre cozulemiyorsa (ornegin ENCRYPTION_KEY degistiyse) degeri
            # uydurmak yerine "tanimsiz" deriz. Sessizce yanlis deger
            # dondurmek, teshisi imkansiz hatalara yol acar.
            log.error("ayar_cozulemedi", anahtar=anahtar)
            return None
    return os.environ.get(anahtar) or None


def deger_yaz(db: Session, anahtar: str, deger: str, *, user_id: uuid.UUID | None) -> None:
    """Ayari sifreleyerek kaydeder. Deger loglanmaz."""
    if anahtar not in AYAR_ANAHTARLARI:
        raise ValueError(f"Bilinmeyen ayar: {anahtar}")
    deger = deger.strip()
    if not deger:
        raise ValueError("Değer boş olamaz.")

    kayit = db.execute(
        select(SystemSetting).where(SystemSetting.anahtar == anahtar)
    ).scalar_one_or_none()
    if kayit is None:
        kayit = SystemSetting(anahtar=anahtar, sifreli_deger="")
        db.add(kayit)

    kayit.sifreli_deger = encrypt_secret(deger)
    kayit.son_dort = deger[-4:] if len(deger) >= 4 else None
    kayit.degistiren_user_id = user_id
    # Yalnizca HANGI ayarin degistigi loglanir; degerin kendisi asla.
    log.info("ayar_guncellendi", anahtar=anahtar, user_id=str(user_id) if user_id else None)


def deger_sil(db: Session, anahtar: str) -> bool:
    kayit = db.execute(
        select(SystemSetting).where(SystemSetting.anahtar == anahtar)
    ).scalar_one_or_none()
    if kayit is None:
        return False
    db.delete(kayit)
    log.info("ayar_silindi", anahtar=anahtar)
    return True


def durum_listesi(db: Session) -> list[dict]:
    """Panelde gosterilecek durum. TAM DEGER ICERMEZ."""
    kayitlar = {
        k.anahtar: k
        for k in db.execute(select(SystemSetting)).scalars().all()
    }
    satirlar = []
    for tanim in AYARLAR:
        kayit = kayitlar.get(tanim.anahtar)
        ortamda = bool(os.environ.get(tanim.anahtar))
        satirlar.append(
            {
                "anahtar": tanim.anahtar,
                "etiket": tanim.etiket,
                "aciklama": tanim.aciklama,
                "gizli": tanim.gizli,
                "acar": tanim.acar,
                "tanimli": kayit is not None or ortamda,
                "kaynak": "panel" if kayit is not None else ("sunucu" if ortamda else None),
                "son_dort": kayit.son_dort if kayit else None,
                "guncellendi": kayit.updated_at if kayit else None,
                "grup": tanim.grup,
                "ornek": tanim.ornek,
                # SU AN HANGI DEGER GECERLI.
                #
                # Gizli olmayan ayarlarda bunu gostermek sart: kullanici
                # bir deger girdiginde "gecerli oldu mu, yoksa varsayilan
                # mi kullaniliyor?" sorusunu baska turlu yanitlayamaz.
                "gecerli_deger": (
                    None if tanim.gizli else _gecerli_deger(db, tanim.anahtar)
                ),
            }
        )
    return satirlar


def _gecerli_deger(db: Session, anahtar: str) -> str | None:
    """Sistemin SU AN kullandigi deger (gizli olmayan ayarlar icin)."""
    if anahtar.startswith("META_"):
        # Meta ayarlari tek bir yerden cozulur; panel o sonucu gosterir.
        from app.platforms.meta_ayar import meta_ayarlarini_oku

        ayar = meta_ayarlarini_oku()
        esleme = {
            "META_APP_ID": ayar.app_id,
            "META_API_VERSION": ayar.api_version,
            "META_AUTHORIZE_URL": ayar.authorize_url,
            "META_TOKEN_URL": ayar.token_url,
            "META_GRAPH_BASE_URL": ayar.graph_base_url,
            "META_SCOPES": ",".join(ayar.scopes),
        }
        return esleme.get(anahtar) or None
    return deger_oku(db, anahtar)


# --- Bicim dogrulamasi -------------------------------------------------------
#
# Alanlar panelde oldugu icin YANLIS deger girilebilir. Yanlis deger
# sessizce kabul edilirse baglanti bozulur ve nedeni hicbir yerde
# gorunmez. Bu yuzden kaydetmeden ONCE bicim kontrol edilir.
#
# Dikkat: bu kontrol degerin DOGRU oldugunu kanitlamaz, yalnizca
# ACIKCA YANLIS olani engeller. Dogrulugu Meta'nin resmi dokumani
# belirler.

import re  # noqa: E402

_SURUM = re.compile(r"^v\d+\.\d+$")
_KAPSAM = re.compile(r"^[a-z0-9_]+(,[a-z0-9_]+)*$")


class AyarHatasi(ValueError):
    """Girilen deger beklenen bicimde degil."""


def dogrula(anahtar: str, deger: str) -> str:
    """Degeri temizler ve bicimini kontrol eder."""
    temiz = (deger or "").strip()
    tanim = next((a for a in AYARLAR if a.anahtar == anahtar), None)
    if tanim is None or not tanim.dogrulama or not temiz:
        return temiz

    if tanim.dogrulama == "surum":
        if not _SURUM.match(temiz):
            raise AyarHatasi(
                f"{tanim.etiket}: sürüm 'v' ile başlamalı ve nokta içermeli. "
                f"Örnek: {tanim.ornek}"
            )
    elif tanim.dogrulama == "url":
        if not temiz.startswith("https://"):
            raise AyarHatasi(
                f"{tanim.etiket}: adres https:// ile başlamalı. "
                f"Örnek: {tanim.ornek}"
            )
        if " " in temiz:
            raise AyarHatasi(f"{tanim.etiket}: adreste boşluk olamaz.")
    elif tanim.dogrulama == "kapsam":
        sade = temiz.replace(" ", "")
        if not _KAPSAM.match(sade):
            raise AyarHatasi(
                f"{tanim.etiket}: izinler virgülle ayrılmalı, boşluk ve "
                f"büyük harf olmamalı. Örnek: {tanim.ornek}"
            )
        # YAYIN IZNI ENGELLENIR.
        #
        # Bu surumde sistem hicbir seyi kendisi paylasmaz. Yayin izni
        # istemek, kullanmadigimiz bir yetkiyi hesap sahibinden istemek
        # olurdu; ayrica ileride bir hata yayina donusebilirdi.
        yasakli = [p for p in sade.split(",") if "publish" in p or "content_publish" in p]
        if yasakli:
            raise AyarHatasi(
                "Yayın izni istenemez: bu sürümde sistem hiçbir şeyi kendisi "
                f"paylaşmaz. Kaldırın: {', '.join(yasakli)}"
            )
        return sade

    return temiz
