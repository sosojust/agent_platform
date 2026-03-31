# 基于 DeerFlow 的 Core 层架构演进规划

## 1. 背景与基准前提
- **核心定位**：当前系统核心是 **Agent Platform (基建层，即 `core` 目录)**。
- **业务域**：`domain_agents` 目录下的业务（如保单、理赔等）目前均视为**示例和验证场景**，非最终实际使用场景。因此，所有的能力沉淀和架构优化都必须收敛到 `core` 层，对上游提供通用、可复用、可插拔的接口。
- **明确排除**：根据规划，**IM 渠道接入**（飞书/企微等）当前阶段**暂不考虑**。

---

## 2. 核心改造点与演进路径（按优先级排序）

### 【P0】记忆系统深度增强（Agent 效果的核心决定因素） [✅ 已完成]
**痛点**：目前 `core/memory_rag/memory` 的实现以 Redis 短期滑动窗口（带简单去重和过滤）和基础的向量化检索为主，缺乏深度的语义理解和结构化沉淀，导致长线对话中的关键信息容易丢失或被淹没。
**Core 层演进方案**：
1. **引入 LLM 结构化事实提取**：
   - 弃用单纯的“历史对话记录”作为长期记忆，改为异步队列触发 LLM 提取**结构化事实（Facts）**。
   - 提取的 Fact 必须包含：`category`（分类）、`confidence`（置信度）、`createdAt`（创建时间）等元数据。
2. **记忆去重与更新机制**：
   - 实现基于内容哈希（Content Hash）和语义相似度的去重，防止重复事实堆积。
   - 具备事实修正能力（例如用户改变了之前的意图或条件，新的事实需要覆盖旧事实）。
3. **分层存储与注入限额（Token 预算控制）**：
   - 定义清晰的记忆层级：如 `short_term_context`（近期对话）、`working_memory`（当前任务关键事实）、`long_term_background`（租户/用户全局画像）。
   - 在构建 Prompt Context 时，增加 `max_injection_tokens` 的严格预算控制，按优先级动态组装记忆，防止撑爆上下文。

### 【P0】层级边界与防腐门禁（防止架构腐化） [✅ 已完成]
**痛点**：当前项目缺乏硬性约束，存在 `core` 层或 `shared` 层反向依赖 `domain_agents` 示例代码的风险。
**Core 层演进方案**：
1. **自动化 AST 扫描门禁**：
   - 在 `tests/` 目录下新增基于 `ast` 模块的静态代码分析单测（如 `test_architecture_boundary.py`）。
   - 强校验规则：`core/` 和 `shared/` 目录下的所有文件，绝对不允许出现 `import domain_agents` 及其子模块的语句。
2. **强制单向依赖**：
   - `domain_agents` 只能通过平台稳定接口（`agent_engine(factory/run)`, `tool_service`, `ai_core` 等）调用核心能力。

### 【P1】编排层解耦：引入 Middleware / Guard 模式 [✅ 已完成]
**痛点**：在 `core/agent_engine/workflows/base_agent.py` 中，诸如 `make_llm_reason_node` 的工厂函数内部糅合了多项职责：步骤超限拦截（MaxSteps）、Prompt 拼接、记忆与 RAG 上下文注入、LLM 调用。职责不单一，极难进行单元测试和局部复用。
**Core 层演进方案**：
1. **抽象中间件机制**：借鉴 DeerFlow 的横切关注点分离思想，将流程编排中的通用控制逻辑抽离为 Middleware 或独立 Node：
   - **`MaxStepsGuard`**：专门负责检查流转步数并决定是否强制中断。
   - **`ContextInjector`**：专门负责将 Memory、RAG 的检索结果组装进 System Prompt。
   - **`LLMAction`**：纯粹的大模型推理节点。
2. **通用性提升**：
   - 将原定理赔域中特殊的 `doc_verify` 等逻辑抽象成“通用材料核验中间件”沉淀到 `core` 层，上游域只需传入不同的 `材料核验配置清单` 即可复用。

### 【P1】统一动态配置访问层 [✅ 已完成]
**痛点**：当前 `shared/config/nacos.py` 通过监听 Nacos 更新，并把新值直接塞入 `settings._dynamic` 字典中。这导致代码中存在隐式的两套配置读取路径，一旦字段漂移容易静默失败。
**Core 层演进方案**：
1. **封装 `DynamicSettings` 代理类**：
   - 重构 `settings` 的访问模式，隐藏内部的 `_dynamic` 字典。
   - 提供一个统一的 `get(key, fallback)` 方法：优先读取 Nacos 动态缓存，未命中则回退到 Pydantic 的静态环境变量默认值。
