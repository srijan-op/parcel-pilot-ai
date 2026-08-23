from __future__ import annotations

import shutil
from functools import lru_cache
from pathlib import Path

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings as ChromaSettings

from app.config import get_settings
from app.vector.metadata_filters import chroma_metadata

COLLECTION_NAME = "parcelpilot_documents"


def _resolved_chroma_path() -> Path:
    settings = get_settings()
    base = Path(__file__).resolve().parent.parent.parent
    path = Path(settings.chroma_path)
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _wipe_chroma_store() -> None:
    """Remove persisted Chroma data (e.g. after version mismatch or corruption)."""
    get_chroma_client.cache_clear()
    path = _resolved_chroma_path()
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        return

    # Windows keeps chroma.sqlite3 locked while a client is open — never hold
    # a client reference across rmtree.
    import gc
    import time

    for attempt in range(3):
        try:
            shutil.rmtree(path)
            break
        except PermissionError:
            gc.collect()
            time.sleep(0.25 * (attempt + 1))
    path.mkdir(parents=True, exist_ok=True)


def _reset_collection() -> None:
    """Full wipe for ingest — avoids reading corrupted collection metadata."""
    _wipe_chroma_store()


@lru_cache
def get_chroma_client() -> chromadb.PersistentClient:
    path = _resolved_chroma_path()
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(path),
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def get_document_collection(*, reset: bool = False) -> Collection:
    if reset:
        _reset_collection()

    client = get_chroma_client()
    try:
        return client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    except Exception:
        _wipe_chroma_store()
        client = get_chroma_client()
        return client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )


__all__ = [
    "COLLECTION_NAME",
    "chroma_metadata",
    "get_chroma_client",
    "get_document_collection",
]
