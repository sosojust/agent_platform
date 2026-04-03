# 架构文档

本目录包含系统的架构设计文档。

## 文档列表

### 1. [Tool Service 架构](./tool_service_architecture.md)

**主题**: 工具服务的架构设计和职责划分

**核心要点**:
- `core/tool_service/` 是基础设施层，只提供工具注册、发现、调用能力
- `domain_agents/*/tools/` 是业务层，包含具体的业务工具实现
- 支持 MCP 和 Skill 两种工具类型
- 内部/外部 MCP 客户端分离

**适用场景**:
- 添加新的业务工具
- 集成外部 MCP 服务器
- 理解工具调用流程

---

### 2. [PDF 解析设计](./pdf_parsing_design.md)

**主题**: PDF 文档解析和处理的设计方案

---

## 架构原则

### 1. 分层架构

```
┌─────────────────────────────────────┐
│     domain_agents/ (业务层)         │
│  - 业务工具实现                      │
│  - 领域知识                          │
│  - Agent 定义                        │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│     core/ (核心能力层)               │
│  - agent_engine: Agent 引擎          │
│  - tool_service: 工具服务            │
│  - ai_core: AI 能力                  │
│  - memory_rag: 记忆和 RAG            │
└─────────────────────────────────────┐
              ↓
┌─────────────────────────────────────┐
│     shared/ (基础设施层)             │
│  - config: 配置管理                  │
│  - logging: 日志                     │
│  - middleware: 中间件                │
│  - internal_http: 内部 HTTP 客户端   │
│  - i18n: 国际化                      │
└─────────────────────────────────────┘
```

### 2. 职责分离

- **基础设施层** (`shared/`): 提供通用能力，不包含业务逻辑
- **核心能力层** (`core/`): 提供 AI、工具、记忆等核心能力，与具体业务无关
- **业务层** (`domain_agents/`): 实现具体的业务逻辑和工具

### 3. 依赖方向

- 业务层 → 核心能力层 → 基础设施层
- 禁止反向依赖
- 同层之间尽量避免依赖

### 4. 上下文传递

所有内部服务调用都应该透传上下文信息：
- 租户信息（X-Tenant-Id）
- 追踪信息（X-Trace-Id）
- 会话信息（X-Conversation-Id）
- 用户信息（X-User-Id）
- 等等

**实现方式**:
- HTTP 调用：使用 `shared/internal_http/client.py`
- MCP 调用：使用 `core/tool_service/internal_mcp/client.py`

### 5. 配置管理

- 使用 Pydantic Settings 管理配置
- 支持环境变量覆盖
- 支持 Nacos 动态配置
- 配置集中在 `shared/config/settings.py`

### 6. 错误处理

- 使用结构化日志记录错误
- 返回友好的错误信息给用户
- 不暴露内部实现细节
- 支持错误追踪（trace_id）

### 7. 测试策略

- 单元测试：测试单个函数/类
- 集成测试：测试模块间交互
- Mock 外部依赖（HTTP、数据库等）
- 测试文件与源文件对应

## 模块说明

### core/agent_engine
Agent 执行引擎，基于 LangGraph 实现。

### core/tool_service
工具服务基础设施，提供工具注册、发现、调用能力。

### core/ai_core
AI 核心能力：
- LLM 客户端
- Embedding 提供者
- Prompt 管理

### core/memory_rag
记忆和 RAG 能力：
- 短期记忆（Redis）
- 长期记忆（向量数据库）
- RAG 检索
- Rerank

### shared/internal_http
内部服务 HTTP 客户端，自动透传上下文。

### shared/middleware
中间件：
- 租户识别
- 上下文管理
- 请求追踪

### shared/i18n
国际化支持：
- 多语言翻译
- 时区处理
- 区域设置

### domain_agents
业务领域 Agent：
- policy: 保单域
- claim: 理赔域
- customer: 客服域

## 开发指南

### 添加新的业务工具

1. 在 `domain_agents/` 下创建新的领域目录
2. 使用 FastMCP 定义工具
3. 在 `register.py` 中注册 Agent
4. 编写测试

### 添加新的核心能力

1. 在 `core/` 下创建新的模块
2. 定义清晰的接口
3. 提供单例或工厂函数
4. 编写文档和测试

### 添加新的基础设施

1. 在 `shared/` 下创建新的模块
2. 确保通用性，不包含业务逻辑
3. 提供清晰的 API
4. 编写文档和测试

## 参考资料

- [重构记录](../refactoring/README.md)
- [任务列表](../tasks/README.md)
