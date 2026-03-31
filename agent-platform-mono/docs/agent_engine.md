# agent_engine 层能力设计说明

定位：编排框架层。提供 Agent 元数据注册、基础 LangGraph 工作流与检查点持久化，支持多 Agent/子图编排。对上游 `domain_agents` 暴露“注册 Agent、获得可运行实例”的能力。

## 设计目标
- 稳定：流程节点明确、状态可恢复（checkpoint）。
- 复用：可复用基础工作流（含工具节点、记忆、RAG）。
- 扩展：支持子图/多 Agent 编排，工具开放。

## 能力总览
- Agent 注册表（AgentMeta）
- 可复用基础工作流（base_agent）
- 编排中间件流水线（Middleware / Guard）
- Checkpoint 管理（Redis/内存）
- 多 Agent 编排（子图/ToolNode）

## 模块与提供方式

### 1) Agent 注册表
- 位置：`core/agent_engine/agents/registry.py`
- 能力：
  - `register(meta: AgentMeta)`：注册 Agent 基元
  - `get(agent_id: str) -> AgentMeta | None`
  - `list_all() -> list[AgentMeta]`
- AgentMeta 示例字段：
  - `agent_id`: 唯一标识
  - `name`: 展示名称
  - `description`: 说明
  - `factory`: `() -> Graph`（返回可运行的 graph 实例）
- `domain_agents/*/register.py` 将本域 Agent 注册到注册表

### 2) 基础工作流（Base Agent）
- 位置：`core/agent_engine/workflows/base_agent.py`
- 配套中间件：`core/agent_engine/workflows/middlewares.py`
- 当前状态字段：`messages`, `conversation_id`, `tenant_id`, `memory_context`, `rag_context`, `step_count`
- 当前主流程：`retrieve_memory -> retrieve_rag -> llm_reason -> (tools | update_memory)`
- 当前实现要点：
  - `llm_reason` 已拆分为洋葱圈中间件流水线：`MaxStepsGuard -> ContextInjector -> LLMAction`
  - `ContextInjector` 负责把 Prompt、Memory 与 RAG 组装成 `SystemMessage`
  - `MaxStepsGuard` 负责步数拦截与 `step_count` 自动递增
  - `should_continue` 根据 `tool_calls` 与最大步数决定是否进入 `ToolNode`
- 可插拔：可按域定制工具列表与 `MemoryConfig`
- 提供方式：
  - `domain_agents` 复用 `build_base_agent(tools, memory_config, ...)` 或自定义 workflow

### 3) Middleware / Guard
- 位置：`core/agent_engine/workflows/middlewares.py`
- 能力：
  - `build_middleware_pipeline(middlewares, base_action)`：按洋葱模型串联横切逻辑
  - `MaxStepsGuard`：在进入 LLM 前拦截超步数请求，并保证步数回写
  - `ContextInjector`：把 `prompt_gateway`、`memory_context`、`rag_context` 注入成统一系统提示
- 价值：
  - 将步数治理、上下文注入与模型推理解耦，降低 `base_agent.py` 的职责耦合
  - 方便后续继续沉淀通用 Guard，例如超时治理、风险分级、输出校验

### 4) Checkpoint 管理
- 位置：`core/agent_engine/checkpoints/redis_checkpoint.py`
- 能力：
  - 生产使用 RedisSaver（支持 Human-in-the-loop 与中断恢复）
  - 本地/测试可用 MemorySaver（无外部依赖）
- 提供方式：
  - 在运行时通过 `get_checkpointer()` 获取并设置到 graph 配置中
- `config = {"configurable": {"thread_id": conversation_id, "checkpointer": ...}}`
- 配置：
  - `CHECKPOINT_BACKEND=memory|redis`（默认 `memory`）
  - `REDIS_URL` 与 `CHECKPOINT_TTL` 在选择 `redis` 时生效
  - 初始化 RedisSaver 失败时自动降级为 MemorySaver，保证可用；/ready 保持 Redis 连通性检查以决定是否放量

### 5) 多 Agent/子图编排
- 能力（建议）：
  - 子图：一个 Agent 作为 Tool（LangGraph 子图）
  - 调度：主 Agent 的 ToolNode 调用子 Agent 完成子任务
  - 状态隔离：各自 thread_id 与 checkpoint 独立（或共享会话）
- 示例思路（伪代码）：
  - policy 助手在复杂场景可调用 claim 子 Agent 完成理赔进度核验

## domain_agents 使用边界
- domain_agents 负责：
  - 定义域内 Agent 的工具清单与 MemoryConfig
  - 选择复用 base_agent 或自定义 workflow
  - 在 `register.py` 中注册到注册表
- agent_engine 负责：
  - Graph 构建/运行的通用机制、检查点与节点拼装

