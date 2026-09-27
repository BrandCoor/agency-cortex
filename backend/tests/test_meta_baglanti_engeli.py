"""Meta baglantisi: tutarsiz ayarda DENEME YAPILMAZ.

OLAY: Kullanici Instagram hesabini baglamaya calisti. Meta izin ekrani
acildi, izni verdi, uygulama Facebook hesabina baglandi - sonra anahtar
degisimi su hatayla kirildi:

    "Meta anahtari gecersiz: Error validating client secret"

Panelde bir tutarsizlik UYARISI vardi ama dugme yine de calisiyordu.
Uyari gostermek yetmedi: kullanici zaman kaybetti ve Meta tarafinda
yarim bir yetkilendirme kaldi.

Artik hata DENEMEDEN ONCE ve duzeltilecek alanin adiyla soyleniyor.
"""

from __future__ import annotations

from app.platforms.meta_ayar import (
    MetaAyarlari,
    baglanmaya_hazir_mi,
    tutarsiz_alanlar,
)

FACEBOOK_IZIN = "https://www.facebook.com/v21.0/dialog/oauth"
INSTAGRAM_ANAHTAR = "https://api.instagram.com/oauth/access_token"
INSTAGRAM_IZIN = "https://www.instagram.com/oauth/authorize"
INSTAGRAM_VERI = "https://graph.instagram.com/v26.0/"


def _ayar(**degisiklik) -> MetaAyarlari:
    temel = {
        "app_id": "1587998600005598",
        "app_secret": "gizli",
        "redirect_uri": "https://agencycortex.tech/api/v1/oauth/meta/callback",
        "api_version": "v26.0",
        "authorize_url": INSTAGRAM_IZIN,
        "token_url": INSTAGRAM_ANAHTAR,
        "graph_base_url": INSTAGRAM_VERI,
        "scopes": ["instagram_business_basic"],
    }
    temel.update(degisiklik)
    return MetaAyarlari(**temel)


# --- Tutarli yapilandirma -----------------------------------------------------

def test_tutarli_ayarda_baglanma_serbest():
    hazir, engel = baglanmaya_hazir_mi(_ayar())
    assert hazir is True
    assert engel is None


def test_tutarli_ayarda_tutarsizlik_bildirilmiyor():
    assert tutarsiz_alanlar(_ayar()) == {}


# --- Kullanicinin yasadigi durum ---------------------------------------------

def test_izin_facebook_anahtar_instagram_ise_baglanma_durduruluyor():
    """Kullanicinin yasadigi tam durum: izin ekrani facebook, anahtar ucu instagram."""
    hazir, engel = baglanmaya_hazir_mi(_ayar(authorize_url=FACEBOOK_IZIN))
    assert hazir is False
    assert engel is not None
    # Hangi ALANIN duzeltilecegi yaziyor.
    assert "META_AUTHORIZE_URL" in engel
    assert "META_TOKEN_URL" in engel
    # Kullanicinin gordugu hata mesaji da yaziyor; ayni sey oldugunu anlasin.
    assert "Error validating client secret" in engel


def test_tutarsiz_alanlar_tek_tek_bildiriliyor():
    alanlar = tutarsiz_alanlar(_ayar(authorize_url=FACEBOOK_IZIN))
    assert alanlar["İzin ekranı (META_AUTHORIZE_URL)"] == "facebook.com"
    assert alanlar["Anahtar değişimi (META_TOKEN_URL)"] == "instagram.com"


def test_eksik_deger_varsa_baglanma_durduruluyor():
    hazir, engel = baglanmaya_hazir_mi(_ayar(app_secret=""))
    assert hazir is False
    assert "META_APP_SECRET" in engel


# --- Hata mesaji ise yarar bilgi tasimali ------------------------------------

def test_hata_mesaji_hangi_uca_gidildigini_soyluyor():
    """"Error validating client secret" tek basina hangi alanin yanlis
    oldugunu SOYLEMEZ: ayni mesaj, anahtar yanlisken de, anahtar dogru
    ama yanlis aileden bir uca giderken de cikar."""
    import httpx

    from app.platforms.base import TokenExpired
    from app.platforms.meta import MetaAdapter

    adaptor = MetaAdapter(ayarlar=_ayar())
    yanit = httpx.Response(
        400,
        json={"error": {
            "type": "OAuthException",
            "code": 1,
            "message": "Error validating client secret.",
        }},
        request=httpx.Request("POST", INSTAGRAM_ANAHTAR),
    )

    try:
        adaptor._handle_error(yanit, uc=INSTAGRAM_ANAHTAR)
    except TokenExpired as hata:
        assert INSTAGRAM_ANAHTAR in str(hata)
        assert "1587998600005598" in str(hata)
    else:
        raise AssertionError("Hata firlatilmadi.")
