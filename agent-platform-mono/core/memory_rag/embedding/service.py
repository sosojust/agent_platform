from __future__ import annotations
from typing import List
from core.ai_core.embedding.provider import EmbeddingProvider, get_embedding_provider


class EmbeddingService:
    def __init__(self):
        self._provider: EmbeddingProvider | None = None

    def embed(self, texts: List[str]) -> List[List[float]]:
        if self._provider is None:
            self._provider = get_embedding_provider()
        return self._provider.embed(texts)


embedding_service = EmbeddingService()
