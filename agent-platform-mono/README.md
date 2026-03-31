# Agent Platform

团险业务多租户 Agent 平台，采用单体 Python 服务形态，基于 FastAPI + LangGraph 实现可扩展编排、工具调用与记忆/RAG 能力。

## 项目介绍

本项目聚焦以下目标：

- 以统一稳定接口承载 Agent 编排、工具服务、模型调用、记忆与检索能力
- 以多租户为一等公民，贯穿状态、检索、工具调用、日志与链路追踪
- 以防腐层隔离三方 SDK 差异，确保上层业务代码稳定演进
- 以可观测与可降级为底线，支持 /health、/ready 与关键链路打点

## 项目架构

### 分层架构（核心边界）

- `app/gateway`：应用层入口（FastAPI 实例、lifespan、routers、异常处理与健康检查）
- `domain_agents/`：业务域编排与注册（如 policy/claim/customer），通过平台稳定接口接入能力
- `core/agent_engine`：工作流编排与模式选择（command / plan_execute）
- `core/tool_service`：工具注册与调用统一入口（MCP/Skill）
- `core/ai_core`：Prompt 管理、LLM 客户端与模型路由
- `core/memory_rag`：Embedding、向量检索、记忆管理、消息过滤/压缩、RAG Pipeline
- `shared`：配置、日志、中间件、跨层模型

### 关键调用链路

1. 请求经 `main.py` 转发至 `app/gateway/app.py`，中间件注入 `tenant_id/conversation_id/thread_id/trace_id`
2. `agent_engine` 根据 agent 元数据与输入选择编排模式
3. 编排节点通过 `ai_core` 调 LLM，通过 `tool_service` 调工具，通过 `memory_rag` 做记忆、消息过滤/压缩与检索
4. 输出结果并记录统一结构化日志，状态由 checkpoint 管理

### 目录结构（精简）

```text
agent-platform-mono/
├── main.py
├── pyproject.toml
├── .env.example
├── app/
│   └── gateway/
│       ├── app.py
│       ├── lifespan.py
│       ├── error_handlers.py
│       ├── readiness.py
│       └── routers/
│           ├── agents.py
│           ├── tools.py
│           └── health.py
├── shared/
├── core/
│   ├── ai_core/
│   ├── memory_rag/
│   ├── tool_service/
│   └── agent_engine/
├── domain_agents/
│   ├── policy/
│   ├── claim/
│   └── customer/
├── tests/
└── docs/
```

## 模块职责

### shared

- `config/settings.py`：统一配置入口（pydantic-settings）
- `config/nacos.py`：Nacos 动态配置加载
- `logging/logger.py`：JSON 结构化日志
- `middleware/tenant.py`：租户与链路上下文注入

### core/ai_core

- `prompt/manager.py`：PromptGateway（统一 Prompt 入口，内部 Provider 链路兜底）
- `llm/client.py`：LLMGateway（统一 LLM 入口，屏蔽三方 SDK 差异，内置同模型多部署高可用路由）
- `routing/router.py`：业务语义路由（按 scene/task_type 映射模型能力与敏感约束）
- `embedding/provider.py`：Embedding 抽象与默认实现

### core/memory_rag

- `memory/manager.py`：MemoryGateway（短期记忆写入治理、LLM 结构化长期记忆、内容 Hash 去重、上下文预算控制）
- `memory/config.py`：记忆/RAG 策略配置（含新增 M1/M2 配置项）
- `memory/filters.py`：消息过滤器（如噪声/重复/工具中间态过滤）与策略注册
- `memory/compressor.py`：消息压缩器（如 simple/llm 摘要压缩）与策略装配
- `memory/extractor.py`：长期记忆事实提取器（`LLMFactExtractor`，提取 `fact/category/confidence/timestamp`）
- `rag/pipeline.py`：RagGateway（召回与精排流水线）
- `vector/store.py`：VectorGateway（当前向量库实现为 QdrantProvider）
- `rag/filters.py`：Filter DSL 到后端过滤表达式转换

### core/tool_service

- `registry.py`：ToolGateway（统一工具列表与调用入口）
- `mcp/*.py`：内部/外部 MCP 适配
- `client/gateway.py`：业务网关调用与错误归一化

### core/agent_engine

