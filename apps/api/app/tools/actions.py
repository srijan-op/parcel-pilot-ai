from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.auth.acl import assert_account_access
from app.auth.models import AuthUser
from app.db.models import (
    AuditLog,
    Escalation,
    FollowUpTask,
    PendingAction,
    Ticket,
)
from app.timeutil import get_snapshot_at

ACTION_CREATE_ESCALATION = "create_escalation"
ACTION_UPDATE_TICKET = "update_ticket"
ACTION_CREATE_FOLLOW_UP = "create_follow_up_task"

ALLOWED_ACTIONS = frozenset(
    {ACTION_CREATE_ESCALATION, ACTION_UPDATE_TICKET, ACTION_CREATE_FOLLOW_UP}
)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _write_audit(
    db: Session,
    *,
    event: str,
    actor: str,
    pending_action_id: str | None,
    detail: dict[str, Any],
) -> None:
    db.add(
        AuditLog(
            event=event,
            pending_action_id=pending_action_id,
            actor=actor,
            detail=detail,
            created_at=get_snapshot_at(),
        )
    )


def serialize_pending(row: PendingAction) -> dict[str, Any]:
    return {
        "pending_id": row.pending_id,
        "action_type": row.action_type,
        "status": row.status,
        "account_id": row.account_id,
        "ticket_id": row.ticket_id,
        "payload": row.payload,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "resolved_by": row.resolved_by,
        "result_ref": row.result_ref,
        "needs_confirmation": row.status == "pending",
    }


def propose_action(
    db: Session,
    user: AuthUser,
    *,
    action_type: str,
    ticket_id: str | None = None,
    severity: str | None = None,
    reason: str | None = None,
    recommended_next_step: str | None = None,
    status: str | None = None,
    assigned_to: str | None = None,
    notes: str | None = None,
    title: str | None = None,
    details: str | None = None,
) -> dict[str, Any]:
    """
    Create a pending_action only — no escalation/ticket mutation yet.
    """
    action_type = action_type.strip()
    if action_type not in ALLOWED_ACTIONS:
        raise ValueError(
            f"Unknown action_type '{action_type}'. Allowed: {sorted(ALLOWED_ACTIONS)}"
        )

    ticket: Ticket | None = None
    account_id: str

    if action_type in (ACTION_CREATE_ESCALATION, ACTION_UPDATE_TICKET):
        if not ticket_id:
            raise ValueError("ticket_id is required")
        ticket = db.get(Ticket, ticket_id.strip())
        if ticket is None:
            raise LookupError(f"Ticket not found: {ticket_id}")
        assert_account_access(user, ticket.account_id)
        account_id = ticket.account_id
    else:
        # follow-up task may attach to a ticket
        if ticket_id:
            ticket = db.get(Ticket, ticket_id.strip())
            if ticket is None:
                raise LookupError(f"Ticket not found: {ticket_id}")
            assert_account_access(user, ticket.account_id)
            account_id = ticket.account_id
        else:
            if user.account_id:
                account_id = user.account_id
            else:
                raise ValueError("ticket_id or customer account scope is required")

    payload: dict[str, Any]
    if action_type == ACTION_CREATE_ESCALATION:
        if not reason or not recommended_next_step:
            raise ValueError("reason and recommended_next_step are required")
        sev = (severity or "P1").strip().upper()
        if sev not in ("P1", "P2", "P3"):
            raise ValueError("severity must be P1, P2, or P3")
        payload = {
            "ticket_id": ticket.ticket_id if ticket else ticket_id,
            "severity": sev,
            "reason": reason.strip(),
            "recommended_next_step": recommended_next_step.strip(),
        }
    elif action_type == ACTION_UPDATE_TICKET:
        payload = {
            "ticket_id": ticket.ticket_id if ticket else ticket_id,
            "status": status,
            "assigned_to": assigned_to,
            "notes": notes,
        }
        if not any([status, assigned_to, notes]):
            raise ValueError("Provide at least one of status, assigned_to, notes")
    else:
        if not title:
            raise ValueError("title is required for create_follow_up_task")
        payload = {
            "ticket_id": ticket.ticket_id if ticket else ticket_id,
            "title": title.strip(),
            "details": details,
        }

    pending = PendingAction(
        pending_id=_new_id("PA"),
        action_type=action_type,
        status="pending",
        account_id=account_id,
        ticket_id=payload.get("ticket_id"),
        payload=payload,
        created_by=user.persona_id,
        created_at=get_snapshot_at(),
    )
    db.add(pending)
    _write_audit(
        db,
        event="action_proposed",
        actor=user.persona_id,
        pending_action_id=pending.pending_id,
        detail={"action_type": action_type, "payload": payload},
    )
    db.commit()
    db.refresh(pending)

    return {
        "needs_confirmation": True,
        "message": "Action proposed. Confirm to execute; cancel to discard.",
        "pending_action": serialize_pending(pending),
    }


