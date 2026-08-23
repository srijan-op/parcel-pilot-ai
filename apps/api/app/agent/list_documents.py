from __future__ import annotations

from typing import Any

from app.auth.acl import is_customer
from app.auth.models import AuthUser
from app.ingest.document_registry import get_document_registry


def list_documents(user: AuthUser, *, include_deprecated: bool = False) -> list[dict[str, Any]]:
    """
    Document catalog for the agent (registry source of truth).
    Customers only see global docs + their own agreement.
    """
    rows: list[dict[str, Any]] = []
    for entry in get_document_registry():
        status = str(entry["status"])
        if not include_deprecated and status in ("DEPRECATED", "ARCHIVED"):
            continue
        account_id = entry.get("account_id")
        if is_customer(user):
            if account_id and account_id != user.account_id:
                continue
        rows.append(
            {
                "doc_id": entry["doc_id"],
                "title": entry["title"],
                "status": status,
                "doc_type": entry["doc_type"],
                "authority_rank": entry["authority_rank"],
                "account_id": account_id,
                "summary": entry.get("summary"),
            }
        )
    rows.sort(key=lambda r: (r["authority_rank"], r["title"]))
    return rows


def format_catalog_for_prompt(docs: list[dict[str, Any]]) -> str:
    if not docs:
        return "(no documents visible for this user)"
    lines = []
    for d in docs:
        acct = d["account_id"] or "global"
        lines.append(
            f"- [{d['status']}] rank={d['authority_rank']} type={d['doc_type']} "
            f"acct={acct} :: {d['title']} — {d.get('summary') or ''}"
        )
    return "\n".join(lines)
