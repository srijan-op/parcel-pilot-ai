from types import SimpleNamespace

from app.tools.structured_data import (
    _order_matches_ticket_context,
    extract_order_ids_from_text,
)


def test_extract_order_ids_from_text_dedupes_and_normalizes() -> None:
    ids = extract_order_ids_from_text(
        "Please check ORD-1001 and ord-1002",
        "Follow up on ORD-1001",
    )
    assert ids == ["ORD-1001", "ORD-1002"]


def test_extract_order_ids_empty_when_missing() -> None:
    assert extract_order_ids_from_text(None, "") == []


def test_order_matches_ticket_context_by_carrier_name() -> None:
    ticket = SimpleNamespace(
        subject="SwiftShip order still shows BOOKED after driver pickup",
        description="Driver collected the parcel around 10 minutes ago.",
        historical_resolution=None,
    )
    order = SimpleNamespace(
        order_id="ORD-1001",
        carrier="SwiftShip",
        status="BOOKED",
    )
    assert _order_matches_ticket_context(order, ticket, []) is True


def test_order_matches_ticket_context_by_explicit_order_id() -> None:
    ticket = SimpleNamespace(
        subject="Question about ORD-2002 credit",
        description=None,
        historical_resolution=None,
    )
    order = SimpleNamespace(
        order_id="ORD-2002",
        carrier="BlueDart Pro",
        status="PICKED_UP",
    )
    assert _order_matches_ticket_context(order, ticket, ["ORD-2002"]) is True


def test_order_matches_ticket_context_rejects_unrelated_order() -> None:
    ticket = SimpleNamespace(
        subject="SwiftShip order still shows BOOKED after driver pickup",
        description=None,
        historical_resolution=None,
    )
    order = SimpleNamespace(
        order_id="ORD-1002",
        carrier="BlueDart Pro",
        status="PICKED_UP",
    )
    assert _order_matches_ticket_context(order, ticket, []) is False
