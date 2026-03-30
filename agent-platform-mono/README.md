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

- `apps/`：业务域编排与注册（如 policy/claim/customer），通过平台稳定接口接入能力
- `core/agent_engine`：工作流编排与模式选择（command / plan_execute）
- `core/tool_service`：工具注册与调用统一入口（MCP/Skill）
- `core/ai_core`：Prompt 管理、LLM 客户端与模型路由
- `core/memory_rag`：Embedding、向量检索、记忆管理、RAG Pipeline
- `shared`：配置、日志、中间件、跨层模型

### 关键调用链路

1. 请求进入 `main.py`，中间件注入 `tenant_id/conversation_id/thread_id/trace_id`
2. `agent_engine` 根据 agent 元数据与输入选择编排模式
3. 编排节点通过 `ai_core` 调 LLM，通过 `tool_service` 调工具，通过 `memory_rag` 做记忆与检索
4. 输出结果并记录统一结构化日志，状态由 checkpoint 管理

### 目录结构（精简）

```text
agent-platform-mono/
├── main.py
├── pyproject.toml
├── .env.example
├── shared/
├── core/
│   ├── ai_core/
│   ├── memory_rag/
│   ├── tool_service/
│   └── agent_engine/
├── apps/
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

- `prompt/manager.py`：Prompt 拉取与本地兜底
- `llm/client.py`：统一 LLM 客户端封装
- `routing/router.py`：按任务类型路由模型
- `embedding/provider.py`：Embedding 抽象与默认实现

### core/memory_rag

- `memory/manager.py`：短期记忆写入治理、长期记忆读写、短转长触发与上下文聚合
- `memory/config.py`：记忆/RAG 策略配置（含新增 M1/M2 配置项）
- `rag/pipeline.py`：召回与精排流水线
- `vector/store.py`：当前向量库实现为 Qdrant 适配器
- `rag/filters.py`：Filter DSL 到后端过滤表达式转换

### core/tool_service

- `registry.py`：统一工具列表与调用入口
- `mcp/*.py`：内部/外部 MCP 适配
- `client/gateway.py`：业务网关调用与错误归一化

### core/agent_engine

- `workflows/base_agent.py`：基础编排骨架
- `workflows/plan_execute.py`：计划执行模式
- `orchestrator_factory.py`：编排工厂与模式分发
- `mode_selector.py`：模式选择与降级策略
- `tools/router.py`：工具选择与提示词管理接入

### apps

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
| 编排 | `ORCH_DEFAULT_MODE` `ORCH_MAX_STEPS` `ORCH_MAX_REPLANS` `ORCH_PLAN_EXECUTE_AGENTS` `ORCH_PLAN_EXECUTE_TENANTS` |
| 模型 | `LLM_DEFAULT_MODEL` `LLM_STRONG_MODEL` `OPENAI_API_KEY` `ANTHROPIC_API_KEY` |
| Prompt/Nacos | `NACOS_SERVER_ADDR` `NACOS_NAMESPACE` `NACOS_GROUP` `NACOS_DATA_ID` |
| 向量与检索 | `VECTOR_DB_BACKEND` `QDRANT_URL` `EMBEDDING_MODEL` `RERANK_MODEL` `EMBEDDING_DEVICE` |
| 缓存与状态 | `REDIS_URL` `CHECKPOINT_BACKEND` `CHECKPOINT_TTL` |
| 工具网关 | `INTERNAL_GATEWAY_URL` `GATEWAY_TIMEOUT` |
| 观测 | `LANGFUSE_HOST` `LANGFUSE_PUBLIC_KEY` `LANGFUSE_SECRET_KEY` `OTEL_EXPORTER_OTLP_ENDPOINT` |

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
- 长期记忆：`append_long_term` / `retrieve_long_term`
- 短转长：达到阈值自动触发 `consolidate_short_to_long`
- 上下文构建：短期 + 长期聚合
- 配置扩展：`memory_noise_filter_enabled`、`short_to_long_trigger_turns`、`long_term_retrieve_top_k`、`memory_types_default`
- 单元测试：覆盖噪声过滤、去重、触发 consolidate、聚合读取

规划中（M3）：

- 长期写入去重增强（hash/semantic）
- 读取时间衰减与结果治理
- 与 RAG 融合权重治理
- 异步压缩清理与可观测指标完善

详见：`docs/memory_rag.md` 与 `docs/memory-最小可落地改造任务清单.md`

## 新增业务域（标准流程）

1. 在 `apps/<domain>/` 新增 `register.py`、`*_agent.py`、`memory_config.py`、`tools/`、`prompts/`
2. 在 `register.py` 声明 agent 元信息、候选工具、memory 配置
3. 重启服务后自动注册，无需改 `main.py`

## 变更记录

- 2026-03-30
  - 基于近期架构与 Memory 模块沟通，完整重构 README：更新项目介绍、分层职责、依赖配置、接口说明、质量门禁与 Memory 进展
  - 统一命名：`core/memory_rag/embedding/gateway.py` 对外实例命名为 `embedding_gateway`，并同步更新 RAG、Memory、ToolRouter、向量存储与就绪检查引用

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
