"""Giris, oturum yenileme ve 'ben kimim' uclari."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.logging_config import get_logger
from app.core.security import (
    TokenError,
    create_token,
    decode_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.models.identity import User
from app.schemas import LoginRequest, RefreshRequest, TokenResponse, UserOut

router = APIRouter(prefix="/api/v1/auth", tags=["kimlik"])
log = get_logger("auth")

# E-posta yanlis da olsa sifre yanlis da olsa AYNI mesaj doner.
# Aksi halde saldirgan, hangi e-postalarin kayitli oldugunu ogrenebilir.
_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="E-posta veya sifre hatali.",
)


@router.post("/login", response_model=TokenResponse, summary="Giris yap")
def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    user = db.execute(
        select(User).where(User.email == payload.email.lower())
    ).scalar_one_or_none()

    if user is None:
        # Kullanici yoksa bile sifre dogrulamasi calistirilir; boylece yanit
        # suresi kullanicinin var olup olmadigini ele vermez.
        verify_password(payload.password, _DUMMY_HASH)
        log.info("giris_basarisiz", reason="kullanici_yok")
        raise _INVALID_CREDENTIALS

    if not verify_password(payload.password, user.password_hash):
        log.info("giris_basarisiz", reason="sifre_hatali", user_id=str(user.id))
        raise _INVALID_CREDENTIALS

    if not user.is_active:
        log.info("giris_basarisiz", reason="hesap_pasif", user_id=str(user.id))
        raise _INVALID_CREDENTIALS

    # Guvenlik parametreleri guncellendiyse sifre ozeti sessizce yenilenir.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)

    user.last_login_at = datetime.now(UTC)
    db.commit()

    log.info("giris_basarili", user_id=str(user.id))
    return TokenResponse(
        access_token=create_token(user.id, "access"),
        refresh_token=create_token(user.id, "refresh"),
    )


@router.post("/refresh", response_model=TokenResponse, summary="Oturumu yenile")
def refresh(payload: RefreshRequest, db: DbSession) -> TokenResponse:
    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    try:
        user_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Oturum anahtari gecersiz."
        ) from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Kullanici bulunamadi veya pasif."
        )

    return TokenResponse(
        access_token=create_token(user.id, "access"),
        refresh_token=create_token(user.id, "refresh"),
    )


@router.get("/me", response_model=UserOut, summary="Oturumdaki kullanici")
def me(user: CurrentUser) -> User:
    return user


# Zamanlama saldirisina karsi sabit maliyetli sahte ozet.
_DUMMY_HASH = hash_password("bu-sifre-hicbir-hesaba-ait-degil")
