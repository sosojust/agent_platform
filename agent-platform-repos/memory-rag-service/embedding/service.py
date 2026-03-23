"""本地 bge-m3 Embedding，懒加载单例。"""
from typing import Optional
from sentence_transformers import SentenceTransformer
from config.settings import settings
from agent_platform_shared.logging.logger import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    def __init__(self) -> None:
        self._model: Optional[SentenceTransformer] = None

    def _load(self) -> SentenceTransformer:
        if self._model is None:
            logger.info("loading_embedding_model", model=settings.embedding_model)
            self._model = SentenceTransformer(
                settings.embedding_model, device=settings.embedding_device
            )
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._load().encode(
            texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False
        ).tolist()

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]

    @property
    def dimension(self) -> int:
        return self._load().get_sentence_embedding_dimension() or 1024


embedding_service = EmbeddingService()
