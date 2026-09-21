"""Sifre ozeti, oturum anahtarlari ve token sifreleme.

Uc ayri isi kapsar:
1. Kullanici sifrelerini geri cevrilemez sekilde ozetlemek (Argon2).
2. Oturum anahtari (JWT) uretip dogrulamak.
3. Sosyal medya token'larini veritabaninda sifreli saklamak (Fernet).
"""

from __future__ import annotations

import base64
import hashlib
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

_settings = get_settings()

# Argon2id: sifre ozetleme icin guncel onerilen yontem.
_hasher = PasswordHasher()

JWT_ALGORITHM = "HS256"
TokenType = Literal["access", "refresh"]


# --------------------------------------------------------------------------
# Sifreler
# --------------------------------------------------------------------------

def _normalize_password(plain: str) -> str:
    """Sifreyi tek bir Unicode gosterimine cevirir.

    NEDEN GEREKLI?
    Turkce harfler (g, u, s, i, o, c) iki farkli sekilde kodlanabilir:
    tek bir karakter olarak (U+011F) veya taban harf + birlesik isaret
    olarak (g + U+0306). Ekranda ikisi de AYNI gorunur, fakat bayt
    duzeyinde farklidir; ozetleri de farkli cikar.

    Kullanici sifresini bir cihazda olusturup baska bir cihazda yazdiginda
    (ornegin masaustunde olusturup telefondan girdiginde) bu iki gosterim
    karisabilir ve "sifre hatali" hatasi alinir - sifre aslinda dogru
    oldugu halde.

    Cozum, RFC 8265'in (PRECIS OpaqueString) onerdigi yaklasimdir: sifre
    hem ozetlenirken hem dogrulanirken ayni bicime (NFKC) cevrilir.
    Sifrenin gucu degismez; yalnizca gosterim birlestirilir.
    """
    return unicodedata.normalize("NFKC", plain)


def hash_password(plain: str) -> str:
    """Sifreyi geri cevrilemez sekilde ozetler."""
    if not plain:
        raise ValueError("Sifre bos olamaz.")
    return _hasher.hash(_normalize_password(plain))


def verify_password(plain: str, hashed: str) -> bool:
    """Girilen sifre, saklanan ozete uyuyor mu?

    Hatali ozet veya uyusmazlik durumunda istisna firlatmaz; False doner.
    Boylece giris ucu, hatanin turunu disariya sizdirmaz.
    """
    try:
        return _hasher.verify(hashed, _normalize_password(plain))
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def needs_rehash(hashed: str) -> bool:
    """Guvenlik parametreleri guncellendiyse sifre yeniden ozetlenmeli."""
    try:
        return _hasher.check_needs_rehash(hashed)
    except (InvalidHashError, ValueError):
        return True


# --------------------------------------------------------------------------
# Oturum anahtarlari (JWT)
# --------------------------------------------------------------------------

def create_token(
    subject: str | uuid.UUID,
    token_type: TokenType = "access",
    expires_delta: timedelta | None = None,
) -> str:
    """Kullanici icin imzali oturum anahtari uretir."""
    now = datetime.now(UTC)
    if expires_delta is None:
        expires_delta = (
            timedelta(minutes=_settings.access_token_ttl_minutes)
            if token_type == "access"
            else timedelta(days=_settings.refresh_token_ttl_days)
        )

    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _settings.secret_key, algorithm=JWT_ALGORITHM)


class TokenError(Exception):
    """Anahtar gecersiz, suresi dolmus veya beklenen turde degil."""


def decode_token(token: str, expected_type: TokenType = "access") -> dict[str, Any]:
    """Anahtari dogrular ve icerigini doner.

    Suresi dolmus, imzasi bozuk veya turu yanlis anahtarlar reddedilir.
    Yanlis turun reddedilmesi onemlidir: yenileme anahtari erisim anahtari
    yerine kullanilamaz.
    """
    try:
        payload = jwt.decode(token, _settings.secret_key, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Oturum anahtarinin suresi dolmus.") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Oturum anahtari gecersiz.") from exc

    if payload.get("type") != expected_type:
        raise TokenError("Oturum anahtari beklenen turde degil.")
    return payload


# --------------------------------------------------------------------------
# Token sifreleme (sosyal medya erisim anahtarlari icin)
# --------------------------------------------------------------------------

def _fernet() -> Fernet:
    """Ayarlardaki anahtardan Fernet anahtari turetir.

    ENCRYPTION_KEY herhangi bir metin olabilir; SHA-256 ile 32 bayta
    indirgenip base64'e cevrilir.
    """
    digest = hashlib.sha256(_settings.encryption_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plain: str) -> str:
    """Bir sirri veritabaninda saklanmak uzere sifreler."""
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_secret(encrypted: str) -> str:
    """Sifreli sirri cozer. Bozuk veriyse acik hata verir."""
    try:
        return _fernet().decrypt(encrypted.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise ValueError("Sifreli deger cozulemedi. Anahtar degismis olabilir.") from exc
