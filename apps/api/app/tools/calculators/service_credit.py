from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db.models import Account, Order
from app.timeutil import get_snapshot_at, get_snapshot_tz

SOP_DOC = "03_Cancellation_and_Service_Credit_SOP_v4.pdf"
LUMENWORKS_CONTRACT = "06_LumenWorks_Service_Agreement.pdf"

# Default SOP failed-pickup credit
SOP_LATE_THRESHOLD_HOURS = 2.0
SOP_CREDIT_CAP_INR = 500
SOP_CREDIT_PERCENT = 0.10

# LumenWorks agreement override
LUMEN_LATE_THRESHOLD_HOURS = 4.0
LUMEN_FIXED_CREDIT_INR = 300

# SOP approval gate
MANAGER_APPROVAL_THRESHOLD_INR = 1000


def _aware(dt: datetime) -> datetime:
    tz = get_snapshot_tz()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def _is_lumenworks(account: Account) -> bool:
    if account.contract_file == LUMENWORKS_CONTRACT:
        return True
    return account.account_id == "ACCT-002" and bool(account.contract_file)


def calc_service_credit(order: Order, account: Account) -> dict[str, Any]:
    """
    Failed-pickup service credit (SOP default + LumenWorks override).
    Clock: snapshot_at vs pickup_window_end.
    """
    sources: list[dict[str, str]] = [
        {
            "type": "order",
            "id": order.order_id,
            "note": (
                f"status={order.status}; carrier_fault={order.carrier_fault}; "
                f"customer_fault={order.customer_fault}; fee_inr={order.shipment_fee_inr}"
            ),
        }
    ]

    snapshot = get_snapshot_at()
    window_end = _aware(order.pickup_window_end)
    hours_late = (snapshot - window_end).total_seconds() / 3600.0

    # --- Fault gates ---
    if order.customer_fault:
        sources.append(
            {
                "type": "sop",
                "id": SOP_DOC,
                "note": "Customer fault present → not eligible for failed-pickup credit",
            }
        )
        return _result(
            eligible=False,
            amount_inr=None,
            reason="Not eligible: customer_fault is true. Failed-pickup credit requires no customer fault.",
            sources=sources,
            hours_late=hours_late,
            needs_manager_approval=False,
            agreement_override=False,
            sop_would_amount_inr=None,
            account_id=account.account_id,
            abstain=False,
        )

    if not order.carrier_fault:
        sources.append(
            {
                "type": "sop",
                "id": SOP_DOC,
                "note": "carrier_fault is false/unknown → do not promise credit",
            }
        )
        return _result(
            eligible=False,
            amount_inr=None,
            reason=(
                "Cannot confirm credit: carrier_fault is not true. "
                "Do not promise a service credit until fault attribution is verified."
            ),
            sources=sources,
            hours_late=hours_late,
            needs_manager_approval=False,
            agreement_override=False,
            sop_would_amount_inr=None,
            account_id=account.account_id,
            abstain=True,
        )

    # --- SOP baseline amount (for conflict transparency) ---
    sop_amount: int | None = None
    if hours_late > SOP_LATE_THRESHOLD_HOURS:
        sop_amount = int(
            min(
                SOP_CREDIT_CAP_INR,
                round(order.shipment_fee_inr * SOP_CREDIT_PERCENT),
            )
        )
    sources.append(
        {
            "type": "sop",
            "id": SOP_DOC,
            "note": (
                f"Default: >{SOP_LATE_THRESHOLD_HOURS}h past window end + carrier fault "
                f"+ no customer fault → min(INR {SOP_CREDIT_CAP_INR}, "
                f"{int(SOP_CREDIT_PERCENT * 100)}% of fee). "
                f"hours_late={hours_late:.2f}; SOP amount={sop_amount}."
            ),
        }
    )

    # --- LumenWorks override ---
    if _is_lumenworks(account):
        sources.append(
            {
                "type": "agreement",
                "id": account.contract_file or LUMENWORKS_CONTRACT,
                "note": (
                    f"LumenWorks: >{LUMEN_LATE_THRESHOLD_HOURS}h late + carrier fault "
                    f"+ no customer fault → fixed INR {LUMEN_FIXED_CREDIT_INR} "
                    "(replaces SOP threshold and amount)."
                ),
            }
        )
        if hours_late <= LUMEN_LATE_THRESHOLD_HOURS:
            return _result(
                eligible=False,
                amount_inr=None,
                reason=(
                    f"Not eligible under LumenWorks agreement: pickup is only "
                    f"{hours_late:.2f}h past window end (needs >{LUMEN_LATE_THRESHOLD_HOURS}h)."
                ),
                sources=sources,
                hours_late=hours_late,
                needs_manager_approval=False,
                agreement_override=True,
                sop_would_amount_inr=sop_amount,
                account_id=account.account_id,
                abstain=False,
            )

        amount = LUMEN_FIXED_CREDIT_INR
        needs_approval = amount > MANAGER_APPROVAL_THRESHOLD_INR
        return _result(
            eligible=True,
            amount_inr=amount,
            reason=(
                f"Eligible for INR {amount} service credit under LumenWorks Service Agreement "
                f"({hours_late:.2f}h past pickup window end; carrier fault; no customer fault). "
                f"SOP alone would have suggested INR {sop_amount}; agreement replaces that."
            ),
            sources=sources,
            hours_late=hours_late,
            needs_manager_approval=needs_approval,
            agreement_override=True,
            sop_would_amount_inr=sop_amount,
            account_id=account.account_id,
            abstain=False,
        )

    # --- Default SOP path ---
    if hours_late <= SOP_LATE_THRESHOLD_HOURS:
        return _result(
            eligible=False,
            amount_inr=None,
            reason=(
                f"Not eligible under Cancellation/Service Credit SOP: pickup is only "
                f"{hours_late:.2f}h past window end (needs >{SOP_LATE_THRESHOLD_HOURS}h)."
            ),
            sources=sources,
            hours_late=hours_late,
            needs_manager_approval=False,
            agreement_override=False,
            sop_would_amount_inr=None,
            account_id=account.account_id,
            abstain=False,
        )

    assert sop_amount is not None
    needs_approval = sop_amount > MANAGER_APPROVAL_THRESHOLD_INR
    reason = (
        f"Eligible for INR {sop_amount} service credit per SOP "
        f"(min(INR {SOP_CREDIT_CAP_INR}, {int(SOP_CREDIT_PERCENT * 100)}% of "
        f"INR {order.shipment_fee_inr:.0f}); {hours_late:.2f}h late; carrier fault)."
    )
    if needs_approval:
        reason += (
            f" Amount exceeds INR {MANAGER_APPROVAL_THRESHOLD_INR} — "
            "manager approval required before promising."
        )

    return _result(
        eligible=True,
        amount_inr=sop_amount,
        reason=reason,
        sources=sources,
        hours_late=hours_late,
        needs_manager_approval=needs_approval,
        agreement_override=False,
        sop_would_amount_inr=sop_amount,
        account_id=account.account_id,
        abstain=False,
    )


def _result(
    *,
    eligible: bool,
    amount_inr: int | None,
    reason: str,
    sources: list[dict[str, str]],
    hours_late: float,
    needs_manager_approval: bool,
    agreement_override: bool,
    sop_would_amount_inr: int | None,
    account_id: str,
    abstain: bool,
) -> dict[str, Any]:
    return {
        "eligible": eligible,
        "amount_inr": amount_inr,
        "reason": reason,
        "sources": sources,
        "hours_late": round(hours_late, 2),
        "needs_manager_approval": needs_manager_approval,
        "agreement_override": agreement_override,
        "sop_would_amount_inr": sop_would_amount_inr,
        "account_id": account_id,
        "abstain": abstain,
        "snapshot_at": get_snapshot_at().isoformat(),
    }