- `workflows/base_agent.py`：基础编排骨架
- `workflows/middlewares.py`：编排中间件流水线（`MaxStepsGuard`、`ContextInjector`）
- `workflows/plan_execute.py`：计划执行模式（通过可插拔 Planner Provider 输出显式 `route_decision`，支持子 Agent 派发策略与聚合策略决策）
- `subagent_gateway.py`：子 Agent 并发调度入口（任务建模、线程隔离、上下文透传、并发/超时治理、事件上报）
- `subagent_aggregator.py`：子 Agent 结果标准聚合器（summary/priority/vote/confidence_rank/conflict_resolution 策略）
- `subagent_planner_gateway.py`：子 Agent Planner Gateway（支持 `rule/llm/hybrid` Provider）
- `orchestrator_factory.py`：编排工厂与模式分发
- `mode_selector.py`：模式选择与降级策略
- `tools/router.py`：工具选择与提示词管理接入

### domain_agents

业务域（policy/claim/customer）通过 `register.py` 注册 agent、工具与 memory 配置，框架层无需改动。

## 项目依赖

### 运行时依赖

- Python `>=3.11`
- FastAPI / Uvicorn
- LangGraph / LangChain
- LiteLLM
- Redis
- Qdrant Client（当前向量存储实现）
- Sentence Transformers / FlagEmbedding
- Langfuse / OpenTelemetry

### 开发依赖

- pytest / pytest-asyncio / pytest-cov
- ruff
- mypy（strict）

## 项目配置

统一通过 `.env` 管理（参考 `.env.example`），关键配置如下：

| 配置组 | 关键变量 |
|---|---|
| 服务 | `APP_ENV` `HOST` `PORT` |
| 编排 | `ORCH_DEFAULT_MODE` `ORCH_MAX_STEPS` `ORCH_MAX_REPLANS` `ORCH_PLAN_EXECUTE_AGENTS` `ORCH_PLAN_EXECUTE_TENANTS` `ORCH_SUBAGENT_MAX_CONCURRENCY` `ORCH_SUBAGENT_TIMEOUT_SECONDS` `ORCH_SUBAGENT_PLANNER_PROVIDER` `ORCH_SUBAGENT_PRIORITY_ORDER` `ORCH_SUBAGENT_MIN_CONFIDENCE` `ORCH_SUBAGENT_CONFLICT_RESOLUTION_TEMPLATE` `ORCH_SUBAGENT_HYBRID_MERGE_MODE` `ORCH_SUBAGENT_HYBRID_RULE_WEIGHT` `ORCH_SUBAGENT_HYBRID_LLM_WEIGHT` `ORCH_SUBAGENT_HYBRID_TIE_BREAKER` `ORCH_SUBAGENT_HYBRID_STRATEGY_MERGE_MODE` `ORCH_SUBAGENT_HYBRID_SUBAGENT_MERGE_MODE` `ORCH_SUBAGENT_AGGREGATION_OVERRIDES` |
| 模型 | `LLM_DEFAULT_MODEL` `LLM_STRONG_MODEL` `LLM_MEDIUM_MODEL` `LLM_NANO_MODEL` `LLM_LOCAL_MODEL` `LLM_ROUTER_DEPLOYMENTS` `LLM_ROUTER_COOLDOWN_SECONDS` `LLM_ROUTER_MAX_ATTEMPTS` `LLM_CACHE_ENABLED` `LLM_CACHE_DEFAULT_TTL_SECONDS` `LLM_CACHE_SCENE_TTL` `LLM_CACHE_TASK_TTL` `LLM_CACHE_MAX_ENTRIES` `OPENAI_API_KEY` `ANTHROPIC_API_KEY` |
| Prompt/Nacos | `NACOS_SERVER_ADDR` `NACOS_NAMESPACE` `NACOS_GROUP` `NACOS_DATA_ID` |
| 向量与检索 | `VECTOR_DB_BACKEND` `QDRANT_URL` `EMBEDDING_MODEL` `RERANK_MODEL` `EMBEDDING_DEVICE` |
| 缓存与状态 | `REDIS_URL` `CHECKPOINT_BACKEND` `CHECKPOINT_TTL` |
| 工具网关 | `INTERNAL_GATEWAY_URL` `GATEWAY_TIMEOUT` |
| 观测 | `LANGFUSE_HOST` `LANGFUSE_PUBLIC_KEY` `LANGFUSE_SECRET_KEY` `OTEL_EXPORTER_OTLP_ENDPOINT` `OBS_SUBAGENT_BACKEND` `OBS_SUBAGENT_REDIS_PREFIX` `OBS_SUBAGENT_RECENT_LIMIT` |

## 项目使用说明

### 1) 本地启动

