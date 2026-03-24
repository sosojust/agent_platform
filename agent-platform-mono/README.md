# Agent Platform

团险业务 Agent Platform，单一 Python 服务，FastAPI + LangGraph 实现。

---

## 目录结构总览

```
agent-platform/
│
├── main.py                        # FastAPI 启动入口，lifespan 自动扫描注册所有域
├── pyproject.toml                 # 依赖管理（Python 3.11+）
├── .env.example                   # 环境变量模板
├── Dockerfile                     # 生产镜像
├── docker-compose.dev.yml         # 本地开发基础设施（Milvus/Redis/Langfuse 等）
│
├── shared/                        # 跨所有模块的公共基础设施，不含业务逻辑
│   ├── config/
│   │   ├── settings.py            # 所有环境变量统一定义（pydantic-settings），全局单例
│   │   └── nacos.py               # Nacos 配置接入，动态参数热更新
│   ├── logging/
│   │   └── logger.py              # structlog JSON 结构化日志，自动携带 tenant_id/trace_id
│   ├── middleware/
│   │   └── tenant.py              # 从 Header 提取 X-Tenant-Id，注入 contextvars
│   └── models/
│       └── schemas.py             # 跨层公用 Pydantic 模型（请求/响应/事件）
│
├── core/                          # 核心平台服务层
│   ├── ai_core/                   # AI 能力层 (大模型与 Prompt)
│   │   ├── llm/
│   │   │   └── client.py          # LiteLLM 统一封装，Langfuse 上报
│   │   ├── prompt/
│   │   │   └── manager.py         # Prompt 统一管理 (Langfuse 拉取/本地兜底)
│   │   └── routing/
│   │       └── router.py          # 模型路由 (大小模型、本地模型切换)
│   │
│   ├── memory_rag/                # 数据智能层 (记忆与知识库)
│   │   ├── embedding/
│   │   │   └── service.py         # bge-m3 本地 Embedding
│   │   ├── rerank/
│   │   │   └── service.py         # bge-reranker 本地精排
│   │   ├── vector/
│   │   │   └── store.py           # Milvus 向量库操作
│   │   ├── memory/
│   │   │   ├── manager.py         # 长期/短期记忆管理 (mem0/redis)
│   │   │   └── config.py          # 各域记忆策略配置基类
│   │   └── rag/
│   │       └── pipeline.py        # 统一 RAG 流程
│   │
│   ├── tool_service/              # MCP 工具服务层 (与业务系统对接)
│   │   └── client/
│   │       └── gateway.py         # 统一网关客户端 (带鉴权和租户头)
│   │
│   └── agent_engine/              # 核心编排框架层 (LangGraph)
│       ├── agents/
│       │   └── registry.py        # 全局 Agent 注册表
│       ├── workflows/
│       │   └── base_agent.py      # 可复用的基础 LangGraph Graph
│       └── checkpoints/
│           └── redis_checkpoint.py# 中断恢复与 Human-in-the-loop
│
├── apps/                       # 业务域：每个域自成体系，对框架层零侵入
│   ├── __init__.py                # 域自动发现入口
│   │
│   ├── policy/                    # 保单域
│   │   ├── register.py            # 域注册入口：声明 Agent、Tools、Memory 策略
│   │   ├── policy_agent.py        # 保单专属 LangGraph workflow
│   │   ├── memory_config.py       # 保单域 Memory 策略（短平快，不需要长期记忆）
│   │   ├── tools/
│   │   │   ├── policy_tools.py    # 保单查询、列表等 MCP tools
│   │   │   └── underwrite_tools.py# 核保相关 MCP tools
│   │   └── prompts/
│   │       └── system.txt         # 保单域 system prompt 模板
│   │
│   ├── claim/                     # 理赔域
│   │   ├── register.py
│   │   ├── claim_agent.py         # 理赔专属 workflow（多步骤，需要文档核验）
│   │   ├── memory_config.py       # 理赔域 Memory 策略（长期记忆，保留完整理赔历史）
│   │   ├── tools/
│   │   │   ├── claim_tools.py     # 理赔状态查询、申请提交等 MCP tools
│   │   │   └── doc_verify_tools.py# 材料核验 MCP tools
│   │   └── prompts/
│   │       └── system.txt
│   │
│   └── customer/                  # 客服域
│       ├── register.py
│       ├── customer_agent.py      # 客服专属 workflow（FAQ 优先，兜底人工转接）
│       ├── memory_config.py       # 客服域 Memory 策略（中等，记录偏好和历史问题）
│       ├── tools/
│       │   ├── customer_tools.py  # 客户信息查询 MCP tools
│       │   └── faq_tools.py       # FAQ 检索 MCP tools
│       └── prompts/
│           └── system.txt
│
└── tests/                         # 测试，与 src 目录结构镜像
    ├── shared/
    ├── core.ai_core/
    ├── core.memory_rag/
    ├── core.tool_service/
    ├── core.agent_engine/
    └── apps/
        ├── test_policy.py
        ├── test_claim.py
        └── test_customer.py
```

