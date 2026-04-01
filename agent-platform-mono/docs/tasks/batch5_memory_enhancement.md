# Batch 5 — Memory 增强（M3）开发任务

## 概述

Memory 增强包含长期记忆语义去重、时间衰减排序、Context 融合权重治理，是 Memory 层的高级特性。

**前置依赖**: Batch 1 完成（分层检索体系）

---

## Task 5.1 — 长期记忆语义去重

**优先级**: P1  
**预计工时**: 3 天  
**依赖**: Batch 1 完成  
**被依赖**: 无

### 目标

在写入长期记忆时，通过向量相似度检测重复内容，避免冗余存储。

### 实现清单

#### 1. `MemoryConfig` 扩展

```python
# core/memory_rag/memory/config.py
@dataclass
class MemoryConfig:
    # 已有字段...
    
    # 长期记忆去重配置
    long_term_dedup_mode: Literal["hash", "semantic"] = "semantic"
    long_term_dedup_threshold: float = 0.85  # 相似度阈值
    long_term_dedup_action: Literal["skip", "update"] = "skip"  # skip: 跳过写入, update: 覆盖旧记录
```

#### 2. `MemoryGateway._consolidate` 更新

```python
# core/memory_rag/memory/gateway.py
class MemoryGateway:
    async def _consolidate(
        self,
        *,
        conversation_id: str,
        tenant_id: str,
        user_id: str,
        config: MemoryConfig,
    ) -> None:
        """
        1. 读取短期记忆
        2. LLM 压缩摘要
        3. 语义去重检测
        4. 写入长期向量库（USER_MEMORY）
        5. 清理 Redis 旧数据
        """
        # 读取短期记忆
        short_term = await self.get_short_term(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            user_id=user_id,
            config=config,
        )
        
        if not short_term:
            return
        
        # LLM 压缩摘要
        summary = await self._compress_memory(short_term, config)
        
        # 语义去重检测
        if config.long_term_dedup_mode == "semantic":
            is_duplicate, duplicate_id = await self._check_semantic_duplicate(
                summary,
                tenant_id=tenant_id,
                user_id=user_id,
                threshold=config.long_term_dedup_threshold,
            )
            
            if is_duplicate:
                if config.long_term_dedup_action == "skip":
                    logger.info(f"Skip duplicate memory: {summary[:50]}")
                    return
                elif config.long_term_dedup_action == "update":
                    # 删除旧记录
                    await self.ingest_gateway.delete(
                        data_type=DataType.USER_MEMORY,
                        source_id=duplicate_id,
                        tenant_id=tenant_id,
                        user_id=user_id,
                    )
        
        # 写入长期向量库
        source_id = f"memory_{conversation_id}_{int(time.time())}"
        await self.ingest_gateway.ingest(
            IngestRequest(
                content=summary,
                data_type=DataType.USER_MEMORY,
                tenant_id=tenant_id,
                user_id=user_id,
                source_id=source_id,
                source_name=f"Conversation {conversation_id}",
                language=get_current_locale(),
                importance=1.0,
            )
        )
        
        # 清理 Redis 旧数据
        await self._clear_short_term(conversation_id, tenant_id, user_id)
    
    async def _check_semantic_duplicate(
        self,
        text: str,
        *,
        tenant_id: str,
        user_id: str,
        threshold: float,
    ) -> tuple[bool, str]:
        """
        检查语义重复
        返回：(是否重复, 重复记录的 source_id)
        """
        # 生成 embedding
        embedding = await self.embedding_gateway.embed(text)
        
        # 检索相似记录
        collection = collection_name(
            DataScope.USER,
            DataType.USER_MEMORY,
            f"{tenant_id}__{user_id}",
        )
        
        results = self.vector_adapter.search(
            collection=collection,
            query_vector=embedding,
            top_k=1,
            score_threshold=threshold,
        )
        
        if results:
            return True, results[0]["metadata"]["source_id"]
        return False, ""
```

#### 3. 指标埋点

```python
# core/memory_rag/memory/metrics.py
memory_dedup_semantic_hits_total = Counter(
    "memory_dedup_semantic_hits_total",
    "Total semantic dedup hits",
    ["action"],  # skip / update
)
```

在 `_check_semantic_duplicate` 中埋点：

```python
if results:
    memory_dedup_semantic_hits_total.labels(
        action=config.long_term_dedup_action
    ).inc()
    return True, results[0]["metadata"]["source_id"]
```

