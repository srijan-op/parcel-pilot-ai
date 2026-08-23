import json

from app.trust.synthesis import synthesize_trust


def test_cancel_fee_agreement_override_conflict() -> None:
    tools_used = [
        {
            "tool": "structured_data_query",
            "args": {"intent": "calc_cancellation", "order_id": "ORD-1001"},
            "result_preview": json.dumps(
                {
                    "intent": "calc_cancellation",
                    "data": {
                        "allowed": True,
                        "fee_inr": 0,
                        "sop_would_charge_inr": 250,
                        "agreement_override": True,
                        "sources": [
                            {"type": "sop", "id": "03_SOP.pdf", "note": "would charge 250"},
                            {
                                "type": "agreement",
                                "id": "05_Northstar.pdf",
                                "note": "waives fee",
                            },
                        ],
                    },
                }
            ),
        }
    ]
    trust = synthesize_trust(
        answer="You can cancel with no fee under the Northstar agreement.",
        tools_used=tools_used,
    )
    assert trust["confidence"] == "high"
    assert trust["agreement_override"] is True
    assert any(c["claim"] == "cancellation_fee" for c in trust["conflicts"])
    assert "Trust note" in trust["answer"]
    assert trust["facts"]["cancellation"]["fee_inr"] == 0


def test_credit_abstain_is_low_confidence() -> None:
    tools_used = [
        {
            "tool": "structured_data_query",
            "args": {"intent": "calc_service_credit"},
            "result_preview": json.dumps(
                {
                    "intent": "calc_service_credit",
                    "data": {
                        "eligible": False,
                        "amount_inr": None,
                        "abstain": True,
                        "sources": [],
                    },
                }
            ),
        }
    ]
    trust = synthesize_trust(answer="I cannot confirm a credit yet.", tools_used=tools_used)
    assert trust["confidence"] == "low"
    assert trust["abstain"] is True


def test_sla_breach_flags_escalation() -> None:
    tools_used = [
        {
            "tool": "structured_data_query",
            "args": {"intent": "calc_sla"},
            "result_preview": json.dumps(
                {
                    "intent": "calc_sla",
                    "data": {
                        "severity": "P1",
                        "target_minutes": 15,
                        "elapsed_minutes": 30,
                        "breached": True,
                        "recommend_escalation": True,
                        "agreement_override": True,
                        "policy_default_minutes": 30,
                        "sources": [],
                    },
                }
            ),
        }
    ]
    trust = synthesize_trust(
        answer="SLA is breached; escalate.",
        tools_used=tools_used,
    )
    assert trust["recommend_escalation"] is True
    assert any(c["claim"] == "sla_target" for c in trust["conflicts"])


def test_no_tools_is_low_confidence() -> None:
    trust = synthesize_trust(answer="Enterprise P1 is always 1 hour.", tools_used=[])
    assert trust["confidence"] == "low"


def test_confirmed_update_ticket_cited() -> None:
    tools_used = [
        {
            "tool": "update_ticket",
            "args": {"ticket_id": "TKT-504", "notes": "called carrier"},
            "result_preview": json.dumps(
                {
                    "hitl": "confirmed",
                    "executed": True,
                    "action_type": "update_ticket",
                    "result_ref": "TKT-504",
                    "result": {"ticket_id": "TKT-504", "changed": {"notes_appended": True}},
                }
            ),
        }
    ]
    trust = synthesize_trust(answer="Ticket TKT-504 updated.", tools_used=tools_used)
    assert trust["facts"]["last_action"]["result_ref"] == "TKT-504"
    assert any(c["type"] == "action" for c in trust["citations"])


def test_calc_intent_from_args_when_preview_unparsed() -> None:
    """Regression: missing/unparsed result_preview must not force confidence=low."""
    tools_used = [
        {
            "tool": "structured_data_query",
            "args": {"intent": "calc_cancellation", "order_id": "ORD-1001"},
            "result_preview": None,
        }
    ]
    trust = synthesize_trust(
        answer="Yes — you can cancel ORD-1001 without a fee.",
        tools_used=tools_used,
    )
    assert trust["confidence"] == "high"

