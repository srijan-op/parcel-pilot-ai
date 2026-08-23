from datetime import datetime
from functools import lru_cache

from app.timeutil import get_snapshot_tz


@lru_cache
def get_document_registry() -> tuple[dict, ...]:
    """Build document registry lazily (avoids timezone lookup at import time)."""
    tz = get_snapshot_tz()

    def dt(year: int, month: int, day: int) -> datetime:
        return datetime(year, month, day, tzinfo=tz)

    return (
        {
            "doc_id": "01_Support_Policy_v3_CURRENT",
            "title": "ParcelPilot Support Policy v3",
            "filename": "01_Support_Policy_v3_CURRENT.pdf",
            "status": "CURRENT",
            "doc_type": "policy",
            "authority_rank": 2,
            "account_id": None,
            "effective_from": dt(2026, 5, 1),
            "effective_to": None,
            "supersedes_doc_id": "02_Support_Policy_v2_DEPRECATED",
            "summary": "Current default support severity and SLA targets; defines source precedence.",
        },
        {
            "doc_id": "02_Support_Policy_v2_DEPRECATED",
            "title": "ParcelPilot Support Policy v2",
            "filename": "02_Support_Policy_v2_DEPRECATED.pdf",
            "status": "DEPRECATED",
            "doc_type": "policy",
            "authority_rank": 99,
            "account_id": None,
            "effective_from": dt(2025, 1, 1),
            "effective_to": dt(2026, 4, 30),
            "supersedes_doc_id": None,
            "summary": "Deprecated. DO NOT USE for current requests. Historical reference only.",
        },
        {
            "doc_id": "03_Cancellation_and_Service_Credit_SOP_v4",
            "title": "Cancellation & Service Credit SOP v4",
            "filename": "03_Cancellation_and_Service_Credit_SOP_v4.pdf",
            "status": "CURRENT",
            "doc_type": "sop",
            "authority_rank": 2,
            "account_id": None,
            "effective_from": dt(2026, 6, 15),
            "effective_to": None,
            "supersedes_doc_id": None,
            "summary": "Cancellation fees by order status; default failed-pickup credit rules.",
        },
        {
            "doc_id": "04_Product_Operations_Guide_and_Known_Issues",
            "title": "Product Operations Guide & Known Issues",
            "filename": "04_Product_Operations_Guide_and_Known_Issues.pdf",
            "status": "CURRENT",
            "doc_type": "product",
            "authority_rank": 2,
            "account_id": None,
            "effective_from": dt(2026, 8, 14),
            "effective_to": None,
            "supersedes_doc_id": None,
            "summary": "Plan capabilities, KI-208 bulk upload, KI-211 SwiftShip webhook delay.",
        },
        {
            "doc_id": "05_Northstar_Logistics_Enterprise_Agreement",
            "title": "Northstar Logistics Enterprise Agreement",
            "filename": "05_Northstar_Logistics_Enterprise_Agreement.pdf",
            "status": "ACTIVE",
            "doc_type": "agreement",
            "authority_rank": 1,
            "account_id": "ACCT-001",
            "effective_from": dt(2026, 1, 1),
            "effective_to": dt(2026, 12, 31),
            "supersedes_doc_id": None,
            "summary": "Custom SLA, cancel fee waiver for BOOKED pre-pickup, monthly credit cap.",
        },
        {
            "doc_id": "06_LumenWorks_Service_Agreement",
            "title": "LumenWorks Service Agreement",
            "filename": "06_LumenWorks_Service_Agreement.pdf",
            "status": "ACTIVE",
            "doc_type": "agreement",
            "authority_rank": 1,
            "account_id": "ACCT-002",
            "effective_from": dt(2026, 3, 1),
            "effective_to": dt(2027, 2, 28),
            "supersedes_doc_id": None,
            "summary": "Growth SLAs; failed-pickup credit >4h fixed INR 300.",
        },
    )
