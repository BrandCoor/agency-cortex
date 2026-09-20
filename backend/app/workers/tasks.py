"""Zamanlanmis ve kuyruga alinan isler."""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.db import check_database
from app.core.logging_config import get_logger
from app.core.redis_client import check_redis
from app.workers.celery_app import celery_app

log = get_logger("worker")


@celery_app.task(name="app.workers.tasks.heartbeat")
def heartbeat() -> dict:
    """Worker'in ayakta ve bagimliliklarina erisebildigini kanitlar.

    Bu is bilerek yan etkisizdir; istedigi kadar tekrar calistirilabilir.
    """
    db_ok, db_error = check_database()
    redis_ok, redis_error = check_redis()

    result = {
        "checked_at": datetime.now(UTC).isoformat(),
        "database_ok": db_ok,
        "redis_ok": redis_ok,
    }

    if db_ok and redis_ok:
        log.info("heartbeat_ok", **result)
    else:
        log.error("heartbeat_basarisiz", db_error=db_error, redis_error=redis_error, **result)

    return result
