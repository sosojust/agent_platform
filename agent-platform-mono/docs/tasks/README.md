# Agent Platform 开发任务总览

## 概述

本目录包含 Agent Platform 完整开发计划的任务拆解，共分为 5 个 Batch，每个 Batch 内部有严格的依赖顺序。

## 批次依赖关系

```
Batch 1（基础设施层）
  ↓
Batch 2（Tool Service 层）
  ↓
Batch 3（AI 能力层 + Prompt 统一治理）
  ↓
Batch 4（可观测性）

Batch 5（Memory 增强）← 依赖 Batch 1，可与 Batch 2-4 并行
```

## 批次概览

### Batch 1 — 基础设施层

**文件**: `batch1_infrastructure.md`  
**预计工时**: 22 天  
**依赖**: 无  
**核心内容**:

- Task 1.1: 上下文模型扩展（Authorization Bearer）
- Task 1.2: 国际化基础层（i18n）
- Task 1.3: 数据分层模型
- Task 1.4: 向量库适配层重写
- Task 1.4.5: shared/libs 基础工具库（PDF 解析接口）
- Task 1.5: 写入层（IngestGateway）
- Task 1.6: 检索层（LayeredRetrievalGateway）
- Task 1.7: Memory 层重写

**关键产出**:

- 完整的四层数据模型（Platform / Channel / Tenant / User）
- 统一的向量检索和写入接口
- 支持多语言的 i18n 基础设施
- 重写的 Memory 层（短期 + 长期）
- 基础工具库结构（PDF/Excel/OCR 接口定义）

---

### Batch 2 — Tool Service 层重构

**文件**: `batch2_tool_service.md`  
**预计工时**: 12 天  
**依赖**: Batch 1 完成  
**核心内容**:

- Task 2.1: tool_service 注册表强化
- Task 2.2: Tool 执行层（ToolExecutorGateway）
- Task 2.3: plan_execute 集成 tools executor
- Task 2.4: command graph ReAct 模式对齐

**关键产出**:

- 统一的 Skill + MCP 工具注册表
- 标准的工具执行层（支持批量并发）
- plan_execute 支持 `executor=tools` 模式
- domain_agents 工具迁移到 tool_service

---

### Batch 3 — AI 能力层 + Prompt 统一治理

**文件**: `batch3_ai_capabilities.md`  
**预计工时**: 10 天  
**依赖**: Batch 1 + Batch 2 完成  
**核心内容**:

- Task 3.1: PromptGateway 多语扩展
- Task 3.2: LLM Gateway 补齐
- Task 3.3: Agent State 和节点重构

**关键产出**:

- 多语言 Prompt 管理（Langfuse + 本地文件）
- 消除所有硬编码 Prompt
- 扩展 AgentState（支持 locale / timezone / tool_context）
- 合并检索节点，更新 ContextInjector

---

### Batch 4 — 可观测性

**文件**: `batch4_observability.md`  
**预计工时**: 6 天  
**依赖**: Batch 3 完成  
**核心内容**:

- Task 4.1: Langfuse Tracing 接入
- Task 4.2: 核心链路指标

**关键产出**:

- 完整的 Langfuse Tracing（LLM / Prompt / Tool / Agent）
- Prometheus 指标体系（LLM / 检索 / Memory / Tool）
- Grafana Dashboard 配置

---

### Batch 5 — Memory 增强（M3）

**文件**: `batch5_memory_enhancement.md`  
**预计工时**: 8 天  
**依赖**: Batch 1 完成  
**核心内容**:

- Task 5.1: 长期记忆语义去重
- Task 5.2: 时间衰减排序
- Task 5.3: Context 融合权重治理

**关键产出**:

- 语义去重（避免冗余存储）
- 时间衰减打分（按 data_type 配置）
- 动态权重调整（按 tenant_type）

---

## 总体时间线

| 批次 | 预计工时 | 累计工时 | 并行可能性 |
| --- | --- | --- | --- |
| Batch 1 | 22 天 | 22 天 | 无 |
| Batch 2 | 12 天 | 34 天 | 无 |
| Batch 3 | 10 天 | 44 天 | 无 |
| Batch 4 | 6 天 | 50 天 | 无 |
| Batch 5 | 8 天 | - | 可与 Batch 2-4 并行 |

**最短路径**: 50 天（Batch 1-4 串行）  
**并行优化**: 44 天（Batch 5 与 Batch 2-4 并行）

---

## 架构防腐门禁

每个 Batch 交付时同步执行：

### 依赖规则

- [ ] `core/` 和 `shared/` 不允许反向依赖 `domain_agents/`
- [ ] `shared/` 不允许依赖 `core/`

### 实现隔离

- [ ] 向量库具体实现只出现在 `vector/qdrant_adapter.py`
- [ ] 上层不 import `qdrant_client`
- [ ] LLM SDK 只出现在 `ai_core/llm/`
- [ ] 上层不 import `litellm / openai / anthropic`
- [ ] PDF 解析等基础工具放在 `shared/libs/`，不依赖任何框架

### Prompt 治理

- [ ] 所有 prompt 字符串不允许在 `ai_core/prompt/` 和 `domain_agents/*/prompts/` 目录外硬编码

### Tool 规范

- [ ] `domain_agents` 的工具函数只通过 `@skill` 装饰器注册
- [ ] 不直接传入 LangGraph `ToolNode`
- [ ] `ToolCandidate.tool` 字段类型为 `str`（tool_name）
- [ ] 不允许传入可调用对象

---

## 开发流程

### 1. 任务启动

1. 阅读对应 Batch 的任务文档
2. 确认前置依赖已完成
3. 创建功能分支：`feature/batch{N}-task{N.M}`

### 2. 开发过程

1. 按 Task 顺序开发（Batch 内有严格依赖）
2. 每个 Task 完成后运行验收标准中的测试
3. 通过架构防腐门禁检查

### 3. 任务交付

1. 所有验收标准通过
2. 代码 Review
3. 合并到主分支
4. 更新任务状态

### 4. Batch 完成

1. 运行 Batch 完成标志中的集成测试
2. 性能测试
3. 文档更新
4. 发布 Release Notes

---

## 任务状态跟踪

### Batch 1 — 基础设施层

- [ ] Task 1.1: 上下文模型扩展
- [ ] Task 1.2: 国际化基础层
- [ ] Task 1.3: 数据分层模型
- [ ] Task 1.4: 向量库适配层重写
- [ ] Task 1.4.5: shared/libs 基础工具库
- [ ] Task 1.5: 写入层
- [ ] Task 1.6: 检索层
- [ ] Task 1.7: Memory 层重写

### Batch 2 — Tool Service 层重构

- [ ] Task 2.1: tool_service 注册表强化
- [ ] Task 2.2: Tool 执行层
- [ ] Task 2.3: plan_execute 集成
- [ ] Task 2.4: command graph 对齐

### Batch 3 — AI 能力层

- [ ] Task 3.1: PromptGateway 多语扩展
- [ ] Task 3.2: LLM Gateway 补齐
- [ ] Task 3.3: Agent State 重构

### Batch 4 — 可观测性

- [ ] Task 4.1: Langfuse Tracing
- [ ] Task 4.2: 核心链路指标

### Batch 5 — Memory 增强

- [ ] Task 5.1: 语义去重
- [ ] Task 5.2: 时间衰减
- [ ] Task 5.3: 权重治理

---

## 参考文档

- [原始开发计划](../draft/20260401_latest_todo.md)
- [架构设计文档](../architecture/)
- [API 文档](../api/)

---

## 联系方式

如有问题，请联系：

- 架构负责人：[待补充]
- 项目经理：[待补充]
