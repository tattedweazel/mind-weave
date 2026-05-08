"""Server-side refresh token revocation (SE-010)."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, col, delete

from app.persistence.tables import RevokedRefreshToken, utc_now


def purge_expired_revocations(session: Session) -> None:
    session.exec(delete(RevokedRefreshToken).where(col(RevokedRefreshToken.expires_at) < utc_now()))
    session.commit()


def refresh_jti_is_revoked(session: Session, jti: str) -> bool:
    return session.get(RevokedRefreshToken, jti) is not None


def revoke_refresh_jti(session: Session, jti: str, expires_at: datetime) -> None:
    if session.get(RevokedRefreshToken, jti) is not None:
        return
    session.add(RevokedRefreshToken(jti=jti, expires_at=expires_at))
    session.commit()
