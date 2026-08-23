from app.ingest.document_registry import get_document_registry


def test_document_registry_has_six_pdfs() -> None:
    assert len(get_document_registry()) == 6


def test_v2_is_deprecated() -> None:
    v2 = next(d for d in get_document_registry() if "v2" in d["doc_id"])
    assert v2["status"] == "DEPRECATED"
    assert v2["authority_rank"] == 99


def test_v3_supersedes_v2() -> None:
    v3 = next(d for d in get_document_registry() if "v3" in d["doc_id"])
    assert v3["status"] == "CURRENT"
    assert v3["supersedes_doc_id"] == "02_Support_Policy_v2_DEPRECATED"


def test_agreements_are_rank_one() -> None:
    agreements = [d for d in get_document_registry() if d["doc_type"] == "agreement"]
    assert len(agreements) == 2
    assert all(d["authority_rank"] == 1 for d in agreements)
