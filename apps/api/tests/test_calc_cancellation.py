from datetime import datetime, timezone

from app.db.models import Account, Order
from app.tools.calculators.cancellation import calc_cancellation


def _order(
    *,
    order_id: str,
    account_id: str,
    status: str,
    booked_at: str,
    cancel_at: str | None,
    pickup_actual_at: str | None = None,
) -> Order:
    return Order(
        order_id=order_id,
        account_id=account_id,
        carrier="TestCarrier",
        status=status,
        booked_at=datetime.fromisoformat(booked_at).replace(tzinfo=timezone.utc),
        pickup_window_start=datetime.fromisoformat(booked_at).replace(tzinfo=timezone.utc),
        pickup_window_end=datetime.fromisoformat(booked_at).replace(tzinfo=timezone.utc),
        pickup_actual_at=(
            datetime.fromisoformat(pickup_actual_at).replace(tzinfo=timezone.utc)
            if pickup_actual_at
            else None
        ),
        shipment_fee_inr=1000.0,
        carrier_fault=False,
        customer_fault=False,
        cancellation_requested_at=(
            datetime.fromisoformat(cancel_at).replace(tzinfo=timezone.utc) if cancel_at else None
        ),
        notes=None,
    )


def _account(account_id: str, contract_file: str | None) -> Account:
    return Account(
        account_id=account_id,
        account_name="Test",
        plan="Enterprise",
        status="active",
        csm=None,
        contract_file=contract_file,
        premium_support=False,
        notes=None,
    )


def test_g1_northstar_ord_1001_no_fee() -> None:
    order = _order(
        order_id="ORD-1001",
        account_id="ACCT-001",
        status="BOOKED",
        booked_at="2026-08-16T03:30:00",
        cancel_at="2026-08-16T05:30:00",
    )
    account = _account("ACCT-001", "05_Northstar_Logistics_Enterprise_Agreement.pdf")
    result = calc_cancellation(order, account)
    assert result["allowed"] is True
    assert result["fee_inr"] == 0
    assert result["agreement_override"] is True
    assert result["sop_would_charge_inr"] == 250
    assert result["minutes_since_booking"] == 120


def test_g2_lumenworks_ord_2001_fee_250() -> None:
    order = _order(
        order_id="ORD-2001",
        account_id="ACCT-002",
        status="BOOKED",
        booked_at="2026-08-16T03:30:00",
        cancel_at="2026-08-16T04:45:00",
    )
    account = _account("ACCT-002", "06_LumenWorks_Service_Agreement.pdf")
    result = calc_cancellation(order, account)
    assert result["allowed"] is True
    assert result["fee_inr"] == 250
    assert result["agreement_override"] is False
    assert result["minutes_since_booking"] == 75


def test_g3_beacon_ord_3001_within_30_min() -> None:
    order = _order(
        order_id="ORD-3001",
        account_id="ACCT-003",
        status="BOOKED",
        booked_at="2026-08-16T04:55:00",
        cancel_at="2026-08-16T05:10:00",
    )
    account = _account("ACCT-003", None)
    result = calc_cancellation(order, account)
    assert result["allowed"] is True
    assert result["fee_inr"] == 0
    assert result["minutes_since_booking"] == 15


def test_g4_ord_1002_picked_up_rto() -> None:
    order = _order(
        order_id="ORD-1002",
        account_id="ACCT-001",
        status="PICKED_UP",
        booked_at="2026-08-16T02:40:00",
        cancel_at="2026-08-16T04:50:00",
        pickup_actual_at="2026-08-16T04:05:00",
    )
    account = _account("ACCT-001", "05_Northstar_Logistics_Enterprise_Agreement.pdf")
    result = calc_cancellation(order, account)
    assert result["allowed"] is False
    assert result["fee_inr"] is None
    assert "RTO" in result["reason"] or "return-to-origin" in result["reason"].lower()


def test_g5_ord_4001_delivered() -> None:
    order = _order(
        order_id="ORD-4001",
        account_id="ACCT-004",
        status="DELIVERED",
        booked_at="2026-08-14T08:30:00",
        cancel_at=None,
        pickup_actual_at="2026-08-15T03:50:00",
    )
    account = _account("ACCT-004", None)
    result = calc_cancellation(order, account)
    assert result["allowed"] is False
    assert "DELIVERED" in result["reason"]
