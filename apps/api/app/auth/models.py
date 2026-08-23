from __future__ import annotations

from pydantic import BaseModel, Field

from app.auth.personas import Role


class AuthUser(BaseModel):
    """Identity carried in JWT and request context."""

    user_id: str
    name: str
    role: Role
    account_id: str | None = None
    persona_id: str


class LoginRequest(BaseModel):
    persona_id: str = Field(..., min_length=1, description="e.g. northstar, maya, ops")


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: AuthUser


class PersonaOut(BaseModel):
    persona_id: str
    name: str
    role: Role
    account_id: str | None
    description: str
