"""Tek kullanimlik sifre belirleme bagi.

NEDEN GEREKLI:
Sifre, kullanicidan sisteme ulasirken birkac durakta bicim degistirebilir
(kopyala-yapistirda kacan bosluk, Turkce harflerin farkli Unicode
gosterimleri, farkli klavye duzenleri). Bu duraklarin her biri "sifre
dogru ama giris olmuyor" arizasina yol acar.

Bu akista sifre HIC AKTARILMAZ: kullanici sifresini dogrudan tarayicida,
sistemin kendi formunda belirler. Aradaki tum duraklar ortadan kalkar.

GUVENLIK:
- Jeton tahmin edilemez (32 bayt rastgele).
- Kisa omurludur (varsayilan 30 dakika).
- TEK KULLANIMLIKTIR: dogrulandigi anda silinir, ikinci kez calismaz.
- Jetonun kendisi degil, yalnizca SHA-256 ozeti saklanir; Redis'e erisen
  biri jetondan bag uretemez.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid

from app.core.logging_config import get_logger
from app.core.redis_client import client as redis_client

log = get_logger("sifre_sifirlama")

_PREFIX = "sifre:belirle:"
VARSAYILAN_OMUR_SANIYE = 30 * 60


class JetonHatasi(Exception):
    """Jeton gecersiz, suresi dolmus veya daha once kullanilmis."""


def _ozet(jeton: str) -> str:
    return hashlib.sha256(jeton.encode("utf-8")).hexdigest()


def jeton_uret(user_id: uuid.UUID, *, omur_saniye: int = VARSAYILAN_OMUR_SANIYE) -> str:
    """Bir kullanici icin tek kullanimlik jeton uretir ve ozetini saklar."""
    jeton = secrets.token_urlsafe(32)
    redis_client.setex(_PREFIX + _ozet(jeton), omur_saniye, str(user_id))
    # Jetonun kendisi loglanmaz.
    log.info("sifre_belirleme_jetonu_uretildi", user_id=str(user_id), omur_saniye=omur_saniye)
    return jeton


def jeton_gecerli_mi(jeton: str) -> bool:
    """Jetonu TUKETMEDEN gecerli olup olmadigina bakar.

    Formu gostermeden once kullanilir: gecersiz bir jetonda bos form
    gostermek yerine dogrudan aciklama verebilelim.
    """
    if not jeton:
        return False
    return redis_client.exists(_PREFIX + _ozet(jeton)) == 1


def jetonu_tuket(jeton: str) -> uuid.UUID:
    """Jetonu dogrular ve tek kullanimlik olarak tuketir."""
    if not jeton:
        raise JetonHatasi("Jeton bos.")

    # Once sil, sonra kullan: es zamanli iki istekten yalnizca biri gecer.
    ham = redis_client.getdel(_PREFIX + _ozet(jeton))
    if ham is None:
        raise JetonHatasi("Bag gecersiz, suresi dolmus veya daha once kullanilmis.")
    return uuid.UUID(ham)
