"""
客服域 Memory 策略。
特点：FAQ 优先，记录用户偏好和历史问题，中等记忆需求。
"""
from memory_rag.memory.config import MemoryConfig

CUSTOMER_MEMORY_CONFIG = MemoryConfig(
    short_term_max_turns=20,
    long_term_enabled=True,      # 记住用户偏好、常问问题
    rag_top_k_recall=15,
    rag_top_k_rerank=5,
    rag_rerank_threshold=0.35,
    rag_query_rewrite=True,      # 客服问题口语化，改写有帮助
    max_steps=10,
)
