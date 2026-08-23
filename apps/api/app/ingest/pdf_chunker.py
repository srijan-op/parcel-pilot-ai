from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

# Approximate token budget (words × ~1.3 ≈ tokens for English prose).
MAX_SECTION_WORDS = 600
WHOLE_DOC_WORDS = 800
SUBCHUNK_OVERLAP_WORDS = 50

SECTION_PATTERN = re.compile(r"(?=^\d+\.\s)", re.MULTILINE)


@dataclass
class TextChunk:
    section_title: str
    section_path: str
    body: str
    chunk_index: int

    @property
    def word_count(self) -> int:
        return len(self.body.split())


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    text = "\n".join(pages)
    # Normalize line endings and collapse excessive blank lines.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return parts if parts else ([text.strip()] if text.strip() else [])


def _subsplit_section(body: str, max_words: int = MAX_SECTION_WORDS) -> list[str]:
    if len(body.split()) <= max_words:
        return [body]

    paragraphs = _split_paragraphs(body)
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    for paragraph in paragraphs:
        paragraph_words = len(paragraph.split())
        if current and current_words + paragraph_words > max_words:
            chunks.append("\n\n".join(current))
            # Overlap: carry trailing paragraph(s) for context
            if current:
                overlap = "\n\n".join(current[-1:])
                current = [overlap, paragraph] if overlap else [paragraph]
                current_words = len("\n\n".join(current).split())
            else:
                current = [paragraph]
                current_words = paragraph_words
        else:
            current.append(paragraph)
            current_words += paragraph_words

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def _parse_section_title(section_text: str, fallback: str) -> str:
    first_line = section_text.strip().split("\n", 1)[0].strip()
    if re.match(r"^\d+\.\s", first_line):
        return first_line
    return fallback


def chunk_pdf_text(text: str, doc_title: str) -> list[TextChunk]:
    """Section-aware chunking per docs/RAG_APPROACH.md."""
    if not text.strip():
        return []

    total_words = len(text.split())
    sections = SECTION_PATTERN.split(text)
    sections = [s.strip() for s in sections if s.strip()]

    if len(sections) <= 1:
        if total_words <= WHOLE_DOC_WORDS:
            return [
                TextChunk(
                    section_title=doc_title,
                    section_path=doc_title,
                    body=text,
                    chunk_index=0,
                )
            ]

        # No numbered sections — paragraph-based fallback
        bodies = _subsplit_section(text)
        return [
            TextChunk(
                section_title=doc_title,
                section_path=f"{doc_title} (part {i + 1})",
                body=body,
                chunk_index=i,
            )
            for i, body in enumerate(bodies)
        ]

    chunks: list[TextChunk] = []
    chunk_index = 0
    for section in sections:
        title = _parse_section_title(section, doc_title)
        section_path = f"{doc_title} > {title}"
        for body in _subsplit_section(section):
            chunks.append(
                TextChunk(
                    section_title=title,
                    section_path=section_path,
                    body=body,
                    chunk_index=chunk_index,
                )
            )
            chunk_index += 1

    return chunks


def build_embeddable_text(
    *,
    doc_title: str,
    status: str,
    doc_type: str,
    section_path: str,
    body: str,
) -> str:
    header = (
        f"[doc: {doc_title} | status: {status} | type: {doc_type}]\n"
        f"Section: {section_path}\n\n"
    )
    return header + body.strip()