```bash
docker compose -f docker-compose.dev.yml up -d
pip install -e ".[dev]"
cp .env.example .env
uvicorn main:app --reload --port 8000
```

### 2) 健康检查

- `GET /health`：进程健康状态
- `GET /ready`：就绪状态（模型、prompts、rag、redis、qdrant 等分项）

### 3) 常用接口

- `GET /agent/list`：查看已注册 Agent
- `POST /agent/run`：同步执行
- `POST /agent/stream`：SSE 流式执行
- `GET /observability/subagents`：查看子 Agent 监控看板快照
- `GET /tools`：列出工具（需 `X-App-Id/X-App-Token`）
- `POST /tools/invoke`：调用工具（需 `X-App-Id/X-App-Token`）

### 4) 最小调用示例

```bash
curl -X POST "http://localhost:8000/agent/run" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: demo-tenant" \
  -d '{
    "agent_id": "policy_agent",
    "input": "帮我查询保单状态",
    "conversation_id": "conv-001"
  }'
```

### 5) 开发质量门禁

```bash
pytest -q
mypy .
ruff check .
```

## Memory 模块当前进展

已完成（M1/M2）：

- 写入治理：空白过滤、噪声过滤、短窗口去重
- 策略模块化：过滤能力下沉到 `memory/filters.py`，压缩能力下沉到 `memory/compressor.py`
- 平台契约：新增 `memory/provider_protocols.py`（`MessageFilter`/`MessageCompressor`/`TokenizerProvider`/`LongTermExtractor`）
- 压缩策略：新增 `window/simple_summary/llm_summary` 与 `char/tiktoken` tokenizer provider
- 长期记忆：`append_long_term` / `retrieve_long_term`
- 结构化提取：`LLMFactExtractor` 从短期对话中提取长期 Fact，补齐 `category/confidence/timestamp`
- 长期去重：写入时基于内容 MD5 Hash 生成稳定 ID，避免重复事实堆积
- 短转长：达到阈值自动触发 `consolidate_short_to_long`
- 上下文构建：按 `【相关历史事实】` + `【近期对话】` 聚合，并用 `max_injection_tokens` 控制注入预算
- 配置扩展：`memory_noise_filter_enabled`、`short_to_long_trigger_turns`、`long_term_retrieve_top_k`、`max_injection_tokens`、`memory_types_default`、`filter_strategies`、`compression_strategy`、`compression_threshold`、`compression_token_threshold`
- 单元测试：覆盖噪声过滤、去重、窗口压缩、触发 consolidate、Fact 聚合读取与上下文格式

规划中（M3）：

- 长期写入去重增强（semantic merge / 事实修正）
- 读取时间衰减与结果治理
- 与 RAG 融合权重治理
- 异步压缩清理与可观测指标完善
- 短转长异步化队列与 working memory 分层

详见：`docs/memory_rag.md` 与 `docs/memory-最小可落地改造任务清单.md`

## 新增业务域（标准流程）

1. 在 `domain_agents/<domain>/` 新增 `register.py`、`*_agent.py`、`memory_config.py`、`tools/`、`prompts/`
2. 在 `register.py` 声明 agent 元信息、候选工具、memory 配置
3. 重启服务后自动注册，无需改 `main.py`

## 变更记录

