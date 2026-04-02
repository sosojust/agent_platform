# 架构重构记录

本目录记录了项目的重要架构重构，包括问题分析、解决方案和实施细节。

## 重构列表

### 1. Embedding Layer 清理 (2026-04-02)

**文档**: [embedding_layer_cleanup.md](./embedding_layer_cleanup.md)

**问题**: `core/ai_core/embedding` 和 `core/memory_rag/embedding` 职责重叠，`memory_rag/embedding/gateway.py` 是一个没有价值的 4 行代码中间层。

**解决方案**: 删除 `memory_rag/embedding/gateway.py`，让所有调用方直接使用 `ai_core/embedding/provider.py` 的单例。

**影响范围**:
- 删除 1 个文件
- 修改 5 个文件
- 新增 1 个 `__init__.py`

**架构改进**:
- 消除无意义的中间层
- 明确职责边界：AI 能力在 `ai_core`，业务逻辑在 `memory_rag`
- 符合分层架构原则

---

### 2. Tool Service Client 层清理 (2026-04-02)

**文档**: [tool_service_client_cleanup.md](./tool_service_client_cleanup.md)

**问题**: `core/tool_service/client` 层职责定位不清晰，在当前 MCP 架构下不应该存在直接调用内部 API 的层。

**解决方案**: 
- 删除 `core/tool_service/client` 目录
- 创建 `shared/internal_http/client` 作为内部服务 HTTP 客户端
- 更新所有 `domain_agents` 工具使用新的客户端

**影响范围**:
- 删除 1 个目录（2 个文件）
- 新增 2 个文件（`shared/internal_http/client.py` 和 `__init__.py`）
- 修改 6 个文件（3 个 domain tools + lifespan + 2 个测试）

**架构改进**:
- 职责更清晰：内部 HTTP 客户端在 `shared/internal_http` 基础设施层
- 命名更明确：`internal_http` 清楚表明用于内部服务调用
- 可复用性更好：任何模块都可以使用
- 符合分层架构：基础设施层 → 业务层
- 上下文传递更完善：自动注入所有上下文信息

---

### 3. MCP Client 重命名和改进 (2026-04-02)

**文档**: [mcp_client_rename.md](./mcp_client_rename.md)

**问题**: MCP 客户端命名不够明确，内部客户端缺少完整的上下文透传。

**解决方案**:
- 重命名 `service_client.py` → `internal_client.py`
- 重命名类 `MCPServiceProvider` → `InternalMCPClient`
- 重命名类 `ExternalMCPProvider` → `ExternalMCPClient`
- 改进 `InternalMCPClient` 透传完整上下文信息

**影响范围**:
- 删除 1 个文件（`service_client.py`）
- 新增 1 个文件（`internal_client.py`）
- 修改 3 个文件（`external_client.py`, `__init__.py`, `lifespan.py`）

**架构改进**:
- 命名对称：`InternalMCPClient` vs `ExternalMCPClient`
- 上下文完整：内部客户端透传所有上下文字段
- 职责清晰：内部服务 vs 外部服务器
- 与 `shared/internal_http` 保持一致的上下文透传策略

---

## 重构原则

1. **单一职责**: 每个模块只做一件事
2. **分层清晰**: 基础设施层、能力层、业务层职责明确
3. **避免重复**: 消除无意义的中间层和重复代码
4. **易于测试**: 使用单例模式和依赖注入便于 mock
5. **向后兼容**: 尽量保持 API 兼容，减少影响范围

## 重构流程

1. **问题识别**: 发现架构问题或代码异味
2. **方案设计**: 设计解决方案，评估影响范围
3. **实施重构**: 
   - 创建新代码
   - 更新调用方
   - 删除旧代码
4. **验证测试**: 运行测试确保功能正常
5. **文档记录**: 记录重构过程和决策

## 待重构项

查看 [docs/tasks/batch1_review.md](../tasks/batch1_review.md) 了解待处理的架构问题。

### 4. 工具组织架构改进 (2026-04-02)

**文档**: [tool_organization.md](./tool_organization.md)

**问题**: 
1. domain_agents 中没有 skills 目录，无法存放简单的函数式工具
2. 缺少公共工具的统一存放位置，导致工具重复实现

**解决方案**:
- 在每个 domain_agents 下添加 `skills/` 目录
- 创建顶层 `common_tools/` 目录存放公共工具
- 明确工具分类规则

**影响范围**:
- 新增 3 个 domain skills 目录
- 新增 1 个 common_tools 目录（包含 mcp/ 和 skills/）
- 新增示例工具和文档

**架构改进**:
- 工具分类清晰：MCP vs Skill，领域 vs 公共
- 易于复用：公共工具统一管理
- 避免重复：跨领域工具只实现一次
- 结构完整：每个层次都有明确的工具存放位置

---

### 5. 工具位置和注册机制澄清 (2026-04-02)

**文档**: [tool_location_and_registration.md](./tool_location_and_registration.md)

**问题**:
1. common_tools 最初放在顶层，但应该放在 core/tool_service/ 下更合适
2. 文档中提到需要"注册"工具，但实际上工具通过装饰器自动注册

**解决方案**:
- 将 `common_tools/` 移动到 `core/tool_service/common_tools/`
- 澄清工具注册机制：装饰器自动注册，导入即可用

**影响范围**:
- 移动 1 个目录
- 更新所有文档中的路径引用
- 澄清注册机制说明

**架构改进**:
- 目录结构更清晰：工具相关模块统一在 tool_service 下
- 职责划分明确：基础设施 vs 工具实现
- 开发体验更好：装饰器自动注册，无需手动调用

---

### 6. 删除未使用的 MCP 客户端 (2026-04-02)

**文档**: [remove_unused_mcp_clients.md](./remove_unused_mcp_clients.md)

**问题**:
- `InternalMCPClient` 和 `ExternalMCPClient` 在当前架构中完全未使用
- 所有工具都直接在 domain_agents 中定义，通过装饰器自动注册
- 不存在独立的 mcp-service，也没有接入外部 MCP 服务器

**解决方案**:
- 删除 `internal_client.py` 和 `external_client.py`
- 保留 `base.py` 作为接口定义，供未来扩展
- 更新 lifespan.py，删除未使用的注册代码

**影响范围**:
- 删除 2 个文件（约 200+ 行代码）
- 修改 3 个文件（`__init__.py`, `base.py`, `lifespan.py`）

**架构改进**:
- 代码更简洁：删除未使用的代码
- 架构更清晰：工具直接定义，装饰器自动注册
- 符合 YAGNI 原则：不实现当前用不到的功能
- 维护成本更低：减少需要维护和测试的代码

---
