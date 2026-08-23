from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.auth.models import AuthUser
from app.auth.personas import Persona
from app.config import get_settings


def create_access_token(persona: Persona) -> tuple[str, int]:
    """Return (jwt, expires_in_minutes) for a demo persona."""
    settings = get_settings()
    expires_minutes = settings.jwt_expire_minutes
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=expires_minutes)

    payload = {
        "sub": persona.persona_id,
        "user_id": persona.persona_id,
        "name": persona.name,
        "role": persona.role,
        "account_id": persona.account_id,
        "persona_id": persona.persona_id,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return token, expires_minutes


def decode_access_token(token: str) -> AuthUser:
    """Validate JWT and return AuthUser. Raises ValueError on failure."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc

    role = payload.get("role")
    if role not in ("customer", "support_agent", "ops_admin"):
        raise ValueError("Token missing valid role")

    persona_id = payload.get("persona_id") or payload.get("sub")
    if not persona_id:
        raise ValueError("Token missing persona identity")

    return AuthUser(
        user_id=str(payload.get("user_id") or persona_id),
        name=str(payload.get("name") or persona_id),
        role=role,
        account_id=payload.get("account_id"),
        persona_id=str(persona_id),
    )
