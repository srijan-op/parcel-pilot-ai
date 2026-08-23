from __future__ import annotations

from functools import lru_cache

import google.generativeai as genai

from app.config import get_settings


class GeminiEmbeddingClient:
    def __init__(self, api_key: str, model: str, output_dimensionality: int = 768) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required for embeddings")
        genai.configure(api_key=api_key)
        self._model = model
        self._output_dimensionality = output_dimensionality

    def _embed(self, text: str, *, task_type: str) -> list[float]:
        result = genai.embed_content(
            model=self._model,
            content=text,
            task_type=task_type,
            output_dimensionality=self._output_dimensionality,
        )
        return list(result["embedding"])

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [self._embed(text, task_type="retrieval_document") for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text, task_type="retrieval_query")


@lru_cache
def get_embedding_client() -> GeminiEmbeddingClient:
    settings = get_settings()
    model = settings.gemini_embedding_model
    if not model.startswith("models/"):
        model = f"models/{model}"
    return GeminiEmbeddingClient(
        api_key=settings.gemini_api_key,
        model=model,
        output_dimensionality=settings.gemini_embedding_dimensions,
    )