## 与 API 的连接
- 入口：`main.py` 的 `/agent/run` 与 `/agent/stream`
  - 通过 `agent_gateway.get(agent_id)` 获取元数据与 factory
  - 构建 graph，注入 `checkpointer` 与 `thread_id`
  - 启动运行并返回结果/流式事件

## 观测与治理
- 日志：记录 agent_id、conversation_id、thread_id、steps、耗时
- 检查点：便于排查与恢复
- 工具清单：由 `core/tool_service` 提供统一来源
- 四元透传：`tenant_id`、`conversation_id`、`thread_id`、`trace_id` 必须在 workflow 与工具调用全链路可见

## 合同与治理（自定义 workflow 的边界）
- 平台合同（必须项）
  - GraphFactory 协议：`domain_agents` 必须暴露 `factory() -> Graph`
- 标准 state 字段：`messages`, `conversation_id`, `tenant_id`, `step_count`
  - 必接入检查点：通过 `get_checkpointer()` 注入 `thread_id` 与 `checkpointer`
  - 工具调用统一走 `core/tool_service` 注册表，禁止自建 HTTP 调用
  - 租户隔离：state 或 config 中包含 `tenant_id`，全链路透传
- 注册表合规校验
  - 注册时执行静态/运行时校验：标准 state、checkpointer、工具来源、`step_count` 增长
  - 不通过则拒绝注册并记录原因
- 复用节点与钩子
  - 当前已拆出中间件层：`MaxStepsGuard`、`ContextInjector`
  - 后续继续将 base_agent 演进为可复用节点：记忆读取 → RAG 检索 → LLM 决策 → ToolNode → 记忆写回
  - 提供钩子：`pre_rewrite`/`post_rewrite`、`pre_tool`/`post_tool`
  - 策略钩子：`memory_write_policy`、`error_policy`
- 声明式优先
  - 优先通过 `RetrievalPlan`/`MemoryConfig`/工具清单表达差异
  - 仅当声明式无法覆盖时才引入自定义节点
- 统一观测与合规
  - 埋点字段：`agent_id`, `conversation_id`, `thread_id`, `tenant_id`, `graph_id`, `step_count`, `node_name`, `duration`, `error_code`
  - 统一日志：使用 `shared/logging`，禁止自定义 logger
  - 自动化合规测试（建议）：最小成功路径/错误路径/checkpoint 恢复路径、工具调用走 `tool_service`、租户头存在性
- 版本与变更控制
  - 基础节点与 base_agent 使用语义版本；破坏性变更新增 v2，旧版标记 `deprecated` 后有序迁移
  - 注册时记录 `graph_meta`（版本、依赖节点、工具列表），便于全局审计
- “完全自定义”准入门槛
  - 证明声明式与标准节点无法覆盖
  - 通过合规校验（合同、工具与检查点接入、观测规范）
  - 补充用例覆盖：最小成功/常见错误/checkpoint 恢复

## 层级稳定与依赖防腐（总则）
- 对外稳定（每层对上暴露稳定接口）：
  - agent_engine：注册/获取/运行 Graph 的稳定入口（factory、run/stream）
  - tool_service：`list_tools/invoke` 与统一鉴权
  - ai_core：`complete/stream` 与 `get_prompt/select_model`
  - memory_rag：`retrieve` 与 `get_context/append_*`
- 对内防腐（每层对下封装依赖差异）：
  - agent_engine：节点内部不直连外部系统，工具调用统一走 tool_service
  - tool_service：外部 MCP 与业务网关由适配器封装（协议/认证/错误归一）
  - ai_core：LLM Provider 适配器（SDK/模型差异屏蔽、错误与用量归一）
  - memory_rag：VectorStore 适配器（后端差异屏蔽、Filter 翻译）
- 演进与替换：
  - 新 SDK/新后端通过实现适配器接口即可替换；上层调用签名不变
  - 统一在适配层处理：重试/降级/观测/安全校验

## 最佳实践与雷区清单
- 建议
  - 优先复用 base_agent 与标准节点；通过 `MemoryConfig`/`RetrievalPlan`/工具清单调参
  - 优先复用中间件机制承载横切逻辑，不要把 Guard/Context 拼装重新写回 LLM 节点
  - 必接入 checkpointer，长链路务必可恢复
  - 工具统一走 `core/tool_service`，便于鉴权与观测
  - 日志使用 `shared/logging`，自动带 `tenant_id`/`trace_id`
- 禁止
  - 直连外部系统（越过 `tool_service`）
  - 自建日志体系、绕开租户隔离
  - 绕过注册表合规校验

