# Agent Platform 架构探索项目

本项目是关于 Agent 平台架构演进的探索与实践，旨在对比和验证不同架构模式下的系统设计与工程实现。项目中包含了两种典型架构的完整实现：**单体架构（Monolithic）** 与 **服务拆分架构（Microservices/Multi-repo）**。

## 项目架构介绍

本项目包含两个主要的子目录，分别对应两种不同的架构设计：

### 1. 单体架构 (agent-platform-mono)
位于 `agent-platform-mono/` 目录下，采用传统的单体应用架构设计。所有的核心模块和业务领域都集中在一个代码库和进程中运行。

#### 代码目录结构
```text
agent-platform-mono/
├── apps/                         # 业务域 (原 domains)
│   ├── policy/                   # 示例：保单域
│   │   ├── register.py           # 域注册入口 (注册到 AgentRegistry)
│   │   ├── policy_agent.py       # (可选) 自定义 LangGraph workflow
│   │   ├── memory_config.py      # (可选) 覆盖全局 Memory 策略
│   │   ├── tools/                # MCP Tools
│   │   └── prompts/              # System Prompts
│   ├── claim/                    # 示例：理赔域
│   └── customer/                 # 示例：客服域
├── core/                         # 核心平台服务层
│   ├── agent_engine/             # Agent 编排层 (LangGraph, 注册表)
│   ├── ai_core/                  # AI 能力层 (LLM, Prompts, 路由)
│   ├── memory_rag/               # 数据智能层 (记忆, 知识库)
│   └── tool_service/             # Tool 服务层 (MCP 客户端等)
├── shared/                       # 共享基础组件 (无业务逻辑)
│   ├── config/                   # 配置管理
│   ├── middleware/               # FastAPI 中间件
│   ├── models/                   # 公共数据模型
│   └── logging/                  # 统一日志
├── tests/                        # 单元测试与集成测试
└── main.py                       # FastAPI 入口
```

### 2. 服务拆分架构 (agent-platform-repos)
位于 `agent-platform-repos/` 目录下，采用微服务架构设计，将不同领域的职责拆分为独立的服务，各服务可通过 API 或消息队列进行通信。

**主要服务包括：**
- `agent-service/`: 负责 Agent 编排与执行的独立服务。
- `ai-core-service/`: 独立的大模型网关与核心调度服务。
- `mcp-service/`: 独立的 MCP 协议服务，提供标准化的工具和上下文访问能力。
- `memory-rag-service/`: 独立的记忆与知识库检索引擎服务。
- `shared-lib/`: 提取出的公共依赖库，供各独立服务引入使用。

## 项目依赖与配置

两个架构实现均基于 Python 生态构建。
- **依赖管理**: 使用 `pyproject.toml` 进行依赖管理。
- **环境配置**: 各项目及服务均提供 `.env.example` 模板文件，运行时需复制为 `.env` 并配置相应的环境变量（如 LLM API Key、数据库连接、Redis/Nacos 配置等）。
- **容器化部署**: 提供了 `Dockerfile` 和 `docker-compose.yml` (或 `docker-compose.dev.yml`) 文件，支持一键式容器化启动和本地开发环境搭建。

## 项目使用说明

### 单体架构运行
1. 进入单体项目目录：`cd agent-platform-mono`
2. 复制配置文件：`cp .env.example .env` 并完善配置。
3. 安装依赖：`pip install -e .` (或使用 poetry/uv 等工具)。
4. 启动服务：执行 `main.py` 或使用 `docker-compose up -d` 启动。

### 服务拆分架构运行
1. 进入服务拆分项目目录：`cd agent-platform-repos`
2. 各个微服务独立运行。进入对应服务目录（如 `agent-service`），复制并修改 `.env` 文件。
3. 在根目录下可以使用 Docker Compose 统一启动所有服务：`docker-compose up -d`。

## 变更记录

- **[2026-03-23]** 采用 V2 版本的服务拆分实现（直接替换原 `agent-platform-repos`）：引入了更加标准化的微服务应用工厂和 `ReadinessRegistry`，全面支持 K8s 语意的 liveness/readiness 探针及统一异常处理。
- **[2026-03-23]** 重构服务拆分架构：在 `shared-lib` 中封装了 FastAPI 的通用工厂方法 `create_base_app`，统一了微服务的存活（liveness）和就绪（readiness）健康检查机制。
- **[2026-03-23]** 清理项目中已经生成的 `.DS_Store` 文件。
- **[2026-03-23]** 初始化整体项目 README 文档：说明了单体架构和服务拆分架构两套探索方案。
