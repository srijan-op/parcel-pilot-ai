from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Role = Literal["customer", "support_agent", "ops_admin"]


@dataclass(frozen=True)
class Persona:
    persona_id: str
    name: str
    role: Role
    account_id: str | None
    description: str


# Demo personas from ParcelPilot_Assessment_Plan.md §7.3
PERSONAS: dict[str, Persona] = {
    "northstar": Persona(
        persona_id="northstar",
        name="Northstar User",
        role="customer",
        account_id="ACCT-001",
        description="Customer — Northstar Logistics (Enterprise)",
    ),
    "lumenworks": Persona(
        persona_id="lumenworks",
        name="LumenWorks User",
        role="customer",
        account_id="ACCT-002",
        description="Customer — LumenWorks (Growth)",
    ),
    "beacon": Persona(
        persona_id="beacon",
        name="Beacon User",
        role="customer",
        account_id="ACCT-003",
        description="Customer — Beacon Retail (Standard)",
    ),
    "axis": Persona(
        persona_id="axis",
        name="Axis User",
        role="customer",
        account_id="ACCT-004",
        description="Customer — Axis Parts (Standard)",
    ),
    "maya": Persona(
        persona_id="maya",
        name="Maya",
        role="support_agent",
        account_id=None,
        description="Internal support agent — all accounts",
    ),
    "ops": Persona(
        persona_id="ops",
        name="Ops Lead",
        role="ops_admin",
        account_id=None,
        description="Ops admin — all accounts + dashboard",
    ),
}


def get_persona(persona_id: str) -> Persona | None:
    return PERSONAS.get(persona_id.strip().lower())


def list_personas() -> list[Persona]:
    return list(PERSONAS.values())
