from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.acl import ACLError, assert_account_access, resolve_account_scope
from app.auth.models import AuthUser
from app.db.models import Account, Order, Ticket
from app.tools.calculators.cancellation import calc_cancellation
from app.tools.calculators.service_credit import calc_service_credit
from app.tools.calculators.sla import calc_sla

LOOKUP_INTENTS = frozenset(
    {
        "get_account",
        "get_order",
        "list_orders",
        "get_ticket",
        "list_tickets",
    }
)

CALC_INTENTS = frozenset(
    {
        "calc_cancellation",
        "calc_service_credit",
        "calc_sla",
    }
)

READY_CALC_INTENTS = frozenset({"calc_cancellation", "calc_service_credit", "calc_sla"})
PENDING_CALC_INTENTS = CALC_INTENTS - READY_CALC_INTENTS

ALL_INTENTS = LOOKUP_INTENTS | READY_CALC_INTENTS

_ORDER_ID_RE = re.compile(r"ORD-\d+", re.IGNORECASE)


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def serialize_account(row: Account) -> dict[str, Any]:
    return {
        "account_id": row.account_id,
        "account_name": row.account_name,
        "plan": row.plan,
        "status": row.status,
        "csm": row.csm,
        "contract_file": row.contract_file,
        "premium_support": row.premium_support,
        "notes": row.notes,
    }


def serialize_order(row: Order) -> dict[str, Any]:
    return {
        "order_id": row.order_id,
        "account_id": row.account_id,
        "carrier": row.carrier,
        "status": row.status,
        "booked_at": _dt(row.booked_at),
        "pickup_window_start": _dt(row.pickup_window_start),
        "pickup_window_end": _dt(row.pickup_window_end),
        "pickup_actual_at": _dt(row.pickup_actual_at),
        "shipment_fee_inr": row.shipment_fee_inr,
        "carrier_fault": row.carrier_fault,
        "customer_fault": row.customer_fault,
        "cancellation_requested_at": _dt(row.cancellation_requested_at),
        "notes": row.notes,
    }


def serialize_ticket(row: Ticket) -> dict[str, Any]:
    return {
        "ticket_id": row.ticket_id,
        "account_id": row.account_id,
        "created_at": _dt(row.created_at),
        "status": row.status,
        "subject": row.subject,
        "description": row.description,
        "channel": row.channel,
        "assigned_to": row.assigned_to,
        "last_customer_message_at": _dt(row.last_customer_message_at),
        "historical_resolution": row.historical_resolution,
    }


def extract_order_ids_from_text(*texts: str | None) -> list[str]:
    """Parse ORD-#### references from ticket text fields."""
    found: list[str] = []
    seen: set[str] = set()
    for text in texts:
        if not text:
            continue
        for match in _ORDER_ID_RE.findall(text):
            order_id = match.upper()
            if order_id not in seen:
                seen.add(order_id)
                found.append(order_id)
    return found


def _ticket_text_blob(ticket: Ticket) -> str:
    parts = [ticket.subject or "", ticket.description or "", ticket.historical_resolution or ""]
    return " ".join(parts)


def _order_matches_ticket_context(order: Order, ticket: Ticket, parsed_order_ids: list[str]) -> bool:
    if order.order_id in parsed_order_ids:
        return True

    haystack = _ticket_text_blob(ticket).lower()
    if not haystack:
        return False

    carrier = (order.carrier or "").strip().lower()
    if carrier and carrier in haystack:
        return True

    status = (order.status or "").strip().upper()
    if status and status in haystack.upper():
        # Require carrier or explicit order id hint to avoid listing every BOOKED order.
        if carrier and carrier in haystack:
            return True

    return False


def related_orders_for_ticket(db: Session, ticket: Ticket) -> list[Order]:
    """
    Orders linked to a ticket by explicit ORD-#### mentions or subject/description
    hints (carrier name, status keywords).
    """
    parsed_order_ids = extract_order_ids_from_text(
        ticket.subject,
        ticket.description,
        ticket.historical_resolution,
    )

    account_orders = list(
        db.scalars(
            select(Order)
            .where(Order.account_id == ticket.account_id)
            .order_by(Order.booked_at.desc())
        ).all()
    )

    related: list[Order] = []
    seen: set[str] = set()

    for order_id in parsed_order_ids:
        row = db.get(Order, order_id)
        if row is None or row.account_id != ticket.account_id:
            continue
        if row.order_id not in seen:
            seen.add(row.order_id)
            related.append(row)

    for row in account_orders:
        if row.order_id in seen:
            continue
        if _order_matches_ticket_context(row, ticket, parsed_order_ids):
            seen.add(row.order_id)
            related.append(row)

    return related


def structured_data_query(
    db: Session,
    user: AuthUser,
    *,
    intent: str,
    account_id: str | None = None,
    order_id: str | None = None,
    ticket_id: str | None = None,
    status: str | None = None,
    severity: str | None = None,
) -> dict[str, Any]:
    """
    Parameterized structured lookups + ready calculators (no raw SQL from the model).
    """
    intent = intent.strip().lower()

    if intent in PENDING_CALC_INTENTS:
        raise ValueError(
            f"Intent '{intent}' is not available yet (later Phase B). "
            f"Ready now: {sorted(ALL_INTENTS)}"
        )
    if intent not in ALL_INTENTS:
        raise ValueError(
            f"Unknown intent '{intent}'. Supported: {sorted(ALL_INTENTS)}"
        )

    if intent == "get_account":
        return _get_account(db, user, account_id)
    if intent == "get_order":
        return _get_order(db, user, order_id)
    if intent == "list_orders":
        return _list_orders(db, user, account_id=account_id, status=status)
    if intent == "get_ticket":
        return _get_ticket(db, user, ticket_id)
    if intent == "list_tickets":
        return _list_tickets(db, user, account_id=account_id, status=status)
    if intent == "calc_cancellation":
        return _calc_cancellation(db, user, order_id)
    if intent == "calc_service_credit":
        return _calc_service_credit(db, user, order_id)
    if intent == "calc_sla":
        return _calc_sla(db, user, ticket_id, severity=severity)

    raise ValueError(f"Unhandled intent: {intent}")


