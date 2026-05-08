"""HttpOnly auth cookies (SE-004)."""

from fastapi import Response

from app.core.config import settings

COOKIE_ACCESS = "mw_access_token"
COOKIE_REFRESH = "mw_refresh_token"


def _cookie_common() -> dict:
    secure = settings.APP_ENV != "local"
    return {
        "httponly": True,
        "secure": secure,
        "samesite": "lax",
        "path": "/",
    }


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    common = _cookie_common()
    response.set_cookie(
        COOKIE_ACCESS,
        access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        **common,
    )
    response.set_cookie(
        COOKIE_REFRESH,
        refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        **common,
    )


def clear_auth_cookies(response: Response) -> None:
    common = _cookie_common()
    response.delete_cookie(
        COOKIE_ACCESS,
        path="/",
        secure=common["secure"],
        httponly=common["httponly"],
        samesite=common["samesite"],
    )
    response.delete_cookie(
        COOKIE_REFRESH,
        path="/",
        secure=common["secure"],
        httponly=common["httponly"],
        samesite=common["samesite"],
    )