def confirm_action(db: Session, user: AuthUser, pending_id: str) -> dict[str, Any]:
    pending = db.get(PendingAction, pending_id)
    if pending is None:
        raise LookupError(f"Pending action not found: {pending_id}")
    assert_account_access(user, pending.account_id)

    if pending.status != "pending":
        raise ValueError(f"Action is already '{pending.status}' — cannot confirm")

    result_ref: str
    executed: dict[str, Any]

    if pending.action_type == ACTION_CREATE_ESCALATION:
        result_ref, executed = _execute_escalation(db, user, pending)
    elif pending.action_type == ACTION_UPDATE_TICKET:
        result_ref, executed = _execute_update_ticket(db, user, pending)
    elif pending.action_type == ACTION_CREATE_FOLLOW_UP:
        result_ref, executed = _execute_follow_up(db, user, pending)
    else:
        raise ValueError(f"Unsupported action_type: {pending.action_type}")

    pending.status = "confirmed"
    pending.resolved_at = get_snapshot_at()
    pending.resolved_by = user.persona_id
    pending.result_ref = result_ref

    _write_audit(
        db,
        event="action_confirmed",
        actor=user.persona_id,
        pending_action_id=pending.pending_id,
        detail={"result_ref": result_ref, "executed": executed},
    )
    db.commit()
    db.refresh(pending)

    return {
        "needs_confirmation": False,
        "executed": True,
        "result_ref": result_ref,
        "pending_action": serialize_pending(pending),
        "result": executed,
    }


def cancel_action(db: Session, user: AuthUser, pending_id: str) -> dict[str, Any]:
    pending = db.get(PendingAction, pending_id)
    if pending is None:
        raise LookupError(f"Pending action not found: {pending_id}")
    assert_account_access(user, pending.account_id)

    if pending.status != "pending":
        raise ValueError(f"Action is already '{pending.status}' — cannot cancel")

    pending.status = "cancelled"
    pending.resolved_at = get_snapshot_at()
    pending.resolved_by = user.persona_id

    _write_audit(
        db,
        event="action_cancelled",
        actor=user.persona_id,
        pending_action_id=pending.pending_id,
        detail={"action_type": pending.action_type},
    )
    db.commit()
    db.refresh(pending)

    return {
        "needs_confirmation": False,
        "executed": False,
        "pending_action": serialize_pending(pending),
        "message": "Action cancelled; no mutation applied.",
    }


def get_pending_action(db: Session, user: AuthUser, pending_id: str) -> dict[str, Any]:
    pending = db.get(PendingAction, pending_id)
    if pending is None:
        raise LookupError(f"Pending action not found: {pending_id}")
    assert_account_access(user, pending.account_id)
    return serialize_pending(pending)


def _execute_escalation(
    db: Session, user: AuthUser, pending: PendingAction
) -> tuple[str, dict[str, Any]]:
    payload = pending.payload
    esc_id = _new_id("ESC")
    row = Escalation(
        escalation_id=esc_id,
        ticket_id=payload["ticket_id"],
        account_id=pending.account_id,
        severity=payload["severity"],
        reason=payload["reason"],
        recommended_next_step=payload["recommended_next_step"],
        created_by=user.persona_id,
        created_at=get_snapshot_at(),
        pending_action_id=pending.pending_id,
    )
    db.add(row)

    ticket = db.get(Ticket, payload["ticket_id"])
    if ticket is not None and not ticket.assigned_to:
        ticket.assigned_to = "escalations-queue"

    return esc_id, {
        "escalation_id": esc_id,
        "ticket_id": payload["ticket_id"],
        "severity": payload["severity"],
    }


def _execute_update_ticket(
    db: Session, user: AuthUser, pending: PendingAction
) -> tuple[str, dict[str, Any]]:
    payload = pending.payload
    ticket = db.get(Ticket, payload["ticket_id"])
    if ticket is None:
        raise LookupError(f"Ticket not found: {payload['ticket_id']}")

    changed: dict[str, Any] = {}
    if payload.get("status"):
        ticket.status = str(payload["status"])
        changed["status"] = ticket.status
    if payload.get("assigned_to"):
        ticket.assigned_to = str(payload["assigned_to"])
        changed["assigned_to"] = ticket.assigned_to
    if payload.get("notes"):
        note = str(payload["notes"])
        ticket.historical_resolution = (
            f"{ticket.historical_resolution}\n{note}" if ticket.historical_resolution else note
        )
        changed["notes_appended"] = True

    return ticket.ticket_id, {"ticket_id": ticket.ticket_id, "changed": changed}


def _execute_follow_up(
    db: Session, user: AuthUser, pending: PendingAction
) -> tuple[str, dict[str, Any]]:
    payload = pending.payload
    task_id = _new_id("TASK")
    row = FollowUpTask(
        task_id=task_id,
        ticket_id=payload.get("ticket_id"),
        account_id=pending.account_id,
        title=payload["title"],
        details=payload.get("details"),
        created_by=user.persona_id,
        created_at=get_snapshot_at(),
        pending_action_id=pending.pending_id,
        status="open",
    )
    db.add(row)
    return task_id, {"task_id": task_id, "title": payload["title"]}
