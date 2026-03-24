"""
理赔域 Memory 策略。
特点：流程长、多步骤、需要记住历史理赔记录，长期记忆必须开启。
"""
from core.memory_rag.memory.config import MemoryConfig

CLAIM_MEMORY_CONFIG = MemoryConfig(
    short_term_max_turns=30,     # 理赔对话轮次多，材料核验需要更多上下文
    long_term_enabled=True,      # 必须记住历史理赔记录和用户习惯
    rag_top_k_recall=30,         # 理赔知识库内容密集，多召回候选
    rag_top_k_rerank=8,          # 精排后保留更多，理赔规则需要全面覆盖
    rag_rerank_threshold=0.3,    # 阈值较低，宁多勿少
    rag_query_rewrite=True,      # 理赔问题复杂，改写能提升检索效果
    max_steps=15,                # 理赔流程步骤多，允许更多步骤
)