### 验收标准

- [ ] `long_term_dedup_mode="hash"` 时按内容 hash 去重
- [ ] `long_term_dedup_mode="semantic"` 时按向量相似度去重
- [ ] `long_term_dedup_threshold=0.9` 时高相似度才去重
- [ ] `long_term_dedup_action="skip"` 时跳过写入
- [ ] `long_term_dedup_action="update"` 时覆盖旧记录
- [ ] 指标正确记录去重次数

---

## Task 5.2 — 时间衰减排序

**优先级**: P1  
**预计工时**: 3 天  
**依赖**: Batch 1 完成  
**被依赖**: 无

### 目标

检索结果按时间衰减打分，支持按 `data_type` 设置不同衰减强度。

### 实现清单

#### 1. `MemoryConfig` 扩展

```python
# core/memory_rag/memory/config.py
@dataclass
class MemoryConfig:
    # 已有字段...
    
    # 时间衰减配置
    time_decay_enabled: bool = True
    time_decay_half_life_hours: int = 168  # 7 天半衰期
    time_decay_weight: float = 0.3  # 时间衰减权重（0-1）
    time_decay_by_data_type: dict[str, float] = field(default_factory=lambda: {
        "USER_MEMORY": 0.5,        # 用户记忆衰减快
        "USER_PREFERENCE": 0.1,    # 用户偏好衰减慢
        "TENANT_KNOWLEDGE": 0.0,   # 企业知识不衰减
    })
```

#### 2. `LayeredRetrievalGateway` 更新

```python
# core/memory_rag/retrieval/gateway.py
class LayeredRetrievalGateway:
    async def retrieve(
        self,
        query: str,
        user_id: str,
        tenant_id: str,
        channel_id: str,
        plan: RetrievalPlan,
        memory_config: MemoryConfig | None = None,
    ) -> RetrievalResult:
        """
        检索流程：
        1. 四层并发检索
        2. 各层内部：recall → importance 加权 → 时间衰减 → rerank
        3. budget 分配截取
        4. 组装输出
        """
        # ... 已有逻辑
        
        # 时间衰减打分
        if memory_config and memory_config.time_decay_enabled:
            chunks = self._apply_time_decay(chunks, memory_config)
        
        # ... 其他逻辑
    
    def _apply_time_decay(
        self,
        chunks: list[RetrievedChunk],
        config: MemoryConfig,
    ) -> list[RetrievedChunk]:
        """
        应用时间衰减
        score_final = score_original * (1 - decay_weight) + score_time * decay_weight
        score_time = 0.5 ^ (age_hours / half_life_hours)
        """
        now = int(time.time())
        
        for chunk in chunks:
            # 获取创建时间
            created_at = chunk.metadata.get("created_at", now)
            age_hours = (now - created_at) / 3600
            
            # 获取该 data_type 的衰减权重
            data_type = chunk.data_type
            decay_weight = config.time_decay_by_data_type.get(
                data_type,
                config.time_decay_weight,
            )
            
            # 计算时间衰减分数
            half_life = config.time_decay_half_life_hours
            time_score = 0.5 ** (age_hours / half_life)
            
            # 融合分数
            original_score = chunk.score
            chunk.score = (
                original_score * (1 - decay_weight) +
                time_score * decay_weight
            )
        
        # 重新排序
        chunks.sort(key=lambda c: c.score, reverse=True)
        return chunks
```

#### 3. `ChunkMetadata` 确保包含 `created_at`

```python
# core/memory_rag/types.py
@dataclass
class ChunkMetadata:
    # ... 已有字段
    created_at: int  # UTC timestamp
    # ...
```

#### 4. 指标埋点

```python
# core/memory_rag/retrieval/metrics.py
retrieval_time_decay_applied_total = Counter(
    "retrieval_time_decay_applied_total",
    "Total time decay applications",
    ["scope"],
)
```

### 验收标准

- [ ] `time_decay_enabled=False` 时不应用时间衰减
- [ ] `time_decay_half_life_hours=168` 时 7 天前的记录分数减半
- [ ] `time_decay_by_data_type` 正确应用不同衰减权重
- [ ] `TENANT_KNOWLEDGE` 的 `decay_weight=0.0` 时分数不变
- [ ] 时间衰减后排序正确
- [ ] 指标正确记录应用次数

---

## Task 5.3 — Context 融合权重治理