- 2026-03-31
  - `core/agent_engine/agents/registry.py` 为 `AgentMeta` 增加 `sub_agents` 声明式字段，用于定义主 Agent 可派发的子 Agent 白名单
  - `core/agent_engine/subagent_planner_gateway.py`、`subagent_planner_provider.py`、`subagent_planner_provider_protocols.py` 新增可插拔 Planner Provider 机制，支持 `rule/llm/hybrid` 三种决策模式
  - `core/agent_engine/workflows/plan_execute.py` 输出显式 `route_decision`，由 Planner Provider 决定 `executor/sub_agents/aggregation_strategy/aggregation_params`，并回填 `subagent_metrics`
  - `core/agent_engine/subagent_gateway.py` 增强子 Agent 调度链路，补齐 `duration_ms`、批次/任务级自定义流式事件与耗时日志
  - `core/agent_engine/subagent_aggregator.py` 扩展标准聚合器，支持参数化优先级顺序、最低置信度阈值、冲突裁决模板，并新增 `vote`、`confidence_rank`、`conflict_resolution` 策略
  - `shared/observability/metrics_gateway.py` 与 `GET /observability/subagents` 接入统一监控看板快照，沉淀子 Agent 批次/聚合指标
  - `app/gateway/routers/agents.py` 在 `/agent/stream` 中透传 `on_custom_event`，使子 Agent 派发与聚合事件可直接通过 SSE 输出
  - `shared/observability/metrics_gateway.py` 支持 `memory/redis` 可切换存储后端，指标快照可按 `tenant_id/parent_agent_id` 维度聚合并支持多实例共享
  - `core/agent_engine/subagent_planner_provider.py` 的 Hybrid Provider 升级为显式合并策略（权重投票、冲突裁决、子 Agent 合并模式），不再仅 rule 优先
  - 子 Agent 聚合参数支持租户级/Agent级/租户+Agent级动态覆盖（`ORCH_SUBAGENT_AGGREGATION_OVERRIDES`），并在 `plan_execute` 的 `route_decision` 输出置信度与合并调试信息
  - `shared/config/settings.py` 新增子 Agent 调度配置项：`ORCH_SUBAGENT_MAX_CONCURRENCY`、`ORCH_SUBAGENT_TIMEOUT_SECONDS`
  - 新增/扩展测试：`tests/core/agent_engine/test_subagent_planner_gateway.py`、`tests/core/agent_engine/test_subagent_gateway.py`、`tests/core/agent_engine/test_subagent_aggregator.py`、`tests/core/agent_engine/test_plan_execute.py` 与 `tests/test_main.py`，覆盖 Provider 决策、参数化聚合、监控看板路由与流式自定义事件
  - `core/memory_rag/memory/extractor.py` 新增 `LLMFactExtractor`，将短期对话提取为结构化长期事实并补齐 `category/confidence/timestamp`
  - `core/memory_rag/memory/manager.py` 新增长期记忆内容 Hash 去重与 `max_injection_tokens` 预算控制，统一输出 `【相关历史事实】` / `【近期对话】` 上下文格式
  - `core/agent_engine/workflows/middlewares.py` 新增编排中间件流水线，将 `MaxStepsGuard` 与 `ContextInjector` 从 LLM 推理节点中解耦
  - `shared/config/settings.py` 引入 `DynamicSettings` 动态配置代理，统一静态配置回退与 Nacos 动态配置访问
  - `shared/config/nacos.py` 改为通过 `settings.update_dynamic()` 落盘动态配置，并保留对现有 `settings.llm.*` 读取方式的兼容
  - 新增 `tests/test_architecture_boundary.py`，基于 AST 校验 `core/`、`shared/` 不反向依赖 `domain_agents/`
  - README、`docs/memory_rag.md`、`docs/agent_engine.md` 同步更新 Core 层现状说明
  - `core/ai_core/llm/client.py` 新增 LiteLLM 同模型多部署高可用路由：支持按部署轮询、失败熔断冷却、自动重试与默认部署兜底
  - `shared/config/settings.py` 新增路由配置项：`LLM_ROUTER_DEPLOYMENTS`、`LLM_ROUTER_COOLDOWN_SECONDS`、`LLM_ROUTER_MAX_ATTEMPTS`
  - `core/ai_core/llm/client.py` 落地统一缓存策略：按 `scene/task_type` 自动命中 TTL，移除上游显式 cache 开关透传
  - `shared/config/settings.py` 新增缓存配置项：`LLM_CACHE_ENABLED`、`LLM_CACHE_DEFAULT_TTL_SECONDS`、`LLM_CACHE_SCENE_TTL`、`LLM_CACHE_TASK_TTL`、`LLM_CACHE_MAX_ENTRIES`
  - `shared/config/nacos.py` 增加 LLM Router/模型/缓存动态配置覆盖能力，支持运行时热更新
  - 新增测试：`tests/core/ai_core/test_llm_gateway_runtime.py` 与 `tests/core/memory_rag/test_rag_pipeline.py`，覆盖生效模型、fallback、usage 统计与 RAG rewrite 场景路由
  - `core/memory_rag/memory/compressor.py` 的 `llm_summary` 路径完成 `scene` 优先路由并兼容旧 `task_type` 参数
  - `docs/ai_core-LiteLLM迁移任务清单.md` 完成“双层 Router 改造”中 LiteLLM 高可用调度项
  - `pyproject.toml` 增加 `asyncio_default_fixture_loop_scope=function`，消除 `pytest-asyncio` 默认事件循环作用域弃用告警
  - `core/tool_service/skills/base.py` 补齐 `skill` 装饰器类型签名，减少严格类型检查下的未类型化装饰器告警
  - `domain_agents/*/tools/*.py` 补齐 `dict[str, Any]` 与工具列表类型注解，修复工具层一批 mypy 报错
  - `tests/apps/*.py` 与 `tests/test_main.py` 补齐异步测试函数与 fixture 类型注解
  - `tests/core/memory_rag/test_rag_pipeline.py` 改为字符串路径 monkeypatch，规避模块导出属性类型检查告警

