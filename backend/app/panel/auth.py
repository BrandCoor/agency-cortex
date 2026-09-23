"""Panel oturum yonetimi.

Panel tarayicidan kullanildigi icin API'den farkli bir oturum yontemi
gerekir. Oturum anahtari, JavaScript'in okuyamayacagi bir cerezde tutulur
(`httponly`); boylece sayfaya sizan bir betik anahtari calamaz.
"""

from __future__ import annotations

import uuid

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import TokenError, decode_token
from app.models.identity import User

COOKIE_NAME = "ac_session"


def set_session_cookie(response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        # JavaScript okuyamaz - calinma riski azalir.
        httponly=True,
        # Uretimde yalnizca HTTPS uzerinden gonderilir.
        secure=settings.is_production,
        # Baska sitelerden gelen isteklerde gonderilmez (CSRF korumasi).
        samesite="lax",
        max_age=settings.access_token_ttl_minutes * 60,
        path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def current_user_from_cookie(request: Request, db: Session) -> User | None:
    """Cerezden kullaniciyi cozer. Gecersizse None doner."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        payload = decode_token(token, expected_type="access")
        user_id = uuid.UUID(payload["sub"])
    except (TokenError, KeyError, ValueError):
        return None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None

    # GORUNUM TERCIHI TEK NOKTADAN.
    #
    # Her panel sayfasi bu fonksiyondan geciyor; tercihi burada
    # saklamak, yirmi ayri render cagrisina ayri ayri parametre
    # gecirmekten hem kisa hem de unutulmaya kapali.
    from app.services.gorunum import tema_gecerli, vurgu_gecerli

    request.state.tema = tema_gecerli(user.tema)
    request.state.vurgu = vurgu_gecerli(user.vurgu)
    return user
