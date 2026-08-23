from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.acl import ACLError
from app.auth.deps import get_current_user
from app.auth.models import AuthUser
from app.db.session import get_db
from app.tools.actions import (
    ACTION_CREATE_ESCALATION,
    cancel_action,
    confirm_action,
    get_pending_action,
    propose_action,
)

router = APIRouter(prefix="/actions", tags=["actions"])


class ProposeActionRequest(BaseModel):
    action_type: Literal[
        "create_escalation",
        "update_ticket",
        "create_follow_up_task",
    ]
    ticket_id: str | None = None
    severity: str | None = None
    reason: str | None = None
    recommended_next_step: str | None = None
    status: str | None = None
    assigned_to: str | None = None
    notes: str | None = None
    title: str | None = None
    details: str | None = None


class EscalateRequest(BaseModel):
    ticket_id: str
    severity: str = "P1"
    reason: str = Field(..., min_length=1)
    recommended_next_step: str = Field(..., min_length=1)


def _handle_tool_errors(exc: Exception) -> HTTPException:
    if isinstance(exc, ACLError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, LookupError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, SQLAlchemyError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unavailable: {exc}",
        )
    return HTTPException(status_code=500, detail=str(exc))


@router.post("/propose")
def propose(body: ProposeActionRequest, user: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Propose a state-changing action (creates pending_action only)."""
    try:
        return propose_action(
            db,
            user,
            action_type=body.action_type,
            ticket_id=body.ticket_id,
            severity=body.severity,
            reason=body.reason,
            recommended_next_step=body.recommended_next_step,
            status=body.status,
            assigned_to=body.assigned_to,
            notes=body.notes,
            title=body.title,
            details=body.details,
        )
    except (ACLError, LookupError, ValueError, SQLAlchemyError) as exc:
        raise _handle_tool_errors(exc) from exc


@router.post("/escalate")
def escalate(
    body: EscalateRequest,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Shortcut for create_escalation — still requires confirm."""
    try:
        return propose_action(
            db,
            user,
            action_type=ACTION_CREATE_ESCALATION,
            ticket_id=body.ticket_id,
            severity=body.severity,
            reason=body.reason,
            recommended_next_step=body.recommended_next_step,
        )
    except (ACLError, LookupError, ValueError, SQLAlchemyError) as exc:
        raise _handle_tool_errors(exc) from exc


@router.get("/{pending_id}")
def get_action(
    pending_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return get_pending_action(db, user, pending_id)
    except (ACLError, LookupError, ValueError, SQLAlchemyError) as exc:
        raise _handle_tool_errors(exc) from exc


@router.post("/{pending_id}/confirm")
def confirm(
    pending_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Execute the pending mutation and write audit log."""
    try:
        return confirm_action(db, user, pending_id)
    except (ACLError, LookupError, ValueError, SQLAlchemyError) as exc:
        raise _handle_tool_errors(exc) from exc


@router.post("/{pending_id}/cancel")
def cancel(
    pending_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Discard pending action — no mutation."""
    try:
        return cancel_action(db, user, pending_id)
    except (ACLError, LookupError, ValueError, SQLAlchemyError) as exc:
        raise _handle_tool_errors(exc) from exc
