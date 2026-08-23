from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db.models import Account, Order
from app.timeutil import get_snapshot_at, get_snapshot_tz

SOP_FREE_WINDOW_MINUTES = 30
SOP_LATE_FEE_INR = 250

NORTHSTAR_CONTRACT = "05_Northstar_Logistics_Enterprise_Agreement.pdf"
SOP_DOC = "03_Cancellation_and_Service_Credit_SOP_v4.pdf"


def _aware(dt: datetime) -> datetime:
    tz = get_snapshot_tz()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def _has_northstar_cancel_waiver(account: Account) -> bool:
    """Agreement rule: BOOKED pre-pickup → no fee (ACCT-001 Northstar)."""
    if account.contract_file == NORTHSTAR_CONTRACT:
        return True
    return account.account_id == "ACCT-001" and bool(account.contract_file)


def calc_cancellation(order: Order, account: Account) -> dict[str, Any]:
    """
    Deterministic cancellation rules from SOP + account agreements.
    Uses cancellation_requested_at when present, else snapshot clock.
    """
    status = (order.status or "").strip().upper()
    sources: list[dict[str, str]] = [
        {
            "type": "order",
            "id": order.order_id,
            "note": f"status={status}",
        }
    ]

    decision_at = order.cancellation_requested_at or get_snapshot_at()
    decision_at = _aware(decision_at)
    booked_at = _aware(order.booked_at)
    minutes_since_booking = max(
        0, int((decision_at - booked_at).total_seconds() // 60)
    )

    # --- Terminal / post-pickup statuses ---
    if status == "DELIVERED":
        sources.append(
            {
                "type": "sop",
                "id": SOP_DOC,
                "note": "DELIVERED orders cannot be cancelled",
            }
        )
        return _result(
            allowed=False,
            fee_inr=None,
            reason="Order is DELIVERED; cancellation is not allowed.",
            sources=sources,
            minutes_since_booking=minutes_since_booking,
            sop_would_charge_inr=None,
            agreement_override=False,
            status=status,
            account_id=account.account_id,
        )

    if status == "PICKED_UP" or order.pickup_actual_at is not None:
        sources.append(
            {
                "type": "sop",
                "id": SOP_DOC,
                "note": "PICKED_UP → do not cancel; use return-to-origin (RTO)",
            }
        )
        return _result(
            allowed=False,
            fee_inr=None,
            reason=(
                "Order is already PICKED_UP (or pickup confirmed). "
                "Do not cancel in-place; use return-to-origin (RTO) workflow."
            ),
            sources=sources,
            minutes_since_booking=minutes_since_booking,
            sop_would_charge_inr=None,
            agreement_override=False,
            status=status,
            account_id=account.account_id,
        )

    if status == "DRAFT":
        sources.append(
            {
                "type": "sop",
                "id": SOP_DOC,
                "note": "DRAFT → cancel with no fee",
            }
        )
        return _result(
            allowed=True,
            fee_inr=0,
            reason="Order is DRAFT; cancellation allowed with no fee (SOP).",
            sources=sources,
            minutes_since_booking=minutes_since_booking,
            sop_would_charge_inr=0,
            agreement_override=False,
            status=status,
            account_id=account.account_id,
        )

    if status != "BOOKED":
        sources.append(
            {
                "type": "sop",
                "id": SOP_DOC,
                "note": f"Unsupported status for cancellation calc: {status}",
            }
        )
        return _result(
            allowed=False,
            fee_inr=None,
            reason=f"Cancellation rules are not defined for status '{status}'.",
            sources=sources,
            minutes_since_booking=minutes_since_booking,
            sop_would_charge_inr=None,
            agreement_override=False,
            status=status,
            account_id=account.account_id,
        )

    # --- BOOKED, not picked up ---
    sop_fee = 0 if minutes_since_booking <= SOP_FREE_WINDOW_MINUTES else SOP_LATE_FEE_INR
    sources.append(
        {
            "type": "sop",
            "id": SOP_DOC,
            "note": (
                f"BOOKED: free within {SOP_FREE_WINDOW_MINUTES} min of booking; "
                f"else ₹{SOP_LATE_FEE_INR}. Elapsed={minutes_since_booking} min → SOP fee ₹{sop_fee}."
            ),
        }
    )

    if _has_northstar_cancel_waiver(account):
        sources.append(
            {
                "type": "agreement",
                "id": account.contract_file or NORTHSTAR_CONTRACT,
                "note": (
                    "Northstar agreement: any BOOKED order before pickup "
                    "has no cancellation fee (overrides SOP time window)."
                ),
            }
        )
        return _result(
            allowed=True,
            fee_inr=0,
            reason=(
                "Cancellation allowed with no fee. "
                "Northstar Logistics Enterprise Agreement waives the SOP ₹250 "
                f"fee for BOOKED pre-pickup orders (elapsed {minutes_since_booking} min)."
            ),
            sources=sources,
            minutes_since_booking=minutes_since_booking,
            sop_would_charge_inr=sop_fee,
            agreement_override=True,
            status=status,
            account_id=account.account_id,
        )

    if sop_fee == 0:
        reason = (
            f"Cancellation allowed with no fee. "
            f"Request is within {SOP_FREE_WINDOW_MINUTES} minutes of booking "
            f"({minutes_since_booking} min elapsed) per Cancellation SOP."
        )
    else:
        reason = (
            f"Cancellation allowed with fee ₹{sop_fee}. "
            f"Request is {minutes_since_booking} minutes after booking "
            f"(> {SOP_FREE_WINDOW_MINUTES} min free window) per Cancellation SOP. "
            "No account agreement waives this fee."
        )

    return _result(
        allowed=True,
        fee_inr=sop_fee,
        reason=reason,
        sources=sources,
        minutes_since_booking=minutes_since_booking,
        sop_would_charge_inr=sop_fee,
        agreement_override=False,
        status=status,
        account_id=account.account_id,
    )


def _result(
    *,
    allowed: bool,
    fee_inr: int | None,
    reason: str,
    sources: list[dict[str, str]],
    minutes_since_booking: int,
    sop_would_charge_inr: int | None,
    agreement_override: bool,
    status: str,
    account_id: str,
) -> dict[str, Any]:
    return {
        "allowed": allowed,
        "fee_inr": fee_inr,
        "reason": reason,
        "sources": sources,
        "minutes_since_booking": minutes_since_booking,
        "sop_would_charge_inr": sop_would_charge_inr,
        "agreement_override": agreement_override,
        "status": status,
        "account_id": account_id,
        "snapshot_at": get_snapshot_at().isoformat(),
    }