**优先级**: P2  
**预计工时**: 2 天  
**依赖**: Batch 1 完成  
**被依赖**: 无

### 目标

支持按 `tenant_type` 动态调整 `budget_weights`，优化不同租户类型的检索策略。

### 实现清单

#### 1. `RetrievalPlan` 扩展

```python
# core/memory_rag/retrieval/gateway.py
@dataclass
class RetrievalPlan:
    platform: ScopedRetrievalConfig
    channel: ScopedRetrievalConfig
    tenant: ScopedRetrievalConfig
    user: ScopedRetrievalConfig
    budget_weights: dict[str, float] = field(default_factory=lambda: {
        "platform": 0.10,
        "channel": 0.20,
        "tenant": 0.35,
        "user": 0.25,
    })
    budget_weights_by_tenant_type: dict[str, dict[str, float]] = field(default_factory=lambda: {
        "individual": {
            "platform": 0.15,
            "channel": 0.15,
            "tenant": 0.20,
            "user": 0.40,  # 个人用户提高 user 层权重
        },
        "enterprise": {
            "platform": 0.10,
            "channel": 0.15,
            "tenant": 0.50,  # 企业用户提高 tenant 层权重
            "user": 0.15,
        },
        "broker": {
            "platform": 0.10,
            "channel": 0.40,  # 经纪人提高 channel 层权重
            "tenant": 0.30,
            "user": 0.10,
        },
    })
    max_total_tokens: int = 2000
```

#### 2. `LayeredRetrievalGateway` 动态权重

```python
class LayeredRetrievalGateway:
    async def retrieve(
        self,
        query: str,
        user_id: str,
        tenant_id: str,
        channel_id: str,
        plan: RetrievalPlan,
        tenant_type: str = "",
    ) -> RetrievalResult:
        """
        根据 tenant_type 动态调整 budget_weights
        """
        # 获取权重
        if tenant_type and tenant_type in plan.budget_weights_by_tenant_type:
            weights = plan.budget_weights_by_tenant_type[tenant_type]
        else:
            weights = plan.budget_weights
        
        # ... 使用 weights 进行 budget 分配
```

#### 3. `agents.py` 透传 `tenant_type`

```python
# core/agent_engine/agents.py
async def run_agent(request: AgentRunRequest) -> AgentRunResponse:
    # ... 已有逻辑
    
    # 检索时透传 tenant_type
    retrieval_result = await retrieval_gateway.retrieve(
        query=query,
        user_id=state["user_id"],
        tenant_id=state["tenant_id"],
        channel_id=state["channel_id"],
        plan=retrieval_plan,
        tenant_type=state.get("tenant_type", ""),
    )
```

#### 4. 配置化权重

创建 `core/memory_rag/retrieval/config.yaml`：

```yaml
budget_weights_by_tenant_type:
  individual:
    platform: 0.15
    channel: 0.15
    tenant: 0.20
    user: 0.40
  enterprise:
    platform: 0.10
    channel: 0.15
    tenant: 0.50
    user: 0.15
  broker:
    platform: 0.10
    channel: 0.40
    tenant: 0.30
    user: 0.10
```

加载逻辑：

```python
# core/memory_rag/retrieval/gateway.py
def load_retrieval_plan_from_config(config_path: str) -> RetrievalPlan:
    """从配置文件加载 RetrievalPlan"""
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    return RetrievalPlan(
        budget_weights_by_tenant_type=config["budget_weights_by_tenant_type"],
        # ... 其他字段
    )
```

### 验收标准

- [ ] `tenant_type="individual"` 时 user 层权重为 0.40
- [ ] `tenant_type="enterprise"` 时 tenant 层权重为 0.50
- [ ] `tenant_type="broker"` 时 channel 层权重为 0.40
- [ ] `tenant_type` 为空时使用默认权重
- [ ] 配置文件加载正确
- [ ] 权重总和为 1.0（校验逻辑）

---

## 架构防腐门禁

每个 Task 完成时检查：

- [ ] Memory 增强特性不影响基础功能
- [ ] 配置项向后兼容（默认值保持原有行为）
- [ ] 性能影响可控（P95 延迟增加 < 10%）

---

## Batch 5 完成标志

- [ ] 所有 Task 验收标准通过
- [ ] 集成测试：语义去重 + 时间衰减 + 动态权重
- [ ] 性能测试：增强特性开启后 P95 < 600ms
- [ ] 文档：Memory 增强特性配置指南
