from __future__ import annotations

from typing import Any

from app.embeddings.gemini import get_embedding_client
from app.vector.chroma_store import get_document_collection
from app.vector.metadata_filters import build_metadata_filter


def document_search(
    query: str,
    *,
    include_deprecated: bool = False,
    account_id: str | None = None,
    doc_types: list[str] | None = None,
    doc_id: str | None = None,
    top_k: int = 6,
) -> list[dict[str, Any]]:
    """
    Semantic search over policy PDF chunks in Chroma.
    Defaults exclude DEPRECATED/ARCHIVED (see docs/RAG_APPROACH.md).
    """
    if not query.strip():
        return []

    collection = get_document_collection()
    where = build_metadata_filter(
        include_deprecated=include_deprecated,
        account_id=account_id,
        doc_types=doc_types,
        doc_id=doc_id,
    )

    embedder = get_embedding_client()
    query_vector = embedder.embed_query(query)

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    chunks: list[dict[str, Any]] = []
    if not results["ids"] or not results["ids"][0]:
        return chunks

    for idx, chunk_id in enumerate(results["ids"][0]):
        metadata = results["metadatas"][0][idx] or {}
        distance = results["distances"][0][idx]
        # Cosine distance in Chroma: lower is more similar; convert to rough score.
        score = round(1.0 - distance, 4)
        chunks.append(
            {
                "chunk_id": chunk_id,
                "doc_id": metadata.get("doc_id"),
                "title": metadata.get("title"),
                "filename": metadata.get("filename"),
                "status": metadata.get("status"),
                "doc_type": metadata.get("doc_type"),
                "authority_rank": metadata.get("authority_rank"),
                "account_id": metadata.get("account_id") or None,
                "section_title": metadata.get("section_title"),
                "section_path": metadata.get("section_path"),
                "text": results["documents"][0][idx],
                "score": score,
            }
        )

    chunks.sort(key=lambda item: (item.get("authority_rank", 99), -item["score"]))
    return chunks
