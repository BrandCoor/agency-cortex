"""FastAPI uygulamasinin giris noktasi."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import ai, auth, health, oauth, platforms, reports, webhooks, workspaces
from app.core.config import get_settings
from app.core.logging_config import configure_logging, get_logger

settings = get_settings()
configure_logging(level=settings.log_level, json_output=settings.app_env != "development")
log = get_logger("app")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Uygulama acilirken ve kapanirken calisir."""
    # Uretimde sablon sifrelerle acilmasini engelle: sessiz guvenlik acigi olmasin.
    errors = settings.production_safety_errors()
    if errors:
        for err in errors:
            log.error("uretim_ayar_hatasi", detail=err)
        raise RuntimeError(
            "Uretim ayarlari guvenli degil. Ayrintilar icin yukaridaki loglara bakin."
        )

    log.info(
        "uygulama_basladi",
        environment=settings.app_env,
        ai_provider_mode=settings.ai_provider_mode,
        publishing_enabled=settings.feature_publishing_enabled,
    )
    yield
    log.info("uygulama_kapandi")


app = FastAPI(
    title=settings.app_name,
    description="Cok musterili sosyal medya asistani",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Her istege izlenebilir bir kimlik verir ve suresini loglar."""
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(request_id=request_id)
    started = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        # Hatanin tamami loga gider; istemciye ayrinti sizdirilmaz.
        log.exception(
            "istek_hatasi",
            method=request.method,
            path=request.url.path,
            duration_ms=duration_ms,
        )
        structlog.contextvars.clear_contextvars()
        return JSONResponse(
            status_code=500,
            content={"detail": "Beklenmeyen bir hata olustu.", "request_id": request_id},
            headers={"x-request-id": request_id},
        )

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    log.info(
        "istek",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    response.headers["x-request-id"] = request_id
    structlog.contextvars.clear_contextvars()
    return response


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(workspaces.router)
app.include_router(platforms.router)
app.include_router(oauth.router)
app.include_router(webhooks.router)
app.include_router(reports.router)
app.include_router(ai.router)
