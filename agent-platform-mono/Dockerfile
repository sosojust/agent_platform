FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY . .

# 预下载 Embedding / Rerank 模型（避免启动时拉取，生产推荐）
ARG EMBEDDING_MODEL=BAAI/bge-m3
ARG RERANK_MODEL=BAAI/bge-reranker-v2-m3
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')" || true
RUN python -c "from FlagEmbedding import FlagReranker; FlagReranker('${RERANK_MODEL}')" || true

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
