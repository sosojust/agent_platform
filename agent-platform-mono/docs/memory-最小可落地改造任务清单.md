# Memory 层最小可落地改造任务清单

## 目标
- 将 `core/memory_rag/memory` 从“仅短期记忆窗口”升级为“可检索、可治理、可演进”的统一记忆层。
- 保持上层调用稳定：编排层仍通过 `memory_gateway` 统一入口访问，不直接依赖底层实现细节。

## 范围（MVP）
- 纳入：
  - 记忆检索（短期 + 长期，支持 memory_type 过滤策略）
  - 短期转长期（阈值触发）
  - 写入治理（废话过滤、去重）
- 暂不纳入：
  - 复杂实体抽取与知识图谱
  - 复杂多模态记忆
  - 在线学习与自动策略调参

## 最小接口目标
- `append_interaction(conversation_id, tenant_id, role, content, config, memory_type="conversation")`
- `build_memory_context(conversation_id, query, tenant_id, config, memory_types=None)`
- `retrieve_long_term(query, tenant_id, config, memory_types=None, top_k=5)`
- `consolidate_short_to_long(conversation_id, tenant_id, config)`

## 任务清单

### A. 接口与配置对齐
- [x] 在 `core/memory_rag/memory/config.py` 增加最小配置项：
  - [x] `memory_noise_filter_enabled: bool`
  - [x] `short_to_long_trigger_turns: int`
  - [x] `long_term_retrieve_top_k: int`
  - [x] `memory_types_default: list[str]`
- [x] 保持原有配置兼容（不破坏 apps 现有 `MemoryConfig` 初始化）

### B. 写入治理（废话过滤 + 去重）
- [x] 在 `memory/manager.py` 增加写入前处理：
  - [x] 空白/超短噪声过滤
  - [x] 常见寒暄废话过滤（可配置）
  - [x] 连续重复内容去重（同会话窗口）
- [x] 为过滤结果增加可观测日志字段（tenant_id/conversation_id/过滤原因）

### C. 长期记忆最小实现
- [x] 在 `memory/manager.py` 增加长期写入接口（先复用现有向量存储能力）
- [x] 元数据最小字段：`tenant_id/conversation_id/memory_type/role/timestamp`
- [x] 增加长期检索接口并返回可拼接文本片段

### D. 短期转长期
- [x] 在短期追加后检查阈值，达到 `short_to_long_trigger_turns` 时触发 consolidate
- [ ] consolidate 规则（MVP）：
  - [x] 仅提取最近窗口中的有效 user/assistant 轮次
  - [x] 过滤后写入长期记忆
  - [ ] 避免重复写入（基于 hash 或近似文本比较）
  - [ ] 滚动摘要后写入长期（窗口压缩，避免原文堆积）

### E. 读取聚合（短期 + 长期）
- [x] `build_memory_context` 聚合策略：
  - [x] 先短期窗口
  - [x] 再长期检索补充（top_k）
  - [ ] 时间衰减（近期记忆优先）
  - [ ] 合并去重后输出统一 context
- [x] 支持按 `memory_types` 过滤（如 `profile/claim/plan`，属于长期记忆分类标签）
- [ ] 与 RAG 检索结果融合并控制占比（防止 context 膨胀）

### F. 编排层接入与兼容
- [x] 保持 `base_agent.py` 现有调用方式可用
- [x] 在不改动业务 workflow 的前提下接入长期检索能力
- [x] 保证 `tenant_id` 全链路透传

### G. 测试与验收
- [ ] 单元测试：
  - [x] 废话过滤与去重
  - [x] 短期阈值触发 consolidate
  - [ ] 长期检索与 memory_type 过滤
- [ ] 集成测试：
  - [x] `build_memory_context` 输出包含短期 + 长期片段
  - [ ] 多租户隔离校验
- [ ] 异步任务：
  - [ ] 定期压缩与过期清理（任务调度 + 可观测）
- [ ] 验收标准：
  - [x] 现有测试不回归
  - [x] 新增能力默认开关下可运行
  - [x] 配置关闭时行为退化为当前短期记忆模式

## 里程碑建议
- M1：接口与配置、写入治理（A+B）
- M2：长期记忆写入/检索、短期转长期（C+D）
- M3：读取聚合、测试与回归（E+F+G）

## M3 任务拆分（先规划，后实施）

### 批次与优先级
- P0（先做稳定性与质量基线）：
  - 长期写入去重
  - 读取聚合去重
  - 时间衰减排序
  - memory_type 过滤策略完善
- P1（再做融合与生命周期）：
  - 与 RAG 结果融合占比控制
  - 滚动摘要后写入长期
  - 异步压缩与过期清理
  - 多租户隔离集成验证

### T1 长期写入去重（P0）
- 目标：避免 consolidate 或重复对话导致长期记忆重复灌入。
- 范围：
  - 增加 hash 去重（精确重复）
  - 预留近似去重策略（相似度阈值可配置）
  - 去重命中写入可观测日志
