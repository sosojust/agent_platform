# memory_rag 层能力设计说明

定位：数据智能层（与业务无关）。负责“如何存取记忆与知识、如何检索与融合”，对上游 apps 暴露稳定、可配置、可观测的检索与记忆接口。

## 设计目标
- 解耦业务差异：apps 只描述“要什么/怎么调参”，不关心底层数据结构与存储细节。
- 可插拔与可扩展：Embedding/Rerank/向量库/关键词检索/融合策略均可替换。
- 多租户隔离与安全：collection 命名隔离 + 强制 tenant_id 过滤。
- 可观测与可治理：检索链路指标可视化，支持调参与灰度。

## 能力总览
- Dense/Keyword/Hybrid 检索统一入口
- Filter DSL（与底层无关）与运行时翻译
- 二阶段排序（Rerank）与融合（RRF/Fusion）
- Memory 管理：短期/长期记忆，写入与读取转化（去噪/摘要/去重/时间衰减）
- 多租户隔离、权限与数据治理
- 参数化策略（MemoryConfig + RetrievalPlan）
- 降级与兜底（禁用 rerank、keyword-only、缓存命中）

## 模块与提供方式

### 1) Embedding 与 Rerank
- 位置：`core/memory_rag/embedding/service.py`、`core/memory_rag/rerank/service.py`
- 能力：
  - 懒加载单例，批量 encode / rerank
  - CPU/GPU/设备可配，模型可配
- 接入方式：
  - 由检索管线自动调用，apps 无需直接使用

### 2) 向量库抽象
- 位置：`core/memory_rag/vector/store.py`
- 能力：
  - add_texts(texts, metadatas, collection)
  - search(query_vector, filters, top_k, collection)
  - delete/upsert/by_ids
  - 后端：Milvus/Qdrant（由 settings.vector_db.backend 决定）
- 提供方式：
  - 对 pipeline 公开，apps 不直接调用

#### 防腐层（Anti-Corruption Layer, ACL）设计
- 统一接口（示意）：
  - `class IVectorStore:`
    - `create_collection(name: str, schema: dict) -> None`
    - `add_texts(collection: str, texts: list[str], metadatas: list[dict], ids?: list[str]) -> list[str]`
    - `search(collection: str, query_vector: list[float], top_k: int, filter_ast?: dict, with_vectors: bool = False) -> list[Hit]`
    - `delete(collection: str, ids: list[str]) -> int`
    - `upsert(collection: str, items: list[{"id": str, "text": str, "metadata": dict, "vector"?: list[float]}]) -> None`
    - `by_ids(collection: str, ids: list[str]) -> list[Record]`
    - `list_collections() -> list[str]`
- 适配器模式：
  - `MilvusStore(IVectorStore)`、`QdrantStore(IVectorStore)` 等实现
  - 通过 `settings.vector_db.backend` 选择实例
- 语义/行为约定：
  - Idempotency：`add_texts` 允许传入外部 ID；若 ID 重复，改为 `upsert`
  - Batch：API 默认批量，内部按后端限制切批；失败按批粒度重试
  - Consistency：不保证强一致，返回值应包含版本/向量维度等元数据
  - Metadata schema：字段白名单与类型在 ACL 层校验（拒绝不合规字段）
  - Collection 命名：`{tenant}_{domain}_{type}` 强制规范与校验
- 迁移/扩展：
  - 新后端仅需实现 IVectorStore 与 Filter 翻译器
  - 测试基线：统一的 CRUD 与 search 行为测试套件（不同后端复用）

### 3) Memory 管理
- 位置：`core/memory_rag/memory/manager.py`（建议）
- 能力：
  - 短期记忆：Redis/TTL
  - 长期记忆：持久化 + 向量化
  - 写入转化（Write-time）：
    - 清洗/规范化/可选 PII 脱敏
    - 结构化为 MemoryEntry（role/intent/entities/时间戳/重要度）
    - 会话滚动摘要（阈值/窗口触发）
    - 去重与引用链
    - 分流：短期 vs 长期
  - 读取转化（Read-time）：
    - 会话上下文拼接（短期 + 长期摘录）
    - 时间衰减与去重
    - 与检索结果融合（权重/规则）
- 提供方式（示例接口）：
  - append_short_term(conversation_id, role, content, tenant_id, tags?)
  - append_long_term(entries, tenant_id)
  - get_context(conversation_id, window, tenant_id) → 上下文片段
  - consolidate/summarize/compact（后台任务）

### 4) Filter DSL
- 目标：上层声明过滤意图，底层负责翻译为向量库查询。
- 支持：
  - 基本操作：`=`, `!=`, `IN`, `PREFIX`, `EXISTS`
  - 范围：`RANGE(field, min, max)`、`TIME_RANGE(field, from, to)`
  - 组合：`AND([...])`, `OR([...])`, `NOT(expr)`
  - 强制注入：`tenant_id`、`collection`（`{tenant}_{domain}_{type}`）
- 提供方式：
  - `core/memory_rag/rag/filters.py`（建议）：定义表达式与翻译器
  - pipeline 接收 Filter DSL，并在底层翻译

