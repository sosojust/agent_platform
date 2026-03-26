from __future__ import annotations
from typing import List
try:
    from FlagEmbedding import FlagReranker
except Exception:
    FlagReranker = None  # type: ignore
from shared.config.settings import settings


class RerankService:
    def __init__(self, model_name: str):
        self._model = FlagReranker(model_name) if FlagReranker else None

    def rerank(self, query: str, docs: List[str], top_k: int) -> List[str]:
        if self._model is None:
            return docs[:top_k]
        scores: List[float] = []
        for d in docs:
            s = self._model.compute_score([query], [d])
            if isinstance(s, list) and s:
                scores.append(float(s[0]))
            else:
                scores.append(float(s))
        idx = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [docs[i] for i in idx]


rerank_service = RerankService(settings.embedding.rerank_model)
