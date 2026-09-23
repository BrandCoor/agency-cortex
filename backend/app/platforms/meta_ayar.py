"""Meta (Instagram/Facebook) ayarlarinin tek kaynaktan okunmasi.

SORUN: Meta uygulama bilgileri panelden giriliyordu ama adaptor yalnizca
ORTAM DEGISKENLERINE bakiyordu. Kullanici anahtarlari panele girip
kaydediyor, hicbir sey degismiyordu - sessiz bir cikmaz sokak.

Bu dosya tek okuma yolunu tanimlar: once panel ayari, yoksa ortam
degiskeni, o da yoksa dogrulanmis varsayilan (surum, adresler).

GIZLI DEGER LOGLANMAZ.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging_config import get_logger

log = get_logger("meta_ayar")

#: Kullanicinin GERCEKTEN girmesi gereken degerler.
#: Digerleri (surum, adresler, izin kapsami) resmi dokumandan dogrulanmis
#: varsayilanlarla gelir; kullanicidan istenmez.
ZORUNLU_ALANLAR = ("META_APP_ID", "META_APP_SECRET", "META_REDIRECT_URI")


#: Panel ayarlarinin okunacagi oturum ureticisi.
#: Testlerde ayni baglantiya baglanabilmesi icin degistirilebilir
#: (test verisi henuz islenmediginden ayri bir baglanti onu goremez).
_oturum_uretici: Callable[[], Session] | None = None


def oturum_ureticiyi_ayarla(uretici: Callable[[], Session] | None):
    """Ayar okumasinin hangi oturumda yapilacagini degistirir (testler)."""
    global _oturum_uretici
    onceki = _oturum_uretici
    _oturum_uretici = uretici
    return onceki


def _panel_ayari(anahtar: str) -> str | None:
    """Panelden girilen degeri okur. Veritabanina ulasilamazsa None."""
    try:
        from app.core.db import SessionLocal
        from app.services.sistem_ayarlari import deger_oku

        uretici = _oturum_uretici or SessionLocal
        with uretici() as db:
            return deger_oku(db, anahtar) or None
    except Exception:  # noqa: BLE001 - ayar okunamazsa ortam degiskenine duseriz
        return None


def _oku(anahtar: str, varsayilan: str = "") -> str:
    """Once panel, sonra ortam degiskeni, sonra varsayilan."""
    deger = _panel_ayari(anahtar)
    if deger:
        return deger
    return os.environ.get(anahtar) or varsayilan


@dataclass(frozen=True)
class MetaAyarlari:
    app_id: str
    app_secret: str
    redirect_uri: str
    api_version: str
    authorize_url: str
    token_url: str
    graph_base_url: str
    scopes: list[str] = field(default_factory=list)

    @property
    def eksikler(self) -> list[str]:
        """Bağlantı için eksik olan zorunlu alanlar."""
        deger = {
            "META_APP_ID": self.app_id,
            "META_APP_SECRET": self.app_secret,
            "META_REDIRECT_URI": self.redirect_uri,
        }
        return [ad for ad, d in deger.items() if not d]

    @property
    def hazir(self) -> bool:
        """Gercek bir hesap baglanabilir mi?"""
        return not self.eksikler


def meta_ayarlarini_oku() -> MetaAyarlari:
    """Meta ayarlarini panel + ortam + dogrulanmis varsayilanlardan toplar."""
    ayarlar = get_settings()

    # Yonlendirme adresi girilmediyse alan adindan uretilir: kullanicinin
    # elle yazmasina gerek yok ve yazim hatasi riski ortadan kalkar.
    varsayilan_donus = (
        f"https://{ayarlar.public_domain}/api/v1/oauth/meta/callback"
        if ayarlar.public_domain and ayarlar.public_domain != "localhost"
        else ayarlar.meta_redirect_uri
    )

    kapsam = _oku("META_SCOPES", ayarlar.meta_scopes)
    return MetaAyarlari(
        app_id=_oku("META_APP_ID", ayarlar.meta_app_id),
        app_secret=_oku("META_APP_SECRET", ayarlar.meta_app_secret),
        redirect_uri=_oku("META_REDIRECT_URI", ayarlar.meta_redirect_uri or varsayilan_donus),
        api_version=_oku("META_API_VERSION", ayarlar.meta_api_version),
        authorize_url=_oku("META_AUTHORIZE_URL", ayarlar.meta_authorize_url),
        token_url=_oku("META_TOKEN_URL", ayarlar.meta_token_url),
        graph_base_url=_oku("META_GRAPH_BASE_URL", ayarlar.meta_graph_base_url),
        scopes=[s.strip() for s in kapsam.split(",") if s.strip()],
    )


def meta_hazir_mi() -> bool:
    """Gercek Meta baglantisi yapilabilir mi?

    Panelde anahtarlar girilmisse sahte adaptore dusulmez: kullanicinin
    girdigi degerleri gormezden gelmek, ornek veriyi gercek sanmasina yol
    acardi.
    """
    return meta_ayarlarini_oku().hazir
