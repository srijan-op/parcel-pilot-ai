from datetime import datetime, timezone

from app.db.models import Account, Ticket
from app.tools.calculators.sla import calc_sla, classify_severity


def _ticket(
    *,
    ticket_id: str,
    account_id: str,
    created_at: str,
    subject: str,
    description: str,
) -> Ticket:
    return Ticket(
        ticket_id=ticket_id,
        account_id=account_id,
        created_at=datetime.fromisoformat(created_at).replace(tzinfo=timezone.utc),
        status="open",
        subject=subject,
        description=description,
        channel="chat",
        assigned_to=None,
        last_customer_message_at=None,
        historical_resolution=None,
    )


def _account(account_id: str, plan: str, contract_file: str | None) -> Account:
    return Account(
        account_id=account_id,
        account_name="Test",
        plan=plan,
        status="active",
        csm=None,
        contract_file=contract_file,
        premium_support=False,
        notes=None,
    )


def test_g9_tkt_501_northstar_p1_breached() -> None:
    # created 05:00 UTC = 10:30 IST; snapshot 11:00 IST → 30 min elapsed; target 15
    ticket = _ticket(
        ticket_id="TKT-501",
        account_id="ACCT-001",
        created_at="2026-08-16T05:00:00",
        subject="All shipment creation is failing",
        description="Every user at Northstar gets HTTP 500 when creating any shipment.",
    )
    account = _account(
        "ACCT-001", "Enterprise", "05_Northstar_Logistics_Enterprise_Agreement.pdf"
    )
    result = calc_sla(ticket, account)
    assert result["severity"] == "P1"
    assert result["target_minutes"] == 15
    assert result["elapsed_minutes"] == 30
    assert result["breached"] is True
    assert result["agreement_override"] is True
    assert result["policy_default_minutes"] == 30
    assert result["recommend_escalation"] is True


def test_g10_tkt_505_enterprise_p1_breached() -> None:
    # created 03:00 UTC = 08:30 IST; snapshot 11:00 → 150 min; Enterprise default 30
    ticket = _ticket(
        ticket_id="TKT-505",
        account_id="ACCT-004",
        created_at="2026-08-16T03:00:00",
        subject="Possible API key exposure",
        description="An employee accidentally posted a screenshot containing a production API key.",
    )
    account = _account("ACCT-004", "Enterprise", None)
    result = calc_sla(ticket, account)
    assert result["severity"] == "P1"
    assert result["target_minutes"] == 30
    assert result["elapsed_minutes"] == 150
    assert result["breached"] is True
    assert result["agreement_override"] is False


def test_tkt_503_billing_is_p3() -> None:
    ticket = _ticket(
        ticket_id="TKT-503",
        account_id="ACCT-003",
        created_at="2026-08-16T04:35:00",
        subject="How do we change the billing contact?",
        description="Customer wants to replace the billing-contact email on their account.",
    )
    sev, _ = classify_severity(ticket)
    assert sev == "P3"


def test_severity_override() -> None:
    ticket = _ticket(
        ticket_id="TKT-503",
        account_id="ACCT-003",
        created_at="2026-08-16T04:35:00",
        subject="How do we change the billing contact?",
        description="Customer wants to replace the billing-contact email.",
    )
    account = _account("ACCT-003", "Standard", None)
    result = calc_sla(ticket, account, severity="P2")
    assert result["severity"] == "P2"
    assert result["target_minutes"] == 24 * 60
