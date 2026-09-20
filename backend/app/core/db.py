"""Veritabani baglantisi ve oturum yonetimi."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Tum tablolarin ortak atasi."""


_settings = get_settings()

engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,   # Kopmus baglantiyi kullanmadan once dogrular
    pool_size=5,
    max_overflow=10,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI bagimliligi: istek basina bir veritabani oturumu."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database() -> tuple[bool, str | None]:
    """Veritabani erisilebilir mi? (saglikli_mi, hata_mesaji)"""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:  # noqa: BLE001 - saglik kontrolu her hatayi yakalamali
        return False, f"{type(exc).__name__}: {exc}"
