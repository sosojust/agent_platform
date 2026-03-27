"""
MemoryConfig：各业务域覆盖记忆和 RAG 参数的数据类。

框架层提供默认值，业务域在 memory_config.py 中覆盖需要调整的参数。
设计原则：只暴露业务域真正需要调整的参数，底层实现细节不透出。
"""
from dataclasses import dataclass, field


@dataclass
class MemoryConfig:
    short_term_max_turns: int = 20
    long_term_enabled: bool = True
    rag_top_k_recall: int = 20
    rag_top_k_rerank: int = 5
    rag_rerank_threshold: float = 0.3
    rag_collection_type: str = "business"
    rag_query_rewrite: bool = True
    max_steps: int = 10
    memory_noise_filter_enabled: bool = True
    short_to_long_trigger_turns: int = 20
    long_term_retrieve_top_k: int = 5
    memory_types_default: list[str] = field(default_factory=lambda: ["conversation"])


DEFAULT_MEMORY_CONFIG = MemoryConfig()