---

## 模块职责说明

### shared/ — 基础设施层
不含任何业务逻辑。所有模块都可以 import，但 shared 本身不 import 任何业务模块。

| 文件 | 职责 |
|------|------|
| `config/settings.py` | pydantic-settings 统一管理所有环境变量，启动时校验，缺少必填项直接报错 |
| `config/nacos.py` | 接入 Nacos，热更新动态参数（模型路由策略、RAG 阈值、功能开关等） |
| `logging/logger.py` | structlog，输出 JSON，自动携带 tenant_id / trace_id，生产日志直接采集 |
| `middleware/tenant.py` | 从 X-Tenant-Id Header 提取租户信息，写入 contextvars，全链路可读 |
| `models/schemas.py` | AgentRunRequest / AgentRunResponse / StreamEvent 等跨层公用模型 |

### core/ai_core/ — AI 能力层
只关心"怎么调 LLM"，不关心"做什么业务"。

| 文件 | 职责 |
|------|------|
| `llm/client.py` | LiteLLM 封装，支持 OpenAI / Anthropic / 本地模型，自动上报 Langfuse |
| `prompt/manager.py` | 从 Langfuse 拉取版本化 Prompt，降级时用本地 fallback |
| `routing/router.py` | 按 task_type 选模型：simple→小模型省钱，complex→强模型，local→敏感数据不出网 |

### core/memory_rag/ — 数据智能层
只关心"怎么存取记忆和知识"，不关心"哪个业务用"。

| 文件 | 职责 |
|------|------|
| `embedding/service.py` | bge-m3 本地推理单例，懒加载，批量 encode |
| `rerank/service.py` | bge-reranker 本地精排，召回 top-20 → 精排 top-5 |
| `vector/store.py` | Milvus 操作，collection 按 `{tenant_id}_{type}` 命名隔离 |
| `memory/manager.py` | 短期记忆(Redis TTL) + 长期记忆(mem0自动压缩) |
| `memory/config.py` | MemoryConfig 数据类，各域覆盖 top_k / 阈值 / 是否启用长期记忆 |
| `rag/pipeline.py` | 查询改写 → 向量召回 → rerank，接收 MemoryConfig 参数 |

### core/tool_service/ — MCP 协议层
只关心"怎么和内网业务系统通信"。

| 文件 | 职责 |
|------|------|
| `client/gateway.py` | httpx 异步客户端，自动注入 tenant header，tenacity 重试，统一错误日志 |

### core/agent_engine/ — 编排框架层
只关心"LangGraph 的基础结构"，不关心具体业务流程。

| 文件 | 职责 |
|------|------|
| `agents/registry.py` | AgentMeta 注册表，启动时由各域 register.py 填充，运行时按 agent_id 查找 |
| `workflows/base_agent.py` | 可复用的基础 Graph（记忆拉取→RAG→推理→工具→记忆写回），各域继承后扩展节点 |
| `checkpoints/redis_checkpoint.py` | Redis Saver，支持 Human-in-the-loop 和中断恢复 |

### apps/ — 业务域层
**新增业务场景只需要在这里加目录，框架层不动。**

每个域包含：
- `register.py`：域的唯一对外入口，声明 agent_id、tools、memory_config
- `*_agent.py`：继承 base_agent 或自定义 LangGraph workflow
- `memory_config.py`：覆盖该域的记忆和 RAG 参数
- `tools/`：该域专属的 MCP tools，调用 gateway_client
- `prompts/`：该域专属的 system prompt 文本

---

## 快速启动

```bash
# 1. 启动本地基础设施
docker compose -f docker-compose.dev.yml up -d

# 2. 安装依赖
pip install -e ".[dev]"

# 3. 配置环境变量
cp .env.example .env

# 4. 启动服务
uvicorn main:app --reload --port 8000

# 5. 查看 API 文档
open http://localhost:8000/docs
```

---

## 新增业务域（标准流程）

以新增"核保域"为例：

```bash
# 1. 创建目录结构
mkdir -p apps/underwriting/{tools,prompts}

# 2. 实现以下文件
# apps/underwriting/register.py       ← 必须
# apps/underwriting/underwriting_agent.py
# apps/underwriting/memory_config.py
# apps/underwriting/tools/underwrite_tools.py
# apps/underwriting/prompts/system.txt

# 3. 重启服务，框架自动发现并注册
# 无需修改 main.py 或任何框架层代码
```