def _calc_cancellation(
    db: Session, user: AuthUser, order_id: str | None
) -> dict[str, Any]:
    oid = _require("order_id", order_id)
    order = db.get(Order, oid)
    if order is None:
        raise LookupError(f"Order not found: {oid}")
    assert_account_access(user, order.account_id)

    account = db.get(Account, order.account_id)
    if account is None:
        raise LookupError(f"Account not found for order: {order.account_id}")

    result = calc_cancellation(order, account)
    return {
        "intent": "calc_cancellation",
        "order_id": oid,
        "data": result,
    }


def _calc_service_credit(
    db: Session, user: AuthUser, order_id: str | None
) -> dict[str, Any]:
    oid = _require("order_id", order_id)
    order = db.get(Order, oid)
    if order is None:
        raise LookupError(f"Order not found: {oid}")
    assert_account_access(user, order.account_id)

    account = db.get(Account, order.account_id)
    if account is None:
        raise LookupError(f"Account not found for order: {order.account_id}")

    result = calc_service_credit(order, account)
    return {
        "intent": "calc_service_credit",
        "order_id": oid,
        "data": result,
    }


def _calc_sla(
    db: Session,
    user: AuthUser,
    ticket_id: str | None,
    *,
    severity: str | None,
) -> dict[str, Any]:
    tid = _require("ticket_id", ticket_id)
    ticket = db.get(Ticket, tid)
    if ticket is None:
        raise LookupError(f"Ticket not found: {tid}")
    assert_account_access(user, ticket.account_id)

    account = db.get(Account, ticket.account_id)
    if account is None:
        raise LookupError(f"Account not found for ticket: {ticket.account_id}")

    result = calc_sla(ticket, account, severity=severity)
    return {
        "intent": "calc_sla",
        "ticket_id": tid,
        "data": result,
    }


def _require(param: str, value: str | None) -> str:
    if not value or not value.strip():
        raise ValueError(f"Missing required parameter: {param}")
    return value.strip()


def _get_account(db: Session, user: AuthUser, account_id: str | None) -> dict[str, Any]:
    target = resolve_account_scope(user, account_id)
    if target is None:
        raise ValueError("account_id is required for get_account (or login as a customer)")
    assert_account_access(user, target)

    row = db.get(Account, target)
    if row is None:
        raise LookupError(f"Account not found: {target}")
    return {"intent": "get_account", "data": serialize_account(row)}


def _get_order(db: Session, user: AuthUser, order_id: str | None) -> dict[str, Any]:
    oid = _require("order_id", order_id)
    row = db.get(Order, oid)
    if row is None:
        raise LookupError(f"Order not found: {oid}")
    assert_account_access(user, row.account_id)
    return {"intent": "get_order", "data": serialize_order(row)}


def _list_orders(
    db: Session,
    user: AuthUser,
    *,
    account_id: str | None,
    status: str | None,
) -> dict[str, Any]:
    scoped = resolve_account_scope(user, account_id)
    stmt = select(Order).order_by(Order.booked_at.desc())
    if scoped:
        stmt = stmt.where(Order.account_id == scoped)
    if status:
        stmt = stmt.where(Order.status == status.strip().upper())

    rows = list(db.scalars(stmt).all())
    return {
        "intent": "list_orders",
        "scoped_account_id": scoped,
        "count": len(rows),
        "data": [serialize_order(r) for r in rows],
    }


def _get_ticket(db: Session, user: AuthUser, ticket_id: str | None) -> dict[str, Any]:
    tid = _require("ticket_id", ticket_id)
    row = db.get(Ticket, tid)
    if row is None:
        raise LookupError(f"Ticket not found: {tid}")
    assert_account_access(user, row.account_id)

    parsed_order_ids = extract_order_ids_from_text(
        row.subject,
        row.description,
        row.historical_resolution,
    )
    related = related_orders_for_ticket(db, row)

    payload = serialize_ticket(row)
    payload["parsed_order_ids"] = parsed_order_ids
    payload["related_orders"] = [serialize_order(order) for order in related]

    return {"intent": "get_ticket", "data": payload}


def _list_tickets(
    db: Session,
    user: AuthUser,
    *,
    account_id: str | None,
    status: str | None,
) -> dict[str, Any]:
    scoped = resolve_account_scope(user, account_id)
    stmt = select(Ticket).order_by(Ticket.created_at.desc())
    if scoped:
        stmt = stmt.where(Ticket.account_id == scoped)
    if status:
        stmt = stmt.where(Ticket.status == status.strip())

    rows = list(db.scalars(stmt).all())
    return {
        "intent": "list_tickets",
        "scoped_account_id": scoped,
        "count": len(rows),
        "data": [serialize_ticket(r) for r in rows],
    }


__all__ = [
    "ACLError",
    "ALL_INTENTS",
    "LOOKUP_INTENTS",
    "READY_CALC_INTENTS",
    "extract_order_ids_from_text",
    "related_orders_for_ticket",
    "structured_data_query",
]
