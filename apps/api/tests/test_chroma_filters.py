from app.vector.metadata_filters import build_metadata_filter


def test_exclude_deprecated_filter() -> None:
    clause = build_metadata_filter(include_deprecated=False)
    assert clause == {"status": {"$nin": ["DEPRECATED", "ARCHIVED"]}}


def test_account_filter_includes_global_docs() -> None:
    clause = build_metadata_filter(account_id="ACCT-001", include_deprecated=True)
    assert clause is not None
    assert "$or" in clause
    or_clause = clause["$or"]
    assert {"account_id": "ACCT-001"} in or_clause
    assert {"account_id": ""} in or_clause


def test_combined_filter() -> None:
    clause = build_metadata_filter(
        include_deprecated=False,
        account_id="ACCT-001",
        doc_types=["policy", "agreement"],
    )
    assert clause is not None
    assert "$and" in clause
    assert len(clause["$and"]) == 3