#### Filter DSL 规范（提案）
- 基本类型：
  - 字面量：`string | number | boolean | null | datetime`
  - 字段名：`field`（只允许白名单内字段，如 `policyId`、`claimStatus`、`createdAt` 等）
- 原子表达式：
  - `EQ(field, value)`、`NEQ(field, value)`、`IN(field, [values...])`
  - `RANGE(field, min?, max?, include_min=true, include_max=true)`
  - `TIME_RANGE(field, from?, to?)`（from/to 为 ISO8601）
  - `EXISTS(field)`、`PREFIX(field, prefix)`、`MATCH(field, text)`（keyword）
- 组合：
  - `AND([expr...])`、`OR([expr...])`、`NOT(expr)`
- 约束与安全：
  - 强制注入：`EQ("tenant_id", <tenant>)`
  - 字段白名单与值校验在翻译前完成（避免注入与后端差异）
- JSON 例子：
```json
{
  "AND": [
    { "EQ": ["tenant_id", "t_acme"] },
    { "IN": ["claimStatus", ["APPROVED", "PENDING"]] },
    { "TIME_RANGE": ["updatedAt", "2025-01-01T00:00:00Z", null] }
  ]
}
```

#### 运行时翻译与执行规则
- 翻译器接口：
  - `translate(filter_ast) -> BackendQuery`（不同后端返回不同查询对象/结构）
- 翻译策略：
  - 尽可能使用后端原生过滤；不支持的操作降级为客户端过滤（仅在结果集较小且可控时）
  - 时间字段统一转为 UTC 存储与查询
  - 字段命名统一使用 `snake_case` 或 `camelCase`，由翻译器做映射
- 失败/降级：
  - 当后端不支持某操作：记录告警 → 降级策略（例如仅基于索引字段过滤）
  - 观测：记录“不可翻译比例”、“降级次数”，便于治理

### 5) RetrievalPlan（检索管线策略）
- 目标：解决“不同业务场景检索/过滤不同”的需求，apps 用策略描述，memory_rag 负责执行。
- 结构（示例）：
  - query_rewrite: bool|策略名
  - split_strategy: 句子/段落/滑窗
  - recall:
    - dense_top_k
    - keyword_top_k
    - hybrid: true|false, fusion: rrf|mmr|weights
  - rerank_top_k
  - time_decay: 半衰期、近因权重
  - dedup_window: 近似去重窗口
  - filters: Filter DSL 模板/动态生成器
- 提供方式：
  - apps 在 `apps/*/memory_config.py` 给出默认 Plan（或通过 Nacos 下发）
  - pipeline 接受 `RetrievalPlan` 并按阶段执行

### 6) RAG Pipeline（统一检索入口）
- 位置：`core/memory_rag/rag/pipeline.py`（建议）
- 能力：
  - `retrieve(query, tenant_id, config: MemoryConfig, plan: RetrievalPlan | None, filters: Filter | None)`
  - 链路：`pre_rewrite -> recall(dense/keyword/hybrid) -> fusion -> rerank -> postprocess`
  - 输出：上下文片段（含来源、分数、去重标签）与阶段指标（便于观测）
- 提供方式：
  - 对上游暴露唯一入口；apps 不直接依赖底层实现

## 多租户与安全
- collection：`{tenant}_{domain}_{type}`
- 强制注入 tenant_id 与权限校验
- 数据隔离：读写路径必须携带 tenant_id
- 观测日志中自动带 tenant_id/trace_id

## 可观测与调参
- 指标：
  - 阶段耗时：rewrite/recall/rerank/total
  - 召回/精排命中数与命中率
  - 融合后 nDCG/重排提升率（离线评估）
- 调参：
  - MemoryConfig/RetrievalPlan 支持 Nacos 下发与热更新
  - 降级策略：禁用 rerank、改为 keyword-only、cache 命中

## 与 apps 的边界
- apps 负责：
  - 在 `apps/*/memory_config.py` 定义默认 MemoryConfig 与 RetrievalPlan（可按 agent 场景细分）
  - 在 workflow 中调用 pipeline.retrieve，组合 memory 上下文与 RAG 结果
  - 仅声明 filter 模板/boost 规则，不写底层数据代码
- memory_rag 负责：
  - 执行所有与数据有关的细节：embedding、向量检索、关键词检索、融合、重排、转化、隔离与观测

## 典型场景示例（策略层面）
- 保单查询（policy）
  - Filter：policyId 精确匹配优先，companyId 次级；时间衰减弱
  - Hybrid：keyword 强（结构化字段），dense 兜底；rerank on
- 理赔（claim）
  - Filter：claimStatus/claimType 必选；近因权重强
  - Rerank：偏向“最新进展/结论”片段
- 客服（customer）
  - Filter：FAQ 标签优先；长期记忆（偏好）合并；必要时禁用 rerank 保证时延

## 配置与治理
- 配置入口：`shared/config/settings.py`（模型/后端/阈值等）
- 策略与开关：Nacos（灰度/热更新）
- 后台任务：记忆压缩/合并/清理

---

后续迭代建议：
1. 落地 Filter DSL 与 RetrievalPlan 的数据结构与最小可用实现
2. 完成 rag/pipeline 骨架与阶段指标上报
3. 在 apps/policy 与 apps/claim 各提供一份默认计划与过滤模板示例
