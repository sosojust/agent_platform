# Agent Platform — 多仓库微服务架构

5 个独立 Git 仓库，各自独立部署，通过 HTTP 互调。

```
agent-platform-repos/
├── shared-lib/            独立 Python 包，其余 4 个服务通过 pip 安装
├── agent-service/         编排层，port 8001
├── ai-core-service/       AI 能力层，port 8002
├── memory-rag-service/    数据智能层，port 8003
├── mcp-service/           业务能力层，port 8004
└── docker-compose.yml     本地一键启动（开发用）
```

---

## 服务职责与端口

| 服务 | 端口 | 核心职责 | 关键依赖 |
|------|------|----------|----------|
| agent-service | 8001 | LangGraph 编排，SSE 流式输出 | ai-core / memory-rag / mcp |
| ai-core-service | 8002 | LLM 调用，Prompt 管理，模型路由 | LiteLLM, Langfuse |
| memory-rag-service | 8003 | 向量检索，记忆管理，Embedding/Rerank | Milvus, Redis, bge 模型 |
| mcp-service | 8004 | 业务 MCP tools，调用内网 Gateway | Spring Cloud Gateway |

---

## 服务间调用关系

```
客户端
  ↓ SSE / HTTP
Spring Cloud Gateway（Java，对外）
  ↓ HTTP
agent-service :8001
  ├─→ ai-core-service :8002      LLM 推理（HTTP streaming / NDJSON）
  ├─→ memory-rag-service :8003   RAG 检索 + 记忆读写（普通 HTTP）
  └─→ mcp-service :8004          MCP tool 调用（普通 HTTP）
       ↓ HTTP
      Spring Cloud Gateway（Java，内网）
       ↓
      团险业务微服务（保单 / 理赔 / 客户 / 核保）
```

---

## 各仓库文件结构

### shared-lib/
```
shared-lib/
├── pyproject.toml                      包名：agent-platform-shared
└── agent_platform_shared/
    ├── config/
    │   ├── settings_base.py            各服务继承的基础 Settings
    │   └── nacos.py                    Nacos 动态配置接入
    ├── logging/logger.py               structlog JSON 日志
    ├── middleware/tenant.py            上下文四元透传 → contextvars（tenant/conversation/thread/trace）
    └── models/schemas.py               跨服务公用 Pydantic 模型（使用 conversation_id）
```

### agent-service/
```
agent-service/
├── main.py                             FastAPI 入口，SSE /agent/stream
├── pyproject.toml
├── Dockerfile
├── .env.example
├── config/settings.py                  下游服务 URL 配置
├── agents/registry.py                  AgentMeta 注册表
├── workflows/base_agent.py             LangGraph Graph，通过 HTTP client 调其他服务
├── checkpoints/redis_checkpoint.py     LangGraph Redis Checkpoint
├── clients/
│   ├── ai_core_client.py               → ai-core-service（含 stream() 方法）
│   ├── memory_rag_client.py            → memory-rag-service
│   └── mcp_client.py                   → mcp-service
├── domains/
│   ├── policy/register.py              保单域：tool_names / RAG 参数 / factory
│   ├── claim/register.py               理赔域
│   └── customer/register.py            客服域
└── tests/test_agent_api.py
```

### ai-core-service/
```
ai-core-service/
├── main.py                             POST /llm/complete + POST /llm/stream
├── pyproject.toml
├── Dockerfile
├── .env.example
├── config/settings.py
├── llm/client.py                       LiteLLM，stream() 逐 token yield
├── prompt/manager.py                   Langfuse Prompt 版本管理
├── routing/router.py                   simple / complex / local 三档路由
└── tests/test_llm.py
```

### memory-rag-service/
```
memory-rag-service/
├── main.py                             POST /rag/retrieve /memory/* /embedding/embed
├── pyproject.toml
├── Dockerfile
├── .env.example
├── config/settings.py
├── embedding/service.py                本地 bge-m3，进程内推理
├── rerank/service.py                   本地 bge-reranker，精排
├── vector/store.py                     Milvus，按 tenant 隔离 collection
├── memory/manager.py                   Redis 短期 + mem0 长期双层记忆
├── rag/pipeline.py                     查询改写 → 召回 → rerank
└── tests/
```

