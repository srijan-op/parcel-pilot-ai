from __future__ import annotations

from typing import Any


def chroma_metadata(doc_meta: dict[str, Any]) -> dict[str, str | int | float | bool]:
    """Chroma metadata must be scalar; use empty string for null account_id."""
    account_id = doc_meta.get("account_id")
    return {
        "doc_id": str(doc_meta["doc_id"]),
        "filename": str(doc_meta["filename"]),
        "title": str(doc_meta["title"]),
        "status": str(doc_meta["status"]),
        "doc_type": str(doc_meta["doc_type"]),
        "authority_rank": int(doc_meta["authority_rank"]),
        "account_id": str(account_id) if account_id else "",
        "section_title": str(doc_meta.get("section_title", "")),
        "section_path": str(doc_meta.get("section_path", "")),
        "chunk_index": int(doc_meta.get("chunk_index", 0)),
    }


def build_metadata_filter(
    *,
    include_deprecated: bool = False,
    account_id: str | None = None,
    doc_types: list[str] | None = None,
    doc_id: str | None = None,
) -> dict[str, Any] | None:
    """Build Chroma where clause for document_search."""
    clauses: list[dict[str, Any]] = []

    if not include_deprecated:
        clauses.append({"status": {"$nin": ["DEPRECATED", "ARCHIVED"]}})

    if doc_id:
        clauses.append({"doc_id": doc_id})

    if doc_types:
        if len(doc_types) == 1:
            clauses.append({"doc_type": doc_types[0]})
        else:
            clauses.append({"doc_type": {"$in": doc_types}})

    if account_id:
        clauses.append(
            {
                "$or": [
                    {"account_id": account_id},
                    {"account_id": ""},
                ]
            }
        )

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}
