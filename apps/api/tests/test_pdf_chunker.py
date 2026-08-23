from pathlib import Path

import pytest

from app.ingest.pdf_chunker import (
    build_embeddable_text,
    chunk_pdf_text,
    extract_pdf_text,
)


@pytest.fixture
def support_policy_v3_text() -> str:
    path = Path(__file__).resolve().parents[3] / "data" / "01_Support_Policy_v3_CURRENT.pdf"
    return extract_pdf_text(path)


def test_extract_support_policy_v3(support_policy_v3_text: str) -> None:
    assert "Support" in support_policy_v3_text
    assert "Policy" in support_policy_v3_text
    assert "v3" in support_policy_v3_text


def test_chunk_support_policy_v3_has_multiple_sections(support_policy_v3_text: str) -> None:
    chunks = chunk_pdf_text(support_policy_v3_text, doc_title="Support Policy v3")
    assert len(chunks) >= 3
    titles = " ".join(c.section_title for c in chunks)
    assert "Scope" in titles or "Severity" in titles or "response" in titles.lower()


def test_build_embeddable_text_includes_header() -> None:
    text = build_embeddable_text(
        doc_title="Support Policy v3",
        status="CURRENT",
        doc_type="policy",
        section_path="Support Policy v3 > 3. Default first-response targets",
        body="Enterprise P1 is 30 minutes.",
    )
    assert "[doc: Support Policy v3 | status: CURRENT | type: policy]" in text
    assert "Section:" in text
    assert "30 minutes" in text


def test_section_split_on_synthetic_text() -> None:
    text = (
        "1. First section\n\nDetails about first.\n\n"
        "2. Second section\n\nMore details here.\n\n"
        "3. Third section\n\nFinal details."
    )
    chunks = chunk_pdf_text(text, doc_title="Test Doc")
    assert len(chunks) == 3


def test_deprecated_policy_chunks() -> None:
    path = Path(__file__).resolve().parents[3] / "data" / "02_Support_Policy_v2_DEPRECATED.pdf"
    text = extract_pdf_text(path)
    chunks = chunk_pdf_text(text, doc_title="Support Policy v2")
    assert len(chunks) >= 1