## 落地建议
- 将中间件机制继续扩展到超时治理、预算治理、输出校验等横切逻辑
- 新增“合同校验器”与“注册前校验钩子”
- 将 base_agent 内部节点进一步拆分为独立可复用节点包并提供钩子
- 在 `docs/` 内维护自定义 workflow 指南与模板（factory、state、合规校验）

## 典型接入流程（domain_agents 示例）
```python
# domain_agents/policy/register.py
from core.agent_engine.agents.registry import agent_gateway, AgentMeta
from .tools.policy_tools import policy_tools
from .memory_config import POLICY_MEMORY_CONFIG
from core.agent_engine.workflows.base_agent import build_base_agent

def register():
    def factory():
        return build_base_agent(tools=policy_tools, memory_config=POLICY_MEMORY_CONFIG)

    agent_gateway.register(AgentMeta(
        agent_id="policy-assistant",
        name="保单助手",
        description="保单查询与咨询",
        factory=factory,
    ))
```

## ToolRouter（工具选择策略）
- 位置：`core/agent_engine/tools/router.py`
- 能力：
  - `select_tools(input_text, tenant_id, candidates, strategy='hybrid', top_k=3) -> list[tool]`
  - 支持策略：`keyword`、`vector`、`llm`、`hybrid`
    - keyword：按 `keywords/tags` 简单匹配
    - vector：用 `embedding_gateway` 对输入与工具描述向量化后相似度排序
    - llm：用 `llm_gateway` 在受控提示下让模型输出工具名列表（白名单校验）
    - hybrid：keyword 预筛 + vector 排序，最终经 llm 复核；失败时按加权得分回退
- 使用边界：
  - domain_agents 提供候选集合（包含 `name/description/keywords/tool`）
  - 在构建 Base Agent 前调用选择策略得到最终工具列表
  - 工具调用仍通过 `ToolNode` 与 `tool_service`，不越过接入层

## 动态编排方案（可控动态）
- 目标：在保持平台合同与安全边界的前提下，让 Agent 根据上下文动态决定“是否调用工具、进入哪个节点、是否直接结束”。
- 原则：
  - 不是完全自由编排，而是“静态骨架 + 动态分支”
  - 编排边界由 `agent_engine` 控制，节点路径由 Router 决策
  - 工具调用由“模型建议 + 策略复核”双层判定

### 推荐拓扑
- 固定主干节点：`memory_read -> decide_next_step -> (retrieve | reason | tool_exec | finalize) -> memory_write`
- 条件边由 `decide_next_step` 统一输出：
  - `need_context`：进入 `retrieve`
  - `need_action`：进入 `tool_exec`
  - `enough_info`：进入 `reason` 或 `finalize`
  - `fallback`：异常时进入降级路径（非工具回答/备用节点）

### Router 节点职责
- 输入：`messages`, `tenant_id`, `memory_context`, `rag_context`, `tool_candidates`, `step_count`, `error_count`, `budget`
- 输出：`next_node`, `reason`, `confidence`, `selected_tools`, `guard_flags`
- 判定信号（建议）：
  - 信息充分性：上下文是否足以回答
  - 可执行性：是否需要外部系统动作
  - 风险等级：是否涉及敏感或高成本工具
  - 预算约束：token/时延/调用次数阈值
  - 失败历史：最近是否连续失败，是否应降级

### 工具决策与治理
- 第一层（LLM）：基于工具 schema 与描述产出“是否调用工具 + 候选工具名”
- 第二层（策略层）：在 `ToolRouter` 做白名单、租户权限、配额、限流与风险策略校验
- 执行层：统一经 `tool_service.registry.invoke()`，并透传 `tenant_id/conversation_id/thread_id/trace_id`
- 失败处理：超时、鉴权失败、外部 5xx 等统一归一化后触发降级边

### 状态机与可恢复性
- 每个节点必须读写统一 state，并维护 `step_count` 与最近决策元数据
- 所有动态跳转都可回放：`next_node/reason/confidence` 写入 checkpoint
- 依赖 `thread_id + checkpointer` 保证中断恢复后可继续原路径执行

### 观测指标（建议纳入 /ready 与运营看板）
- `router_decision_count{next_node}`
- `tool_call_rate`, `tool_success_rate`, `tool_fallback_rate`
- `avg_hops_per_request`, `p95_latency_by_node`
- `degrade_count`, `max_step_guard_triggered`
- 按 `tenant_id/agent_id` 维度聚合，支持灰度与回滚决策

### 最小可落地版本（MVP）
- 新增 `decide_next_step` 节点，仅输出 `retrieve/tool_exec/reason/finalize`
- 先使用规则 + 轻量 LLM 混合判定，保留阈值配置在 `shared/config/settings.py`
- 将工具候选集合前置到构图阶段，运行时只做选择与执行
- 对 `tool_exec` 增加一次重试与一次降级，不做无限回环
