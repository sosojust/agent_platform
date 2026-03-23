# Agent Platform 架构探索项目

本项目是关于 Agent 平台架构演进的探索与实践，旨在对比和验证不同架构模式下的系统设计与工程实现。项目中包含了两种典型架构的完整实现：**单体架构（Monolithic）** 与 **服务拆分架构（Microservices/Multi-repo）**。

## 项目架构介绍

本项目包含两个主要的子目录，分别对应两种不同的架构设计：

### 1. 单体架构 (agent-platform-mono)
位于 `agent-platform-mono/` 目录下，采用传统的单体应用架构设计。所有的核心模块和业务领域都集中在一个代码库和进程中运行。

**主要模块包括：**
- `agent_service/`: Agent 的核心服务引擎，负责 Agent 的注册与执行。
- `ai_core/`: 大语言模型（LLM）交互、Prompt 管理及路由核心模块。
- `domains/`: 具体业务领域实现（如理赔 `claim`、客户服务 `customer`、保单 `policy` 等）。
- `mcp_server/`: MCP (Model Context Protocol) 协议服务端实现。
- `memory_rag/`: 记忆管理与 RAG（检索增强生成）系统，包含向量存储与重排。
- `shared/`: 公共基础组件（配置、日志、中间件、模型等）。

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

- **[2026-03-23]** 初始化整体项目 README 文档：说明了单体架构和服务拆分架构两套探索方案。
