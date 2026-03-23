"""本地 bge-reranker 精排，懒加载单例。"""
from typing import Optional
from FlagEmbedding import FlagReranker
from config.settings import settings
from agent_platform_shared.logging.logger import get_logger

logger = get_logger(__name__)


class RerankService:
    def __init__(self) -> None:
        self._reranker: Optional[FlagReranker] = None

    def _load(self) -> FlagReranker:
        if self._reranker is None:
            logger.info("loading_rerank_model", model=settings.rerank_model)
            self._reranker = FlagReranker(settings.rerank_model, use_fp16=True)
        return self._reranker

    def rerank(
        self, query: str, documents: list[str], top_k: int = 5
    ) -> list[tuple[int, float, str]]:
        if not documents:
            return []
        scores = self._load().compute_score([[query, d] for d in documents], normalize=True)
        ranked = sorted(enumerate(zip(scores, documents)), key=lambda x: x[1][0], reverse=True)
        return [(i, s, d) for i, (s, d) in ranked[:top_k]]


rerank_service = RerankService()
