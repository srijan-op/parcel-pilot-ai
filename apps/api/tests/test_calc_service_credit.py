from datetime import datetime, timezone

from app.db.models import Account, Order
from app.tools.calculators.service_credit import calc_service_credit


def _order(
    *,
    order_id: str,
    account_id: str,
    window_end: str,
    fee: float,
    carrier_fault: bool,
    customer_fault: bool,
) -> Order:
    end = datetime.fromisoformat(window_end).replace(tzinfo=timezone.utc)
    return Order(
        order_id=order_id,
        account_id=account_id,
        carrier="TestCarrier",
        status="BOOKED",
        booked_at=end,
        pickup_window_start=end,
        pickup_window_end=end,
        pickup_actual_at=None,
        shipment_fee_inr=fee,
        carrier_fault=carrier_fault,
        customer_fault=customer_fault,
        cancellation_requested_at=None,
        notes=None,
    )


def _account(account_id: str, contract_file: str | None) -> Account:
    return Account(
        account_id=account_id,
        account_name="Test",
        plan="Growth",
        status="active",
        csm=None,
        contract_file=contract_file,
        premium_support=False,
        notes=None,
    )


def test_g6_lumenworks_ord_2002_credit_300() -> None:
    # Snapshot 11:00 IST = 05:30 UTC; window end 01:00 UTC → 4.5h late
    order = _order(
        order_id="ORD-2002",
        account_id="ACCT-002",
        window_end="2026-08-16T01:00:00",
        fee=2400.0,
        carrier_fault=True,
        customer_fault=False,
    )
    account = _account("ACCT-002", "06_LumenWorks_Service_Agreement.pdf")
    result = calc_service_credit(order, account)
    assert result["eligible"] is True
    assert result["amount_inr"] == 300
    assert result["agreement_override"] is True
    assert result["sop_would_amount_inr"] == 240  # min(500, 10% of 2400)
    assert result["needs_manager_approval"] is False
    assert result["hours_late"] == 4.5


def test_g7_no_carrier_fault_abstain() -> None:
    order = _order(
        order_id="ORD-X",
        account_id="ACCT-003",
        window_end="2026-08-16T01:00:00",
        fee=2000.0,
        carrier_fault=False,
        customer_fault=False,
    )
    account = _account("ACCT-003", None)
    result = calc_service_credit(order, account)
    assert result["eligible"] is False
    assert result["abstain"] is True
    assert result["amount_inr"] is None


def test_sop_credit_when_not_lumenworks() -> None:
    order = _order(
        order_id="ORD-Y",
        account_id="ACCT-003",
        window_end="2026-08-16T01:00:00",
        fee=2400.0,
        carrier_fault=True,
        customer_fault=False,
    )
    account = _account("ACCT-003", None)
    result = calc_service_credit(order, account)
    assert result["eligible"] is True
    assert result["amount_inr"] == 240
    assert result["agreement_override"] is False


def test_customer_fault_blocks_credit() -> None:
    order = _order(
        order_id="ORD-Z",
        account_id="ACCT-002",
        window_end="2026-08-16T01:00:00",
        fee=2400.0,
        carrier_fault=True,
        customer_fault=True,
    )
    account = _account("ACCT-002", "06_LumenWorks_Service_Agreement.pdf")
    result = calc_service_credit(order, account)
    assert result["eligible"] is False
    assert result["abstain"] is False