- 2026-03-30
  - 架构范围更新：将 chat message 的“消息过滤/压缩”明确纳入 `core/memory_rag`（memory 层负责定义与实现，agent_engine 负责编排调用）
  - README 补充 `core/memory_rag` 下 `memory/filters.py` 与 `memory/compressor.py` 的职责说明，并更新关键调用链路描述
  - `memory/manager.py` 已移除内联 `_is_noise/_normalize_content/_is_duplicate_recent`，统一复用 `filters.py` 与 `compressor.py`
  - 新增 `tests/memory/test_filters_compressor.py`，覆盖内容规范化、噪声识别、近窗去重与窗口压缩
  - 文档对齐：`docs/消息过滤和压缩.md` 按当前 `manager.py` 流程更新
  - 新增平台级能力契约 `core/memory_rag/memory/provider_protocols.py`，定义 Filter/Compressor/Tokenizer/Extractor 抽象
  - 命名对齐：`contracts.py` 更名为 `provider_protocols.py`，统一 `*_gateway`（对上）与 `*_provider`（对下）语义边界
  - 新增压缩策略实现：`SimpleSummaryCompressor`、`LLMSummaryCompressor`，并通过 `compression_strategy` 配置路由
  - 新增 token 计数提供者抽象：`build_tokenizer(char/tiktoken)`，支持 token 阈值触发压缩
  - 架构重构：`apps/` 更名为 `domain_agents/`，新增 `app/gateway` 应用层并拆分为 `app.py`、`lifespan.py`、`routers/*`
  - `main.py` 简化为单行导出：`from app.gateway.app import app`，保持 `uvicorn main:app` 与 Docker 启动兼容
  - `shared/fastapi_utils` 下沉到 `app/gateway`（`readiness.py`、`error_handlers.py`），并完成所有引用迁移
  - 测试与导入路径同步更新：`apps.*` 全部替换为 `domain_agents.*`
  - 基于近期架构与 Memory 模块沟通，完整重构 README：更新项目介绍、分层职责、依赖配置、接口说明、质量门禁与 Memory 进展
  - 统一命名：`core/memory_rag/embedding/gateway.py` 对外实例命名为 `embedding_gateway`，并同步更新 RAG、Memory、ToolRouter、向量存储与就绪检查引用
  - 进一步统一 ACL 命名：对上统一 `*_gateway`（`llm_gateway`/`prompt_gateway`/`memory_gateway`/`rag_gateway`/`tool_gateway`/`agent_gateway`），对下统一 `*_provider`（含 MCP 与外部依赖适配）

- 2026-03-27
  - 新增双模式动态编排：`command` 与 `plan_execute`，运行时由 `orchestrator_factory` 按租户/Agent/输入自动选择
  - 扩展 `AgentMeta`：支持 `orchestration_mode`、`routing_mode`、`fallback_mode`、`max_replans`
  - 新增配置：`ORCH_DEFAULT_MODE`、`ORCH_MAX_STEPS`、`ORCH_MAX_REPLANS`、`ORCH_PLAN_EXECUTE_AGENTS`、`ORCH_PLAN_EXECUTE_TENANTS`
  - `main.py` 的 `/agent/run` 与 `/agent/stream` 接入统一编排工厂，返回结果附带模式信息
  - 新增测试：`test_mode_selector.py`、`test_orchestrator_factory.py`
  - `core/agent_engine/tools/router.py` 的 LLM 工具选择提示词接入 `PromptManager`
  - 明确 `memory_rag` 中 Memory 职责边界，并新增任务文档维护最小可落地改造清单
  - `MemoryConfig` 新增配置：`memory_noise_filter_enabled`、`short_to_long_trigger_turns`、`long_term_retrieve_top_k`、`memory_types_default`
  - `memory/manager.py` 新增写入治理、长期记忆读写、短转长触发与上下文聚合
  - 新增 `tests/memory/test_manager.py` 覆盖关键场景

- 2026-03-26
  - 新增 Embedding Provider、Embedding Service、Rerank Service 与 Prompt Provider
  - 启动阶段增加 embedding/rerank 预热与 readiness 分项检查
  - 新增向量存储与最小 RAG 闭环能力