### mcp-service/
```
mcp-service/
├── main.py                             POST /tools/call  GET /tools/list
├── pyproject.toml
├── Dockerfile
├── .env.example
├── config/settings.py
├── client/gateway.py                   → Spring Cloud Gateway，带重试
├── tools/
│   ├── policy_tools.py                 保单 MCP tools
│   ├── claim_tools.py                  理赔 MCP tools
│   └── customer_tools.py              客服 MCP tools
└── tests/
```

---

## 本地开发启动

```bash
# 1. 配置环境变量（根目录创建 .env）
cp agent-service/.env.example .env.agent
# 各服务 .env.example 分别配置，或统一写根目录 .env

# 2. 一键启动所有服务 + 基础设施
OPENAI_API_KEY=sk-xxx docker compose up -d

# 3. 检查服务健康
curl http://localhost:8001/health   # agent-service
curl http://localhost:8002/health   # ai-core-service
curl http://localhost:8003/health   # memory-rag-service
curl http://localhost:8004/health   # mcp-service

# 4. 测试 Agent 调用
curl -X POST http://localhost:8001/agent/run \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: tenant_001" \
  -H "X-Conversation-Id: conv_demo_001" \
  -d '{"agent_id": "policy-assistant", "input": "查询保单 P2024001"}'

# 5. 测试 SSE 流式输出
curl -N http://localhost:8001/agent/stream \
  -X POST \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: tenant_001" \
  -H "X-Conversation-Id: conv_demo_002" \
  -d '{"agent_id": "claim-assistant", "input": "我的理赔 C2024001 进展如何？"}'

---

## 上下文四元透传规范（必读）
- 透传元素：
  - X-Tenant-Id：租户标识
  - X-Conversation-Id：业务会话ID（跨多请求稳定标识同一对话）
  - X-Thread-Id：执行线程ID（默认等于 Conversation；并行/子Agent可派生命名）
  - X-Trace-Id：链路追踪ID（单请求唯一）
- 透传机制：
  - 每个服务入站由 shared-lib/middleware/tenant.py 读取 Header 注入 contextvars，并绑定到 structlog
  - 出站 HTTP 客户端自动注入四元 Header；如存在用户令牌，将透传 `X-User-Token`
- 命名建议：
  - 共享线程：thread_id = conversation_id
  - 命名空间：thread_id = f"{conversation_id}:{agent_id}"
  - 并行分叉：thread_id = f"{conversation_id}#{短随机}"

---

## 跨服务字段统一（重要）
- 请求/响应字段
  - AgentRunRequest.conversation_id（可选）取代 session_id
  - AgentRunResponse.conversation_id（必有）
  - MemoryGetRequest.conversation_id、MemoryAppendRequest.conversation_id
- 日志字段
  - 全链路统一记录：tenant_id、conversation_id、thread_id、trace_id
- 兼容性
  - 代码已全面切换为 conversation_id；如需兼容旧调用，请在网关层进行字段映射或增加适配层
```

---

## 新增业务域（标准流程）

以新增"核保域"为例：

```bash
# 1. 在 mcp-service 添加 tool
vi mcp-service/tools/underwriting_tools.py   # 实现 @mcp.tool() 函数
vi mcp-service/main.py                       # 在 ALL_TOOLS 中加入 underwriting_tools

# 2. 在 agent-service 添加域注册
mkdir -p agent-service/domains/underwriting
vi agent-service/domains/underwriting/register.py  # 声明 agent_id / tool_names / factory

# 3. 重启两个服务，其余服务不动
docker compose restart mcp-service agent-service
```

---

## 各服务独立测试

```bash
cd ai-core-service && pip install -e ".[dev]" && pytest
cd memory-rag-service && pip install -e ".[dev]" && pytest
cd mcp-service && pip install -e ".[dev]" && pytest
cd agent-service && pip install -e ".[dev]" && pytest
```
