"""
保单域 Memory 策略。
特点：查询为主，短平快，单次对话轮次少，无需长期记忆。
"""
from memory_rag.memory.config import MemoryConfig

POLICY_MEMORY_CONFIG = MemoryConfig(
    short_term_max_turns=10,     # 保单查询对话短，10 轮足够
    long_term_enabled=False,     # 查询类场景不需要跨 session 记忆
    rag_top_k_recall=10,         # 保单知识库结构清晰，少量召回即可
    rag_top_k_rerank=3,
    rag_rerank_threshold=0.5,    # 阈值较高，只保留强相关结果
    rag_query_rewrite=False,     # 保单号/日期类查询无需改写
    max_steps=8,
)
