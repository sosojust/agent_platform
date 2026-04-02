# Tool Service 架构变更日志

> 记录 Tool Service 架构设计的所有重要变更

---

## v1.0 - 2026-04-02：Skill 执行边界规范

### 新增文档

- `skill_execution_boundaries.md`：Skill 执行边界和约束规范

### 核心内容

定义了 Skill 作为工具层概念的五大边界：

1. **执行边界**
   - 禁止 Skill 嵌套调用（只能调用 Tool）
   - max_steps 默认 5，远低于主 Agent 的 12
   - timeout_seconds 默认 30，超时直接抛异常

2. **治理归属**
   - step_count、token 消耗、延迟单独计量
   - SkillToolMetadata 包含 estimated_cost 提示字段
   - 调用方能在调用前知道"这是 LLM 驱动的工具"

3. **观测边界**
   - Skill 内部每次工具调用作为子事件上报
   - 返回结果包含 tool_calls 列表（工具、顺序、结果摘要）
   - 集成 OpenTelemetry 分布式追踪

4. **上下文隔离边界**
   - Skill 不继承主 Agent 的 messages 历史
   - 只接收 Skill 的输入参数和渲染后的 prompt
   - 防止上下文窗口双倍膨胀和隐私信息泄露

5. **降级边界**
   - 返回统一的 SkillExecutionResult 结构
   - 包含 status: success/error/timeout
   - 主 Agent 可根据 status 决定重试或降级策略

### 影响

- Skill 成为真正受限的、可预测的、可计量的工具
- 防止 Skill 失控（递归、超时、成本爆炸）
- 提供完整的可观测性和降级能力

---

## v6.4 - 2026-04-02：架构问题修正

### 修正的问题

1. **health_check 实现有误导性**
   - 问题：`len(tools) >= 0` 永远为 True
   - 修正：改为 `len(tools) > 0` 或 ping 服务端点
   - 影响：健康检查现在能正确反映服务状态

2. **External MCP 工具缓存只在内存里**
   - 问题：实例级内存缓存，服务重启后丢失
   - 修正：添加 TTL、刷新机制、Redis 共享缓存方案
   - 影响：支持多实例部署，缓存更可靠

3. **SkillDefinition 和 ToolMetadata 数据结构不一致**
   - 问题：两套数据结构，Skill 定义只在 Adapter 实例里
   - 修正：统一使用 SkillToolMetadata，支持持久化存储
   - 影响：多实例部署时数据一致，支持动态更新

### 新增文档

- `tool_service_architecture_fixes.md`：详细的问题分析和修正方案

### 修改的文档

- `tool_service_final_design.md`：
  - 添加已知问题说明
  - 添加常见问题章节
  - 引用修正方案文档

---

## v6.3 - 2026-04-02：LLM Gateway 使用修正

### 修正的问题

1. **SkillExecutor 中 llm_gateway.get_chat() 的 scene 参数使用错误**
   - 问题：把 `llm_config` 中的 `model` 当作 `scene` 传入
   - 修正：使用业务语义场景名（如 "skill_execution"）
   - 影响：LLM 路由现在能正确工作

### 新增内容

- 在文档开头添加重要说明
- 添加 LLM Gateway 使用问题章节
- 提供正确和错误的示例对比

---

## v6.2 - 2026-04-01：代码复用修正

### 修正的问题

1. **InternalMCPAdapter 重复实现问题**
   - 问题：InternalMCPAdapter 重复实现了 HTTP 调用逻辑
   - 修正：委托给 InternalHTTPClient 执行
   - 影响：遵循 DRY 原则，代码更简洁

---

## v6.1 - 2026-04-01：权限策略优化

### 优化内容

1. **权限检查策略优化**
   - 默认策略改为 LOCAL_ONLY（性能优先）
   - 远程检查失败时降级到本地规则（可用性优先）
   - 添加权限结果缓存（减少远程调用）

---

## v6.0 - 2026-03-31：目录结构重构

### 重大变更

1. **采用按工具类型划分的目录结构（方案 B）**
   - 每个工具类型是独立的包
   - Base 层提供通用能力
   - 清晰的边界和职责划分

---

## v5.0 - 2026-03-30：Skill 执行模型深度解析

### 新增内容

1. **深度解析 Skill 执行模型**
   - 明确 Skill 是 LLM 驱动的
   - 详细说明执行流程
   - 区分 Tool 和 Skill

2. **MCP/HTTP Adapter 澄清**
   - External MCP：对接外部 MCP Server
   - Internal MCP：HTTP Client + MCP 协议封装

---

## 文档结构

```
docs/architecture/
├── tool_service_final_design.md          # 主设计文档（v6.3）
├── tool_service_architecture_fixes.md    # 架构问题修正（v6.4）
├── skill_execution_boundaries.md         # Skill 执行边界规范（v1.0）⭐ 新增
├── tool_service_changelog.md             # 变更日志（本文档）
├── tool_service_quick_reference.md       # 快速参考
├── tool_service_updates_v5.md            # v5 更新说明
├── tool_service_updates_v6.md            # v6 更新说明
├── tool_service_metadata_fix.md          # Metadata 类型修正
├── tool_service_code_reuse_fix.md        # 代码复用修正
├── tool_service_permission_optimization.md  # 权限优化
└── skill_concept_clarification.md        # Skill 概念澄清
```

---

## 待办事项

### 高优先级

- [ ] 实现 Skill 执行边界约束（五大边界）⭐ 新增
- [ ] 实现 health_check 修正
- [ ] 实现 External MCP 缓存刷新机制
- [ ] 实现 Skill 持久化存储

### 中优先级

- [ ] 实现 SkillExecutionResult 统一返回结构
- [ ] 集成 OpenTelemetry 分布式追踪
- [ ] 添加 Skill 成本预估和提示
- [ ] 添加工具版本管理
- [ ] 实现工具组合（Skill 调用 Skill - 需要重新评估）
- [ ] 添加详细的健康检查接口

### 低优先级

- [ ] 工具市场功能
- [ ] 工具使用统计
- [ ] 工具性能监控

---

**文档维护者**：Agent Platform Team  
**最后更新**：2026-04-02
