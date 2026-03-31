# ai_core LangChain SDK 统一迁移 LiteLLM 任务清单

## 目标
- 将项目内所有 LLM 调用路径统一收敛到 `ai_core/llm`，禁止业务层直连 LangChain 供应商 SDK。
- 建立“双层路由”架构：业务语义路由由 `ai_core/routing` 决策，高可用路由由 LiteLLM Router 负责。
- 在迁移过程中同步落地费控、可观测、降级与回滚能力，确保稳定与成本可控。

## 范围
- 纳入：
  - `apps/`、`agent_engine/`、`memory_rag/` 中所有 LangChain LLM 直接调用点迁移
  - `ai_core/llm` 统一接口与 LiteLLM Provider 完整能力收口
  - 路由、配置、观测、测试与灰度发布配套改造
- 不纳入：
  - 新增业务功能
  - 非 LLM 相关第三方 SDK 替换

## 迁移原则
- 上层只通过稳定入口调用：`llm_gateway.complete/stream/get_chat` 与 `routing.select_model`。
- 统一显式透传上下文：`tenant_id/conversation_id/thread_id/trace_id`。
- 不向上暴露 LiteLLM 内部实现细节（负载算法、并发参数、重试参数、fallback 链细节）。
- 所有模型名、路由策略、超时与鉴权配置全部收敛到 `settings`/Nacos。

## 任务清单

### A. 盘点与边界冻结
- [x] 扫描仓库中 `ChatOpenAI/ChatAnthropic/BaseChatModel/ainvoke/bind_tools` 等调用点并形成清单
- [x] 为每个调用点标注：业务域、场景(scene)、当前模型、风险等级、迁移优先级
- [x] 增加约束：`apps/workflows` 禁止直接 import 供应商 SDK，仅允许通过 ai_core 网关调用

当前调用点清单（已迁移到 `llm_gateway`）：

| 文件 | 业务域 | 场景(scene) | 旧调用 | 风险等级 | 优先级 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| `core/agent_engine/workflows/base_agent.py` | 基础编排 | `sensitive_reason`（可覆盖） | `ChatOpenAI + task_type` | 高 | P0 | 已迁移 |
| `domain_agents/claim/claim_agent.py` | claim | `claim_reason` | base_agent 默认路由 | 高 | P0 | 已迁移 |
| `domain_agents/policy/register.py` | policy | `policy_query` | base_agent 默认路由 | 中 | P0 | 已迁移 |
| `domain_agents/customer/register.py` | customer | `customer_faq` | base_agent 默认路由 | 中 | P0 | 已迁移 |
| `core/agent_engine/workflows/plan_execute.py` | orchestrator | `plan_execute_step` / `plan_execute_summary` | `task_type=complex/simple` | 中 | P1 | 已迁移 |
| `core/agent_engine/tools/router.py` | tool_select | `tool_select` | `task_type=complex` | 中 | P1 | 已迁移 |
| `core/memory_rag/memory/compressor.py` | memory_summary | `memory_summary`（兼容 `task_type`） | `task_type=simple` | 低 | P2 | 已迁移 |
| `core/memory_rag/rag/pipeline.py` | rag | `policy_rag_rewrite` / `claim_rag_rewrite` / `customer_intent` | 原无重写 | 中 | P1 | 已迁移 |

### B. ai_core LLM 统一接口落地
- [x] 固化 `LLMClient` 对外接口：`complete/stream/get_chat/get_tenant_usage/reset_tenant_budget`
- [x] 统一 `LLMResult` 字段：`text/usage/finish_reason/model/cached`
- [x] 在接口层统一参数透传：`tenant_id/conversation_id/thread_id/trace_id/metadata`
- [x] 统一错误码与异常语义，保持上层调用签名稳定

### C. LiteLLM Provider 与兼容层替换
- [x] 实现/完善 `LiteLLMProvider`：超时、重试、fallback、tool calling、usage 归一化
- [x] 将 `get_chat()` 返回对象切换为基于 LiteLLM 的实现，避免直连供应商 SDK
- [x] 保持现有 workflow 调用方式兼容（最小化业务改动）
- [x] 增加 `stream -> complete` 的降级策略与可观测日志

### D. 双层 Router 改造
- [x] 实现业务路由：`select_model(scene, force_local=False) -> ModelSpec(model, task_type)`
- [x] 路由维度升级为“能力等级 + 数据敏感约束”，不再只依赖固定 `task_type`
- [x] 补齐场景映射：`policy_query/claim_reason/customer_faq/*_rag_rewrite/tool_select/sensitive_reason`
- [x] LiteLLM Router 只负责同 `model_name` 下的高可用调度（多 key、限流、重试、fallback）

### E. 配置治理与费控
- [x] 扩展配置项：`LLM_MEDIUM_MODEL/LLM_NANO_MODEL/LLM_LOCAL_MODEL` 及相关端点配置
- [x] 建立两级费控：tenant 级查询对外、conversation 级保护对内
- [x] 统一缓存策略：按 `scene/task_type` 自动决策，移除上游 cache 显式开关
- [x] 将路由与模型配置接入 Nacos，支持灰度与热更新

### F. 业务域迁移实施
- [x] policy 域迁移：从 `task_type` 固定值改为显式 `scene`
- [x] claim 域迁移：复杂推理、材料核验、改写子场景分开路由
- [x] customer 域迁移：FAQ 与意图识别分级路由
- [x] RAG query rewrite 与 tool_select 内部调用迁移为轻量模型场景

### G. 可观测与质量门禁
- [x] 统一日志字段：`tenant_id/conversation_id/thread_id/trace_id/model/tokens/latency/fallback`
- [ ] 接入 Langfuse 归因与成本追踪，确保按租户/会话可回溯
- [x] 补齐单测/集成测试：路由选择、费控拦截、fallback、生效模型、usage 统计
- [ ] 执行并通过项目质量门禁（lint/typecheck/test）

### H. 灰度发布与回滚
- [ ] 按业务域分批灰度：policy -> customer -> claim
- [ ] 监控核心指标：错误率、P95 延迟、单会话成本、fallback 触发率
- [ ] 准备一键回滚策略：异常时回退到迁移前调用路径
- [ ] 完成灰度复盘并固化发布准入标准

## 验收标准（DoD）
- 仓库内无业务层直连 LangChain 供应商 SDK 的 LLM 调用路径。
- 全部 LLM 调用都经过 `ai_core/llm` 与 `ai_core/routing` 的稳定入口。
- 双层 Router 职责清晰且可验证：业务路由与高可用调度相互解耦。
- 费控、可观测、降级、回滚链路可演练且具备日志证据。
- 质量门禁通过，核心业务链路回归通过。
