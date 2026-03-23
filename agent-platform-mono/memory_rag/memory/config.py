"""
MemoryConfig：各业务域覆盖记忆和 RAG 参数的数据类。

框架层提供默认值，业务域在 memory_config.py 中覆盖需要调整的参数。
设计原则：只暴露业务域真正需要调整的参数，底层实现细节不透出。
"""
from dataclasses import dataclass, field


@dataclass
class MemoryConfig:
    # ── 短期记忆 ────────────────────────────────────────────
    # 短期记忆保留的最大对话轮数，超出后触发压缩写入长期记忆
    short_term_max_turns: int = 20

    # ── 长期记忆 ────────────────────────────────────────────
    # 是否启用长期记忆（mem0 自动提取和压缩）
    long_term_enabled: bool = True

    # ── RAG 检索 ────────────────────────────────────────────
    # 向量召回候选数量（召回多，rerank 后取少）
    rag_top_k_recall: int = 20
    # rerank 后保留的最终文档数
    rag_top_k_rerank: int = 5
    # rerank 分数阈值，低于此分数的文档不送给 LLM
    rag_rerank_threshold: float = 0.3
    # 检索的向量库 collection 类型
    rag_collection_type: str = "business"
    # 是否开启查询改写（用 LLM 优化检索词，会增加一次 LLM 调用）
    rag_query_rewrite: bool = True

    # ── Agent 行为 ──────────────────────────────────────────
    # 单次 Agent 运行最大步骤数（防止无限循环）
    max_steps: int = 10


# 框架默认配置，各域未指定时使用此值
DEFAULT_MEMORY_CONFIG = MemoryConfig()