2. **配置版本化**：
   - 增加 `config_version` 字段，确保服务运行时的配置快照具备可追溯性。

### 【P2】核心引擎：子 Agent 并发编排支持 [🚧 已启动]
**痛点**：目前 `agent_engine` 主要是单 Agent 的串行工作流。对于复杂的企业级任务（如需要同时查询多个独立子系统并汇总，或者执行多步材料核验），单线串行效率低且容易“偏题”。
**Core 层演进方案**：
1. **提供原生 `SubagentExecutor`**：
   - 在 `core/agent_engine` 增加子 Agent 调度机制，允许主 Agent (Lead Agent) 作为图中的一个节点，并发 Spawn 多个子 Agent 图。
2. **状态隔离与上下文共享**：
   - 子 Agent 拥有独立的 `thread_id` 和独立的步数控制、超时控制机制，但与主 Agent 共享 `tenant_id` 和高维意图上下文。

**当前落地进度（2026-03-31）**：
1. 已新增 `core/agent_engine/subagent_gateway.py`，提供 `SubagentTask`、`SubagentResult`、`subagent_gateway.run_batch(...)` 与 `make_subagent_executor_node(...)` 四个基础构件。
2. 已实现子 Agent 线程隔离策略：默认按 `{parent_conversation_id}:{task_id|agent_id}` 生成独立 `thread_id`，同时复用主流程的 `tenant_id`。
3. 已实现高维上下文共享：主流程的 `memory_context`、`rag_context` 与显式 `shared_context` 会在进入子 Agent 前统一拼装并透传。
4. 已增加运行时治理：通过 `ORCH_SUBAGENT_MAX_CONCURRENCY` 与 `ORCH_SUBAGENT_TIMEOUT_SECONDS` 控制并发度与超时。
5. 已将 `SubagentGateway` 接入 `workflows/plan_execute.py`：当主 Agent 在 `AgentMeta.sub_agents` 中声明可派发子 Agent，且请求命中“并行/同时/汇总”等关键词时，会自动走并发子 Agent 执行路径。
6. 已新增 `subagent_planner_gateway.py`、`subagent_planner_provider.py` 与 `subagent_planner_provider_protocols.py`，将 Planner 决策抽象为可插拔 Provider，当前支持 `rule/llm/hybrid` 三种模式。
7. Planner 已输出显式 `route_decision`，将 `executor/sub_agents/aggregation_strategy/aggregation_params/reason/decision_source` 作为决策结果写入状态，不再由执行节点隐式决定聚合策略。
8. 已新增 `core/agent_engine/subagent_aggregator.py`，将多子 Agent 返回统一收敛为 `final_output/success_count/error_count/selected_agent_ids/conflict_detected` 等标准字段，内置 `summary`、`priority`、`vote`、`confidence_rank`、`conflict_resolution` 五种聚合策略，并支持优先级顺序、最低置信度阈值、冲突裁决模板等参数。
9. `workflows/state.py` 已补齐 `subagent_aggregation` 与 `subagent_metrics` 状态字段，`plan_execute` 在并发子 Agent 执行后会同时回填原始结果、聚合结果与耗时指标，便于后续总结、流式输出与审计。
10. `subagent_gateway`、`metrics_gateway` 与 `/agent/stream` 已补齐自定义流式事件、耗时指标与监控看板快照：支持 `subagent.planner.decision`、`subagent.batch.*`、`subagent.task.*`、`subagent.aggregation.completed`、`subagent.metrics` 事件，以及 `GET /observability/subagents` 的统一看板输出。
11. 已补齐单元/集成测试：覆盖 Provider 决策、参数化聚合、监控看板路由、并发执行、缺失子 Agent 错误、默认上下文注入、子线程隔离、流式自定义事件与 plan-execute 集成派发。

**后续待补齐**：
- 将当前 Provider 体系继续扩展为真正的 Router/Planner 组合架构，使规则、LLM、ToolRouter 与历史反馈可以共同参与决策。
- 为聚合策略补齐更细粒度的策略参数治理能力，如 vote 平票裁决规则、策略白名单与租户级覆盖。
- 将当前事件/耗时指标进一步接入告警阈值、长期存储与 tenant/agent 维度 SLA 看板，形成完整运营闭环。

---

## 3. 落地建议（下一步行动）

结合当前 `agent_platform` 的基建属性，建议优先从 **P0** 级别的两项开始落地：
1. **先落实架构门禁**：耗时极短，马上可以加上 CI 测试，防患于未然。
2. **集中力量重构 Memory 层**：针对 `core/memory_rag/memory` 进行结构化重写，将现有的简单拼凑升级为具备“特征提取、去重合并、预算控制”的强记忆系统。
