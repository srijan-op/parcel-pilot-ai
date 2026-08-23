from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from app.db.models import Account, Ticket
from app.timeutil import get_snapshot_at, get_snapshot_tz

Severity = Literal["P1", "P2", "P3"]

POLICY_DOC = "01_Support_Policy_v3_CURRENT.pdf"
NORTHSTAR_CONTRACT = "05_Northstar_Logistics_Enterprise_Agreement.pdf"
LUMENWORKS_CONTRACT = "06_LumenWorks_Service_Agreement.pdf"

# Policy v3 defaults (first-response), minutes. "business hours/days" → calendar minutes approx for snapshot math.
DEFAULT_TARGETS_MIN: dict[str, dict[Severity, int]] = {
    "Enterprise": {"P1": 30, "P2": 120, "P3": 24 * 60},
    "Growth": {"P1": 2 * 60, "P2": 4 * 60, "P3": 2 * 24 * 60},
    "Standard": {"P1": 4 * 60, "P2": 24 * 60, "P3": 2 * 24 * 60},
}

# Northstar agreement overrides (24x7 for P1/P2)
NORTHSTAR_TARGETS_MIN: dict[Severity, int] = {
    "P1": 15,
    "P2": 60,
    "P3": 8 * 60,  # 8 business hours approximated
}

# LumenWorks: no weekend/after-hours; P1=2 BH, P2=4 BH, P3=2 BD
LUMENWORKS_TARGETS_MIN: dict[Severity, int] = {
    "P1": 2 * 60,
    "P2": 4 * 60,
    "P3": 2 * 24 * 60,
}

AT_RISK_RATIO = 0.80


def _aware(dt: datetime) -> datetime:
    tz = get_snapshot_tz()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def classify_severity(ticket: Ticket, severity_override: str | None = None) -> tuple[Severity, str]:
    """Return (severity, rationale). Optional explicit override wins."""
    if severity_override:
        sev = severity_override.strip().upper()
        if sev not in ("P1", "P2", "P3"):
            raise ValueError("severity must be P1, P2, or P3")
        return sev, f"Severity provided by caller: {sev}"  # type: ignore[return-value]

    text = f"{ticket.subject or ''} {ticket.description or ''}".lower()

    p1_signals = (
        "all shipment",
        "http 500",
        "complete",
        "outage",
        "api key",
        "credential",
        "security",
        "exposure",
        "production api key",
    )
    if any(s in text for s in p1_signals):
        return "P1", "Classified P1 from subject/description (critical outage or security risk)"

    p2_signals = ("fails", "failure", "degraded", "bulk upload fails", "major")
    if any(s in text for s in p2_signals):
        return "P2", "Classified P2 from subject/description (major feature impact with workaround possible)"

    return "P3", "Classified P3 from subject/description (how-to / limited operational impact)"


def resolve_sla_target(
    account: Account, severity: Severity
) -> tuple[int, str, str, bool]:
    """
    Returns (target_minutes, source_label, source_doc, agreement_override).
    Precedence: signed agreement → Support Policy v3 by plan.
    """
    plan = (account.plan or "Standard").strip()

    if account.contract_file == NORTHSTAR_CONTRACT or (
        account.account_id == "ACCT-001" and account.contract_file
    ):
        minutes = NORTHSTAR_TARGETS_MIN[severity]
        return (
            minutes,
            f"Northstar Logistics Enterprise Agreement ({severity})",
            account.contract_file or NORTHSTAR_CONTRACT,
            True,
        )

    if account.contract_file == LUMENWORKS_CONTRACT or (
        account.account_id == "ACCT-002" and account.contract_file
    ):
        minutes = LUMENWORKS_TARGETS_MIN[severity]
        return (
            minutes,
            f"LumenWorks Service Agreement ({severity}; no weekend/after-hours coverage)",
            account.contract_file or LUMENWORKS_CONTRACT,
            True,
        )

    plan_key = plan if plan in DEFAULT_TARGETS_MIN else "Standard"
    minutes = DEFAULT_TARGETS_MIN[plan_key][severity]
    return (
        minutes,
        f"Support Policy v3 default for {plan_key} {severity}",
        POLICY_DOC,
        False,
    )


def calc_sla(
    ticket: Ticket,
    account: Account,
    *,
    severity: str | None = None,
) -> dict[str, Any]:
    """First-response SLA vs snapshot clock."""
    sev, sev_reason = classify_severity(ticket, severity)
    target_min, target_label, target_doc, agreement_override = resolve_sla_target(account, sev)

    created = _aware(ticket.created_at)
    snapshot = get_snapshot_at()
    elapsed_min = max(0, int((snapshot - created).total_seconds() // 60))
    remaining_min = target_min - elapsed_min
    breached = elapsed_min > target_min
    at_risk = (not breached) and elapsed_min >= int(target_min * AT_RISK_RATIO)

    policy_default = DEFAULT_TARGETS_MIN.get(
        (account.plan or "Standard").strip(), DEFAULT_TARGETS_MIN["Standard"]
    )[sev]

    sources: list[dict[str, str]] = [
        {
            "type": "ticket",
            "id": ticket.ticket_id,
            "note": f"created_at={created.isoformat()}; status={ticket.status}",
        },
        {
            "type": "policy",
            "id": POLICY_DOC,
            "note": sev_reason,
        },
        {
            "type": "agreement" if agreement_override else "policy",
            "id": target_doc,
            "note": f"{target_label}: target={target_min} min (policy default for plan would be {policy_default} min)",
        },
    ]

    if breached:
        reason = (
            f"{sev} first-response SLA BREACHED. "
            f"Target {target_min} min from {target_label}; "
            f"elapsed {elapsed_min} min at snapshot. State the breach and recommend escalation."
        )
    elif at_risk:
        reason = (
            f"{sev} first-response SLA at risk (>80% of target consumed). "
            f"Target {target_min} min; elapsed {elapsed_min} min; remaining {remaining_min} min."
        )
    else:
        reason = (
            f"{sev} first-response SLA within target. "
            f"Target {target_min} min; elapsed {elapsed_min} min; remaining {remaining_min} min."
        )

    return {
        "ticket_id": ticket.ticket_id,
        "account_id": account.account_id,
        "plan": account.plan,
        "severity": sev,
        "severity_reason": sev_reason,
        "target_minutes": target_min,
        "elapsed_minutes": elapsed_min,
        "remaining_minutes": remaining_min,
        "breached": breached,
        "at_risk": at_risk,
        "recommend_escalation": breached or sev == "P1",
        "target_source": target_label,
        "agreement_override": agreement_override,
        "policy_default_minutes": policy_default,
        "reason": reason,
        "sources": sources,
        "snapshot_at": snapshot.isoformat(),
        "created_at": created.isoformat(),
    }
