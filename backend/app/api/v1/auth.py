import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from jose import jwt as jose_jwt
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.core.auth_cookies import COOKIE_REFRESH, clear_auth_cookies, set_auth_cookies
from app.core.config import settings
from app.core.google_oauth import build_authorization_url, exchange_code_for_user_info
from app.core.logging import logger
from app.core.oauth_state import (
    consume_google_session_code,
    consume_state,
    create_google_session_code,
    create_login_state,
    create_state,
)
from app.core.password_policy import validate_password_strength
from app.core.refresh_revocation import (
    purge_expired_revocations,
    refresh_jti_is_revoked,
    revoke_refresh_jti,
)
from app.core.security import (
    ALGORITHM,
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
)
from app.core.user_api_keys_crypto import decrypt_api_keys_store, encrypt_api_keys_store
from app.domain.user_settings import (
    MAX_CONCURRENT_LM_STUDIO_CALLS_MAX,
    MAX_CONCURRENT_LM_STUDIO_CALLS_MIN,
)
from app.integrations.gmail_query import GMAIL_EXCLUDABLE_CATEGORY_SLUGS, GMAIL_INBOX_FOCUS_MODES
from app.persistence.db import get_session
from app.persistence.tables import User
from app.providers.lmstudio_http import normalize_bearer_secret_value

router = APIRouter()


class Token(BaseModel):
    access_token: str | None = None
    token_type: str = "bearer"


class GoogleSessionComplete(BaseModel):
    code: str


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        return validate_password_strength(v)


class AdminUserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str
    is_admin: bool = False

    @field_validator("password")
    @classmethod
    def _password_strength_admin_create(cls, v: str) -> str:
        return validate_password_strength(v)


