"""Sosyal medya anahtarlarinin sifreli saklanmasi.

Anahtarlar veritabanina DUZ METIN olarak asla yazilmaz. Bu modul disinda
hicbir yer sifreleme ile ugrasmaz; tek giris-cikis noktasi burasidir.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.core.security import decrypt_secret, encrypt_secret
from app.models.social import OAuthCredential
from app.platforms.base import TokenBundle

log = get_logger("token_store")


def save_tokens(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    social_account_id: uuid.UUID,
    tokens: TokenBundle,
) -> OAuthCredential:
    """Anahtarlari sifreleyip kaydeder. Varsa uzerine yazar."""
    credential = db.execute(
        select(OAuthCredential).where(
            OAuthCredential.social_account_id == social_account_id,
            # Calisma alani kontrolu: baska musterinin kaydi guncellenemez.
            OAuthCredential.workspace_id == workspace_id,
        )
    ).scalar_one_or_none()

    if credential is None:
        credential = OAuthCredential(
            workspace_id=workspace_id, social_account_id=social_account_id,
            access_token_encrypted="",
        )
        db.add(credential)

    credential.access_token_encrypted = encrypt_secret(tokens.access_token)
    credential.refresh_token_encrypted = (
        encrypt_secret(tokens.refresh_token) if tokens.refresh_token else None
    )
    credential.token_type = tokens.token_type
    credential.scopes = list(tokens.scopes)
    credential.expires_at = tokens.expires_at
    credential.last_refreshed_at = datetime.now(UTC)

    db.flush()
    # Loga anahtarin kendisi DEGIL, yalnizca kaydin kimligi yazilir.
    log.info(
        "anahtar_kaydedildi",
        workspace_id=str(workspace_id),
        social_account_id=str(social_account_id),
        expires_at=tokens.expires_at.isoformat() if tokens.expires_at else None,
    )
    return credential


def load_tokens(
    db: Session, *, workspace_id: uuid.UUID, social_account_id: uuid.UUID
) -> TokenBundle | None:
    """Sifreli anahtarlari cozup doner. Kayit yoksa None."""
    credential = db.execute(
        select(OAuthCredential).where(
            OAuthCredential.social_account_id == social_account_id,
            OAuthCredential.workspace_id == workspace_id,
        )
    ).scalar_one_or_none()

    if credential is None:
        return None

    return TokenBundle(
        access_token=decrypt_secret(credential.access_token_encrypted),
        refresh_token=(
            decrypt_secret(credential.refresh_token_encrypted)
            if credential.refresh_token_encrypted
            else None
        ),
        token_type=credential.token_type,
        expires_at=credential.expires_at,
        scopes=tuple(credential.scopes or ()),
    )


def is_expired(tokens: TokenBundle, *, skew_seconds: int = 300) -> bool:
    """Anahtarin suresi dolmus mu?

    `skew_seconds`: sure dolmadan bir sure once yenilemek icin pay.
    Tam sinirda yenilemek, uzun suren bir istegin ortasinda anahtarin
    gecersizlesmesine yol acabilir.
    """
    if tokens.expires_at is None:
        return False
    expires_at = tokens.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return (expires_at - datetime.now(UTC)).total_seconds() <= skew_seconds