- 接口改动点（计划）：
  - `MemoryConfig`：新增 `long_term_dedup_enabled`、`long_term_dedup_mode`、`long_term_dedup_similarity_threshold`
  - `MemoryManager.append_long_term`：增加去重前检查与命中原因返回
  - 长期 metadata：增加 `content_hash` 字段用于精确去重
- 配置项（计划）：
  - `long_term_dedup_enabled: bool = true`
  - `long_term_dedup_mode: str = "hash"`（预留 `"semantic"`）
  - `long_term_dedup_similarity_threshold: float = 0.92`
- 测试用例建议：
  - `test_append_long_term_dedup_by_hash`
  - `test_append_long_term_dedup_semantic_threshold`
  - `test_append_long_term_keeps_distinct_items`
- 验收命令（建议）：
  - `pytest tests/memory/test_manager.py -k dedup`
  - `mypy core/memory_rag/memory/manager.py`
- 交付物：
  - 设计：去重策略与冲突处理规则
  - 测试：重复文本、多轮相近文本、跨会话重复场景
  - 验收：重复写入率下降，命中指标可观测

### T2 读取聚合去重（P0）
- 目标：`build_memory_context` 输出中避免短期与长期片段重复。
- 范围：
  - 聚合后统一去重
  - 保留信息密度更高片段（长度/语义优先）
  - 控制输出稳定性（同输入结果波动小）
- 接口改动点（计划）：
  - `MemoryConfig`：新增 `memory_context_dedup_enabled`、`memory_context_dedup_window`
  - `MemoryManager.build_memory_context`：增加短期/长期聚合后统一去重步骤
  - 预留去重策略函数：标准化文本键与近似匹配键
- 配置项（计划）：
  - `memory_context_dedup_enabled: bool = true`
  - `memory_context_dedup_window: int = 50`
- 测试用例建议：
  - `test_build_memory_context_dedup_short_and_long`
  - `test_build_memory_context_keeps_high_density_fragment`
  - `test_build_memory_context_dedup_disabled_compatibility`
- 验收命令（建议）：
  - `pytest tests/memory/test_manager.py -k build_memory_context`
  - `mypy core/memory_rag/memory/manager.py`
- 交付物：
  - 设计：去重键与保留规则
  - 测试：短期与长期重复、近似重复、无重复基线
  - 验收：context 重复片段显著减少

### T3 时间衰减排序（P0）
- 目标：同相关度下优先近期记忆，降低陈旧记忆干扰。
- 范围：
  - 引入时间衰减函数（半衰期可配）
  - 与语义分数融合（加权或重排）
  - 支持按 memory_type 调整衰减强度
- 接口改动点（计划）：
  - `MemoryConfig`：新增 `memory_time_decay_enabled`、`memory_time_decay_half_life_hours`、`memory_time_decay_weight`
  - `MemoryManager.retrieve_long_term`：在检索结果阶段追加时间衰减打分
  - 返回调试字段：原始分数/衰减后分数（仅日志）
- 配置项（计划）：
  - `memory_time_decay_enabled: bool = true`
  - `memory_time_decay_half_life_hours: int = 72`
  - `memory_time_decay_weight: float = 0.2`
- 测试用例建议：
  - `test_retrieve_long_term_time_decay_prefers_recent`
  - `test_retrieve_long_term_time_decay_weight_zero`
  - `test_retrieve_long_term_time_decay_by_memory_type`
- 验收命令（建议）：
  - `pytest tests/memory/test_manager.py -k retrieve_long_term`
  - `mypy core/memory_rag/memory/manager.py`
- 交付物：
  - 设计：打分公式与参数默认值
  - 测试：新旧记忆竞争、同分场景排序稳定性
  - 验收：近期记忆优先符合预期且可配置

### T4 memory_type 过滤策略完善（P0）
- 目标：将 profile/claim/plan 作为长期记忆分类标签进行精确过滤。
- 范围：
  - 强化 `memory_type` 过滤入口与默认值行为
  - 校验标签白名单与非法值处理
  - 对应 Filter DSL 组合策略清晰化
- 接口改动点（计划）：
  - `MemoryConfig`：新增 `memory_types_allowed` 与 `memory_types_default`
  - `MemoryManager.retrieve_long_term`：统一 `memory_types` 归一化与非法值拦截
  - `rag/filters.py`：补充 `memory_type` 多值过滤组合策略说明
- 配置项（计划）：
  - `memory_types_allowed: list[str] = ["conversation","profile","claim","plan"]`
  - `memory_types_default: list[str] = ["conversation"]`
- 测试用例建议：
  - `test_retrieve_long_term_filter_by_memory_types`
  - `test_retrieve_long_term_rejects_unknown_memory_type`
  - `test_retrieve_long_term_uses_default_memory_types`
- 验收命令（建议）：
  - `pytest tests/memory/test_manager.py -k memory_type`
  - `mypy core/memory_rag/memory/manager.py core/memory_rag/rag/filters.py`
- 交付物：
  - 设计：分类标签约束与过滤策略
  - 测试：单类型、多类型、非法类型、默认类型
  - 验收：跨类型污染可控，过滤命中率可验证

