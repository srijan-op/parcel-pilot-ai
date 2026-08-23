from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.embeddings.gemini import get_embedding_client
from app.ingest.document_registry import get_document_registry
from app.ingest.pdf_chunker import (
    build_embeddable_text,
    chunk_pdf_text,
    extract_pdf_text,
)
from app.vector.chroma_store import chroma_metadata, get_document_collection


def _registry_by_filename() -> dict[str, dict]:
    return {entry["filename"]: entry for entry in get_document_registry()}


def ingest_pdfs_to_chroma(settings: Settings, *, reset: bool = True) -> dict[str, int | str]:
    registry = _registry_by_filename()
    data_path = settings.resolved_data_path
    collection = get_document_collection(reset=reset)
    embedder = get_embedding_client()

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []

    pdf_files = sorted(data_path.glob("*.pdf"))
    if not pdf_files:
        raise FileNotFoundError(f"No PDF files found in {data_path}")

    for pdf_path in pdf_files:
        meta = registry.get(pdf_path.name)
        if not meta:
            raise KeyError(f"No document registry entry for {pdf_path.name}")

        raw_text = extract_pdf_text(pdf_path)
        chunks = chunk_pdf_text(raw_text, doc_title=meta["title"])

        for chunk in chunks:
            chunk_id = f"{meta['doc_id']}::chunk_{chunk.chunk_index}"
            embed_text = build_embeddable_text(
                doc_title=meta["title"],
                status=meta["status"],
                doc_type=meta["doc_type"],
                section_path=chunk.section_path,
                body=chunk.body,
            )
            chunk_meta = chroma_metadata(
                {
                    **meta,
                    "section_title": chunk.section_title,
                    "section_path": chunk.section_path,
                    "chunk_index": chunk.chunk_index,
                }
            )
            ids.append(chunk_id)
            documents.append(embed_text)
            metadatas.append(chunk_meta)

    vectors = embedder.embed_documents(documents)
    collection.add(
        ids=ids,
        documents=documents,
        embeddings=vectors,
        metadatas=metadatas,
    )

    return {
        "pdfs_indexed": len(pdf_files),
        "chunks_indexed": len(ids),
        "collection": collection.name,
        "chroma_path": str(settings.chroma_path),
    }
