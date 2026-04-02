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
