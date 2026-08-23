from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.deps import get_current_user
from app.auth.models import AuthUser, LoginRequest, LoginResponse, PersonaOut
from app.auth.personas import get_persona, list_personas
from app.auth.tokens import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/personas", response_model=list[PersonaOut])
def auth_personas() -> list[PersonaOut]:
    """List demo personas for the UI picker (no password)."""
    return [
        PersonaOut(
            persona_id=p.persona_id,
            name=p.name,
            role=p.role,
            account_id=p.account_id,
            description=p.description,
        )
        for p in list_personas()
    ]


@router.post("/login", response_model=LoginResponse)
def auth_login(body: LoginRequest) -> LoginResponse:
    """
    Mock login: pick a persona_id, get a JWT.
    No password — assessment mock auth only.
    """
    persona = get_persona(body.persona_id)
    if persona is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown persona_id: {body.persona_id}. "
            "Use GET /auth/personas for valid ids.",
        )

    token, expires_minutes = create_access_token(persona)
    user = AuthUser(
        user_id=persona.persona_id,
        name=persona.name,
        role=persona.role,
        account_id=persona.account_id,
        persona_id=persona.persona_id,
    )
    return LoginResponse(
        access_token=token,
        expires_in_minutes=expires_minutes,
        user=user,
    )


@router.get("/me", response_model=AuthUser)
def auth_me(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    """Return the identity encoded in the Bearer token."""
    return user
