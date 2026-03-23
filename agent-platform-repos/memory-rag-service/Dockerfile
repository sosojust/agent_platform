FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*
COPY ../shared-lib /shared-lib
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .
COPY . .
ARG EMBEDDING_MODEL=BAAI/bge-m3
ARG RERANK_MODEL=BAAI/bge-reranker-v2-m3
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')" || true
RUN python -c "from FlagEmbedding import FlagReranker; FlagReranker('${RERANK_MODEL}')" || true
EXPOSE 8003
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003", "--workers", "2"]