### T5 与 RAG 结果融合占比控制（P1）
- 目标：控制 memory 与 RAG 片段预算，避免 context 膨胀。
- 范围：
  - 定义 memory_context 与 rag_context 预算比例
  - 增加超预算截断策略（优先级明确）
  - 输出附带来源与裁剪信息
- 接口改动点（计划）：
  - `MemoryConfig`：新增 `memory_context_token_budget`、`memory_rag_mix_ratio`
  - `base_agent` 聚合层：在 memory/rag 拼接前执行预算裁剪
  - 输出结构：保留 `source` 与 `truncated` 标记
- 配置项（计划）：
  - `memory_context_token_budget: int = 1200`
  - `memory_rag_mix_ratio: tuple[float,float] = (0.4, 0.6)`
- 测试用例建议：
  - `test_context_mix_respects_budget`
  - `test_context_mix_prefers_higher_priority_fragments`
  - `test_context_mix_marks_truncated_sources`
- 验收命令（建议）：
  - `pytest tests/memory -k context_mix`
  - `mypy core/agent_engine/**/*.py core/memory_rag/**/*.py`
- 交付物：
  - 设计：预算规则与冲突裁剪顺序
  - 测试：长上下文压力、预算边界、来源混合
  - 验收：总上下文长度受控且关键片段保留

### T6 滚动摘要后写入长期（P1）
- 目标：短期窗口超限后先摘要再入长期，降低原文堆积。
- 范围：
  - 定义摘要触发阈值与摘要粒度
  - 摘要条目写入长期并保留来源关系
  - 失败降级为原文片段写入
- 接口改动点（计划）：
  - `MemoryConfig`：新增 `short_to_long_summary_enabled`、`summary_trigger_turns`
  - `MemoryManager.consolidate_short_to_long`：增加摘要分支与失败降级分支
  - 长期 metadata：增加 `source_range`/`source_turns`
- 配置项（计划）：
  - `short_to_long_summary_enabled: bool = true`
  - `summary_trigger_turns: int = 30`
- 测试用例建议：
  - `test_consolidate_short_to_long_with_summary`
  - `test_consolidate_short_to_long_fallback_raw_on_summary_failure`
  - `test_consolidate_short_to_long_preserves_source_trace`
- 验收命令（建议）：
  - `pytest tests/memory/test_manager.py -k consolidate`
  - `mypy core/memory_rag/memory/manager.py`
- 交付物：
  - 设计：摘要模板与降级策略
  - 测试：阈值触发、摘要质量、失败降级
  - 验收：长期存储增速下降且信息可追溯

### T7 异步压缩与过期清理（P1）
- 目标：形成可持续的长期记忆生命周期治理能力。
- 范围：
  - 定时压缩任务（合并低价值片段）
  - 过期清理策略（TTL/保留期）
  - 任务执行日志与指标上报
- 接口改动点（计划）：
  - 新增后台任务入口（memory maintenance job）
  - `MemoryConfig`：新增 `long_term_retention_days`、`maintenance_cron`
  - `MemoryManager`：新增压缩/清理执行方法
- 配置项（计划）：
  - `long_term_retention_days: int = 180`
  - `maintenance_cron: str = "0 3 * * *"`
- 测试用例建议：
  - `test_memory_maintenance_compact_old_fragments`
  - `test_memory_maintenance_cleanup_expired`
  - `test_memory_maintenance_idempotent_retry`
- 验收命令（建议）：
  - `pytest tests/memory -k maintenance`
  - `mypy core/memory_rag/memory/manager.py`
- 交付物：
  - 设计：调度周期、清理规则、失败重试
  - 测试：任务执行成功/失败、幂等与重试
  - 验收：清理结果可观测、任务稳定运行

### T8 多租户隔离集成验证（P1）
- 目标：验证租户隔离在读写与检索全链路严格生效。
- 范围：
  - 写入隔离（collection/metadata）
  - 检索隔离（tenant_id 强制过滤）
  - 观测隔离（日志字段完整）
- 接口改动点（计划）：
  - `MemoryManager`：关键入口增加 tenant_id 非空校验
  - `vector/store` 调用点：统一 collection 命名规则校验
  - 日志字段：补齐 `tenant_id/conversation_id/memory_type`
- 配置项（计划）：
  - `strict_tenant_enforcement: bool = true`
- 测试用例建议：
  - `test_memory_multi_tenant_write_isolation`
  - `test_memory_multi_tenant_search_isolation`
  - `test_memory_multi_tenant_logs_include_tenant_id`
- 验收命令（建议）：
  - `pytest tests/memory -k tenant`
  - `mypy core/memory_rag/memory/manager.py core/memory_rag/vector/store.py`
- 交付物：
  - 设计：隔离检查点清单
  - 测试：跨租户串读/串写反例校验
  - 验收：隔离测试全部通过，无跨租户泄漏

### 建议执行顺序
- 第 1 批：T1 → T2 → T3 → T4
- 第 2 批：T5 → T6
- 第 3 批：T7 → T8
