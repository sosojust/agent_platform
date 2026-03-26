from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List
from sentence_transformers import SentenceTransformer
from shared.config.settings import settings


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        ...


class SentenceTransformerProvider(EmbeddingProvider):
    def __init__(self, model_name: str, device: str):
        self._model = SentenceTransformer(model_name, device=device)

    def embed(self, texts: List[str]) -> List[List[float]]:
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return vectors.tolist()


_embedding_provider: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    global _embedding_provider
    if _embedding_provider is None:
        _embedding_provider = SentenceTransformerProvider(
            settings.embedding.embedding_model,
            settings.embedding.device,
        )
    return _embedding_provider
