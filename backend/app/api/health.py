"""Saglik kontrolu uclari.

- /healthz  : Uygulama ayakta mi? (Docker/Caddy icin hizli kontrol)
- /readyz   : Uygulama is gormeye hazir mi? (veritabani + Redis kontrollu)
- /version  : Hangi surum calisiyor?
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app import __version__
from app.core.config import get_settings
from app.core.db import check_database
from app.core.redis_client import check_redis

router = APIRouter(tags=["saglik"])


@router.get("/healthz", summary="Uygulama ayakta mi")
def healthz() -> dict:
    """Bagimliliklara bakmaz; yalnizca surecin yanit verdigini gosterir."""
    return {"status": "ok"}


@router.get("/readyz", summary="Uygulama hazir mi")
def readyz(response: Response) -> dict:
    """Veritabani ve Redis kontrol edilir.

    Biri bile calismiyorsa HTTP 503 doner. Boylece yari calisan bir sistem
    saglikli gorunmez.
    """
    db_ok, db_error = check_database()
    redis_ok, redis_error = check_redis()

    checks = {
        "database": {"ok": db_ok, "error": db_error},
        "redis": {"ok": redis_ok, "error": redis_error},
    }
    all_ok = db_ok and redis_ok

    if not all_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {"status": "ready" if all_ok else "not_ready", "checks": checks}


@router.get("/version", summary="Surum bilgisi")
def version() -> dict:
    settings = get_settings()
    return {
        "name": settings.app_name,
        "version": __version__,
        "environment": settings.app_env,
        # Ilk surumde yayin kilitlerinin durumu disaridan gorulebilmeli.
        "publishing_enabled": settings.feature_publishing_enabled,
    }
