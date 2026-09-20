"""Yapilandirilmis (JSON) loglama ve hassas veri maskeleme.

Loglara token, sifre, kisisel mesaj veya API anahtari yazilmasi guvenlik
ihlalidir. Bu modul, log kaydina giren sozlukleri tarayip riskli alanlari
otomatik olarak maskeler.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

# Degeri loga hic yazilmamasi gereken alan adlari (kucuk harfe cevrilip aranir).
SENSITIVE_KEYS = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "secret_key",
        "encryption_key",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "api_key",
        "apikey",
        "authorization",
        "client_secret",
        "app_secret",
        "webhook_secret",
        "verify_token",
        "private_key",
        "session",
        "cookie",
        "set-cookie",
        "message_text",
        "dm_body",
        "email",
        "phone",
    }
)

MASK = "***MASKELENDI***"
_MAX_DEPTH = 6


def _mask(value: Any, depth: int = 0) -> Any:
    """Sozluk/liste icinde gezerek hassas alanlari maskeler."""
    if depth > _MAX_DEPTH:
        return value
    if isinstance(value, dict):
        masked: dict[Any, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and k.lower() in SENSITIVE_KEYS:
                masked[k] = MASK
            else:
                masked[k] = _mask(v, depth + 1)
        return masked
    if isinstance(value, (list, tuple)):
        items = [_mask(v, depth + 1) for v in value]
        return type(value)(items) if isinstance(value, tuple) else items
    return value


def mask_sensitive(_logger: Any, _name: str, event_dict: dict) -> dict:
    """structlog islemcisi: her log kaydini maskeden gecirir."""
    return _mask(event_dict)


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    """Loglamayi kurar. Uretimde JSON, gelistirmede okunabilir renkli cikti."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )

    renderer = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            mask_sensitive,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> Any:
    return structlog.get_logger(name)
