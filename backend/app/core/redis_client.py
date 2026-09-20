"""Redis baglantisi (kuyruk ve onbellek)."""

from __future__ import annotations

import redis

from app.core.config import get_settings

_settings = get_settings()

client = redis.Redis.from_url(
    _settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5,
)


def check_redis() -> tuple[bool, str | None]:
    """Redis erisilebilir mi? (saglikli_mi, hata_mesaji)"""
    try:
        client.ping()
        return True, None
    except Exception as exc:  # noqa: BLE001 - saglik kontrolu her hatayi yakalamali
        return False, f"{type(exc).__name__}: {exc}"