class AdminUserUpdate(BaseModel):
    username: str | None = None
    password: str | None = None
    is_admin: bool | None = None

    @field_validator("username")
    @classmethod
    def _admin_update_username_len(cls, v: str | None) -> str | None:
        if v is not None and not (1 <= len(v) <= 64):
            raise ValueError("username must be 1–64 characters")
        return v

    @field_validator("password")
    @classmethod
    def _password_strength_admin_update(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return validate_password_strength(v)


_MAX_SETTINGS_BYTES = 64_000
_MAX_API_KEYS = 32
_MAX_SETTINGS_KEYS = 200
_ALLOWED_SETTINGS_KEYS = frozenset(
    {
        "avatar_url",
        "system_colors",
        "system_palette_id",
        "theme_mode",
        "preferred_editor_palette_id",
        "workflow_editor_remember_panel_widths",
        "gmail_workflow_exclude_categories",
        "gmail_workflow_inbox_focus",
        "workflow_time_zone",
        "max_concurrent_lm_studio_calls",
        "auto_play_tts_on_node_end",
        "tts_playback_when",
    }
)
_ALLOWED_THEME_MODES = frozenset({"light", "dark", "system"})
_ALLOWED_TTS_PLAYBACK_WHEN = frozenset({"inline", "manual", "after_workflow"})
_ALLOWED_API_KEY_NAMES = frozenset({"lmstudio_api_key", "openai", "anthropic", "google", "assemblyai"})


class UserUpdate(BaseModel):
    settings: dict[str, Any] | None = None
    api_keys: dict[str, Any] | None = None

    @field_validator("settings")
    @classmethod
    def _bound_settings(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is None:
            return v
        if len(v) > _MAX_SETTINGS_KEYS:
            raise ValueError("settings has too many keys")
        extra = set(v.keys()) - _ALLOWED_SETTINGS_KEYS
        if extra:
            raise ValueError(f"settings keys not allowed: {sorted(extra)}")
        if v.get("avatar_url") is not None:
            av = v["avatar_url"]
            if not isinstance(av, str):
                raise ValueError("settings.avatar_url must be a string")
            if len(av) > 500_000:
                raise ValueError("settings.avatar_url too large")
        if v.get("system_colors") is not None and not isinstance(v["system_colors"], dict):
            raise ValueError("settings.system_colors must be an object")
        if "system_palette_id" in v:
            sid = v["system_palette_id"]
            if sid is None or sid == "":
                v["system_palette_id"] = None
            elif not isinstance(sid, str):
                raise ValueError("settings.system_palette_id must be a string or null")
            else:
                try:
                    uuid.UUID(sid)
                except ValueError as exc:
                    raise ValueError("settings.system_palette_id must be a valid UUID") from exc
        if "preferred_editor_palette_id" in v:
            pid = v["preferred_editor_palette_id"]
            if pid is None or pid == "":
                v["preferred_editor_palette_id"] = None
            elif not isinstance(pid, str):
                raise ValueError("settings.preferred_editor_palette_id must be a string or null")
            else:
                try:
                    uuid.UUID(pid)
                except ValueError as exc:
                    raise ValueError("settings.preferred_editor_palette_id must be a valid UUID") from exc
        if "theme_mode" in v and v["theme_mode"] is not None:
            tm = v["theme_mode"]
            if not isinstance(tm, str):
                raise ValueError("settings.theme_mode must be a string")
            if tm not in _ALLOWED_THEME_MODES:
                raise ValueError("settings.theme_mode must be one of: light, dark, system")
        if "workflow_editor_remember_panel_widths" in v and v["workflow_editor_remember_panel_widths"] is not None:
            rw = v["workflow_editor_remember_panel_widths"]
            if not isinstance(rw, bool):
                raise ValueError("settings.workflow_editor_remember_panel_widths must be a boolean")
        if "auto_play_tts_on_node_end" in v and v["auto_play_tts_on_node_end"] is not None:
            ap = v["auto_play_tts_on_node_end"]
            if not isinstance(ap, bool):
                raise ValueError("settings.auto_play_tts_on_node_end must be a boolean")
        if "tts_playback_when" in v and v["tts_playback_when"] is not None:
            tw = v["tts_playback_when"]
            if not isinstance(tw, str):
                raise ValueError("settings.tts_playback_when must be a string")
            if tw not in _ALLOWED_TTS_PLAYBACK_WHEN:
                raise ValueError(
                    "settings.tts_playback_when must be one of: inline, manual, after_workflow",
                )
        if "gmail_workflow_inbox_focus" in v and v["gmail_workflow_inbox_focus"] is not None:
            gf = v["gmail_workflow_inbox_focus"]
            if not isinstance(gf, str):
                raise ValueError("settings.gmail_workflow_inbox_focus must be a string")
            gfs = gf.strip().lower()
            if gfs not in GMAIL_INBOX_FOCUS_MODES:
                raise ValueError(
                    "settings.gmail_workflow_inbox_focus must be one of: off, primary",
                )
            v["gmail_workflow_inbox_focus"] = gfs
        if "gmail_workflow_exclude_categories" in v and v["gmail_workflow_exclude_categories"] is not None:
            exc = v["gmail_workflow_exclude_categories"]
            if not isinstance(exc, list):
                raise ValueError("settings.gmail_workflow_exclude_categories must be a list")
            norm: list[str] = []
            for item in exc:
                if not isinstance(item, str):
                    raise ValueError(
                        "settings.gmail_workflow_exclude_categories must be a list of strings",
                    )
                slug = item.strip().lower()
                if slug not in GMAIL_EXCLUDABLE_CATEGORY_SLUGS:
                    raise ValueError(
                        f"settings.gmail_workflow_exclude_categories unknown category: {item!r}",
                    )
                if slug not in norm:
                    norm.append(slug)
            v["gmail_workflow_exclude_categories"] = norm
        if "workflow_time_zone" in v and v["workflow_time_zone"] is not None:
            wz = v["workflow_time_zone"]
            if not isinstance(wz, str):
                raise ValueError("settings.workflow_time_zone must be a string")
            ws = wz.strip()
            if ws == "":
                v["workflow_time_zone"] = "system"
            elif len(ws) > 120:
                raise ValueError("settings.workflow_time_zone too long")
            elif ws.casefold() == "system":
                v["workflow_time_zone"] = "system"
            else:
                try:
                    ZoneInfo(ws)
                except Exception as exc:
                    raise ValueError(
                        "settings.workflow_time_zone must be 'system' or a valid IANA time zone name",
                    ) from exc
                v["workflow_time_zone"] = ws
        if "max_concurrent_lm_studio_calls" in v and v["max_concurrent_lm_studio_calls"] is not None:
            mc = v["max_concurrent_lm_studio_calls"]
            if isinstance(mc, bool) or not isinstance(mc, int):
                raise ValueError("settings.max_concurrent_lm_studio_calls must be an integer")
            if mc < MAX_CONCURRENT_LM_STUDIO_CALLS_MIN or mc > MAX_CONCURRENT_LM_STUDIO_CALLS_MAX:
                raise ValueError(
                    f"settings.max_concurrent_lm_studio_calls must be between "
                    f"{MAX_CONCURRENT_LM_STUDIO_CALLS_MIN} and {MAX_CONCURRENT_LM_STUDIO_CALLS_MAX}",
                )
        raw = json.dumps(v)
        if len(raw.encode("utf-8")) > _MAX_SETTINGS_BYTES:
            raise ValueError("settings payload too large")
        return v

    @field_validator("api_keys")
    @classmethod
    def _bound_api_keys(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is None:
            return v
        if len(v) > _MAX_API_KEYS:
            raise ValueError("api_keys has too many entries")
        extra = set(v.keys()) - _ALLOWED_API_KEY_NAMES
        if extra:
            raise ValueError(f"api_keys keys not allowed: {sorted(extra)}")
        for key, val in v.items():
            if len(key) > 128:
                raise ValueError("api_keys key too long")
            if val is not None and val != "" and not isinstance(val, str):
                raise ValueError(f"api_keys.{key} must be a string")
        return v


class GoogleAuthorizeResponse(BaseModel):
    redirect_url: str


def _mask_api_keys_for_api(keys: dict[str, Any]) -> dict[str, Any]:
    """Never echo raw secret values to clients (SE-011)."""
    masked: dict[str, Any] = {}
    for k, val in keys.items():
        if val is None or val == "":
            masked[k] = val
        else:
            masked[k] = "[stored]"
    return masked


_API_KEY_MASK_SENTINEL = "[stored]"


def _merge_api_keys_update(current_stored: dict[str, Any] | None, incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge PUT body onto existing api_keys. Never persist the literal ``[stored]`` placeholder from masked GET responses.
    Empty string is skipped (preserve existing) — clients should omit keys they are not updating; use ``null`` to remove a key.
    """
    current = decrypt_api_keys_store(current_stored)
    merged: dict[str, Any] = dict(current)
    for k, v in incoming.items():
        if k not in _ALLOWED_API_KEY_NAMES:
            continue
        if v is None:
            merged.pop(k, None)
            continue
        if not isinstance(v, str):
            continue
        v = v.strip()
        if v == "":
            continue
        if v == _API_KEY_MASK_SENTINEL:
            continue
        v = normalize_bearer_secret_value(v)
        if v == "":
            continue
        if v == _API_KEY_MASK_SENTINEL:
            continue
        merged[k] = v
    return encrypt_api_keys_store(merged)


def _user_me_response(user: User) -> dict:
    """Build the /me response dict including google_email."""
    return {
        "id": user.id,
        "username": user.username,
        "is_admin": user.is_admin,
        "settings": user.settings,
        "api_keys": _mask_api_keys_for_api(user.api_keys or {}),
        "google_email": user.google_email,
    }


@router.post("/login", response_model=Token)
async def login_for_access_token(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
) -> Token:
    user = session.exec(select(User).where(User.username == form_data.username)).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.google_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="use_google_login",
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.username}, expires_delta=access_token_expires)
    refresh_token = create_refresh_token(user.username)
    set_auth_cookies(response, access_token, refresh_token)
    return Token(access_token=None, token_type="bearer")


@router.post("/register", response_model=Token)
async def register(
    response: Response,
    user_in: UserCreate,
    session: Session = Depends(get_session),
):
    if not settings.OPEN_REGISTRATION:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is disabled",
        )
    existing_user = session.exec(select(User).where(User.username == user_in.username)).first()
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Unable to complete registration",
        )

    hashed_password = get_password_hash(user_in.password)
    user = User(
        username=user_in.username,
        password_hash=hashed_password,
        settings={},
        api_keys={},
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.username}, expires_delta=access_token_expires)
    refresh_token = create_refresh_token(user.username)
    set_auth_cookies(response, access_token, refresh_token)
    return Token(access_token=None, token_type="bearer")


@router.post("/refresh", response_model=Token)
async def refresh_session(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> Token:
    raw_refresh = request.cookies.get(COOKIE_REFRESH)
    if not raw_refresh:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token",
        )
    try:
        payload = jose_jwt.decode(raw_refresh, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("typ") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
        username: str | None = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
        jti_raw = payload.get("jti")
        if not jti_raw or not isinstance(jti_raw, str):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    purge_expired_revocations(session)
    jti = payload.get("jti")
    if jti and refresh_jti_is_revoked(session, jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    exp_ts = payload.get("exp")
    if jti and exp_ts:
        revoke_refresh_jti(
            session,
            jti,
            datetime.fromtimestamp(exp_ts, tz=timezone.utc),
        )

    user = session.exec(select(User).where(User.username == username)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.username}, expires_delta=access_token_expires)
    new_refresh = create_refresh_token(user.username)
    set_auth_cookies(response, access_token, new_refresh)
    return Token(access_token=None, token_type="bearer")


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_auth(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> None:
    raw = request.cookies.get(COOKIE_REFRESH)
    if raw:
        try:
            payload = jose_jwt.decode(
                raw,
                settings.SECRET_KEY,
                algorithms=[ALGORITHM],
                options={"verify_exp": False},
            )
            jti = payload.get("jti")
            exp_ts = payload.get("exp")
            if jti and exp_ts:
                revoke_refresh_jti(
                    session,
                    jti,
                    datetime.fromtimestamp(exp_ts, tz=timezone.utc),
                )
        except JWTError:
            pass
    clear_auth_cookies(response)


@router.post("/google/session", response_model=Token)
async def google_session_complete(
    response: Response,
    body: GoogleSessionComplete,
    session: Session = Depends(get_session),
) -> Token:
    username = consume_google_session_code(session, body.code)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session code",
        )
    user = session.exec(select(User).where(User.username == username)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.username}, expires_delta=access_token_expires)
    refresh_token = create_refresh_token(user.username)
    set_auth_cookies(response, access_token, refresh_token)
    return Token(access_token=None, token_type="bearer")


@router.get("/me", response_model=dict)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return _user_me_response(current_user)


@router.put("/me", response_model=dict)
async def update_user_me(
    user_update: UserUpdate, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)
):
    if user_update.settings is not None:
        current_user.settings = user_update.settings
    if user_update.api_keys is not None:
        current_user.api_keys = _merge_api_keys_update(current_user.api_keys, user_update.api_keys)

    session.add(current_user)
    session.commit()
    session.refresh(current_user)

    return _user_me_response(current_user)


@router.api_route("/google/login", methods=["GET", "HEAD"])
async def google_login(session: Session = Depends(get_session)) -> RedirectResponse:
    """Start Google OAuth login flow. Redirects to Google (no auth required). HEAD for `curl -I`."""
    base_url = f"{settings.FRONTEND_URL.rstrip('/')}"
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        return RedirectResponse(url=f"{base_url}/?google_error=not_configured")
    state = create_login_state(session)
    redirect_url = build_authorization_url(state)
    return RedirectResponse(url=redirect_url)


@router.post("/google/authorize", response_model=GoogleAuthorizeResponse)
async def google_authorize(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Start Google OAuth flow. Returns redirect_url for frontend to navigate to."""
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured",
        )
    state = create_state(session, current_user.id)
    redirect_url = build_authorization_url(state)
    return GoogleAuthorizeResponse(redirect_url=redirect_url)


@router.get("/google/callback")
async def google_callback(
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    """Handle Google OAuth callback. Supports login and association flows."""
    base_url = f"{settings.FRONTEND_URL.rstrip('/')}"
    if error:
        return RedirectResponse(url=f"{base_url}/?google_error=denied")
    if not code or not state:
        return RedirectResponse(url=f"{base_url}/?google_error=missing_params")

    state_value = consume_state(session, state)
    if state_value is None:
        return RedirectResponse(url=f"{base_url}/?google_error=expired")

    try:
        user_info = exchange_code_for_user_info(code)
    except Exception:
        return RedirectResponse(url=f"{base_url}/?google_error=exchange_failed")

    google_sub = user_info["sub"]
    google_email = user_info.get("email", "") or ""

    if state_value == "login":
        user = session.exec(select(User).where(User.google_user_id == google_sub)).first()
        if not user:
            return RedirectResponse(url=f"{base_url}/?google_error=no_account")
        session_code = create_google_session_code(session, user.username)
        return RedirectResponse(url=f"{base_url}/#google_session={session_code}")
    else:
        # Association flow: state_value is user_id
        user_id = state_value
        existing = session.exec(select(User).where(User.google_user_id == google_sub)).first()
        if existing and existing.id != user_id:
            return RedirectResponse(url=f"{base_url}/?google_error=already_linked")

        user = session.get(User, user_id)
        if not user:
            return RedirectResponse(url=f"{base_url}/?google_error=expired")

        user.google_user_id = google_sub
        user.google_email = google_email
        session.add(user)
        session.commit()

        return RedirectResponse(url=f"{base_url}/?google_associated=1")


@router.post("/google/disassociate", status_code=status.HTTP_204_NO_CONTENT)
async def google_disassociate(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Remove Google account association from current user."""
    current_user.google_user_id = None
    current_user.google_email = None
    session.add(current_user)
    session.commit()


@router.get("/users", response_model=list[dict])
async def list_users(session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    users = session.exec(select(User)).all()
    return [{"id": u.id, "username": u.username, "is_admin": u.is_admin, "google_email": u.google_email} for u in users]


@router.post("/users/{user_id}/google/disassociate", status_code=status.HTTP_204_NO_CONTENT)
async def admin_disassociate_google(
    user_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Remove Google account association for a user. Admin only."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    target_user = session.get(User, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    target_user.google_user_id = None
    target_user.google_email = None
    session.add(target_user)
    session.commit()


@router.put("/users/{user_id}", response_model=dict)
async def update_user_admin(
    user_id: uuid.UUID,
    user_update: AdminUserUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Update a user. Admin only."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    target_user = session.get(User, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    if user_update.username is not None:
        existing = session.exec(select(User).where(User.username == user_update.username, User.id != user_id)).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Unable to update user",
            )
        target_user.username = user_update.username

    if user_update.password is not None:
        target_user.password_hash = get_password_hash(user_update.password)

    if user_update.is_admin is not None:
        if user_update.is_admin is False and target_user.is_admin:
            other_admin = session.exec(select(User).where(User.is_admin, User.id != target_user.id)).first()
            if other_admin is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot remove the last admin",
                )
        if user_update.is_admin != target_user.is_admin:
            logger.info(
                "admin_privilege_change actor=%s target=%s new_is_admin=%s",
                current_user.username,
                target_user.username,
                user_update.is_admin,
            )
        target_user.is_admin = user_update.is_admin

    session.add(target_user)
    session.commit()
    session.refresh(target_user)

    return {
        "id": str(target_user.id),
        "username": target_user.username,
        "is_admin": target_user.is_admin,
        "google_email": target_user.google_email,
    }


@router.post("/users", response_model=dict)
async def create_user_admin(
    user_in: AdminUserCreate, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    existing_user = session.exec(select(User).where(User.username == user_in.username)).first()
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Unable to complete registration",
        )

    hashed_password = get_password_hash(user_in.password)
    user = User(
        username=user_in.username, password_hash=hashed_password, is_admin=user_in.is_admin, settings={}, api_keys={}
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return {"message": f"User {user.username} created successfully"}


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    user_to_delete = session.get(User, user_id)
    if not user_to_delete:
        raise HTTPException(status_code=404, detail="User not found")
    if user_to_delete.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    session.delete(user_to_delete)
    session.commit()
