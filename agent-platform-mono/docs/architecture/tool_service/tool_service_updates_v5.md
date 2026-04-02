# Tool Service 架构更新说明 v5.0

> 日期：2026-04-02  
> 更新版本：v5.0

## 一、更新概述

本次更新主要澄清了两个核心概念：

1. **Skill 的执行模型**：Skill 不是简单的 Python 函数，而是基于 LLM 的复合能力
2. **Internal MCP Adapter 的本质**：本质是 HTTP Adapter 的 MCP 协议封装

---

## 二、Skill 执行模型澄清

### 2.1 核心理解

**❌ 错误理解**：Skill 是一个封装好的 Python 函数

**✅ 正确理解**：Skill = Prompt Template + Available Tools + LLM Execution

### 2.2 Skill 的本质

```
Skill 不是这样的：
┌─────────────────────────────────┐
│ async def analyze_risk(...):    │
│     policy = await query(...)   │
│     claims = await list(...)    │
│     if claims > 2:               │
│         return "高风险"          │
│     else:                        │
│         return "低风险"          │
└─────────────────────────────────┘

Skill 是这样的：
┌─────────────────────────────────┐
│ SkillDefinition(                │
│   prompt="分析保单风险...",      │
│   tools=[query, list, ...],     │
│   llm_config={...}               │
│ )                                │
│                                  │
│ 执行时：                         │
│ 1. LLM 读取 prompt              │
│ 2. LLM 决定调用哪些工具         │
│ 3. LLM 综合信息生成结果         │
└─────────────────────────────────┘
```

### 2.3 执行流程

```
用户调用
    ↓
SkillAdapter 接收
    ↓
渲染 prompt 模板
    ↓
从 tool_gateway 获取可用工具
    ↓
创建 LLM Agent
    ↓
LLM Agent 执行（核心）：
    ┌─────────────────────────────┐
    │ LLM 推理循环：              │
    │ 1. 读取 prompt 和当前状态   │
    │ 2. 决定下一步行动           │
    │ 3. 调用工具（如果需要）     │
    │ 4. 获取结果                 │
    │ 5. 回到步骤 1（继续推理）   │
    │ 6. 生成最终答案             │
    └─────────────────────────────┘
    ↓
返回结果
```

### 2.4 关键区别

| 维度 | Tool | Skill |
|------|------|-------|
| **执行方式** | 直接调用函数 | LLM 推理 + 动态工具调用 |
| **逻辑** | 硬编码 | LLM 动态决策 |
| **灵活性** | 固定流程 | 根据情况调整 |
| **调用次数** | 1 次 | 可能多次（LLM 决定） |

**一句话总结**：
> Tool 是"函数"，Skill 是"带工具的 LLM Agent"。

---

## 三、Internal MCP Adapter 澄清

### 3.1 核心理解

**问题**：既然是调用内部微服务（HTTP），为什么叫 "MCP Adapter"？

**答案**：Internal MCP Adapter 本质就是 **HTTP Adapter 的 MCP 协议封装**。

### 3.2 架构层次

```
┌─────────────────────────────────────┐
│   Internal MCP Adapter              │
│  ┌───────────────────────────────┐  │
│  │ MCP 协议层（统一接口）        │  │
│  │ - list_tools()                │  │
│  │ - invoke(tool, arguments)     │  │
│  └───────────┬───────────────────┘  │
│              ↓                       │
│  ┌───────────────────────────────┐  │
│  │ HTTP Client 层（实际执行）    │  │
│  │ - httpx.AsyncClient           │  │
│  │ - 透传上下文                  │  │
│  │ - 服务发现、负载均衡          │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│ 内部微服务（Spring Boot）           │
│ - policy-service                    │
│ - claim-service                     │
└─────────────────────────────────────┘
```

### 3.3 为什么要这样设计？

1. **统一抽象**：对外统一的 MCP 协议接口
2. **解耦实现**：业务层不关心底层是 HTTP 还是 gRPC
3. **灵活替换**：未来可以替换为其他协议

### 3.4 External MCP vs Internal MCP

| 维度 | External MCP | Internal MCP |
|------|-------------|-------------|
| **对接对象** | 外部 MCP Server | 内部微服务 |
| **协议** | MCP 协议 | HTTP + MCP 封装 |
| **认证** | Token 认证 | 透传上下文 |
| **网络** | 外部网络 | 内部网络 |

**一句话总结**：
> Internal MCP Adapter = HTTP Client + MCP 协议抽象 + 上下文透传

---

## 四、MCP 的两种用途

```
MCP 协议
    ├── External MCP Adapter
    │   └── 用于对接外部 MCP Server（第三方服务）
    │       - 天气服务
    │       - 日历服务
    │       - 其他第三方 MCP 服务
    │
    └── Internal MCP Adapter
        └── 用于对接内部微服务（HTTP + MCP 协议封装）
            - policy-service
            - claim-service
            - customer-service
```

---

## 五、完整的工具类型

```
Tool Service
    ├── Tool（确定性工具）
    │   ├── External MCP Adapter → 外部 MCP Server
    │   ├── Internal MCP Adapter → 内部微服务（HTTP）
    │   └── Function Adapter → Python 函数
    │
    └── Skill（LLM 驱动的复合能力）
        └── Skill Adapter → LLM Agent + Tools
```

---

## 六、更新的文档

### 6.1 主要文档

1. **tool_service_final_design.md**（v5.0）
   - 新增"关键概念深度解析"章节
   - 详细解释 Skill 执行模型
   - 详细解释 Internal MCP Adapter 本质
   - 更新所有相关描述

2. **skill_concept_clarification.md**（v2.0）
   - 新增 Skill 执行流程详解
   - 明确 LLM 推理过程
   - 强调 Skill 是 LLM 驱动

### 6.2 关键更新点

| 文档 | 章节 | 更新内容 |
|------|------|---------|
| tool_service_final_design.md | 1.2 Adapter 类型定义 | 新增"本质"列，明确各 Adapter 的本质 |
| tool_service_final_design.md | 4.3 Skill Adapter | 新增执行流程说明 |
| tool_service_final_design.md | 6.2 Adapter 类型 | 新增"本质"和"关键理解" |
| tool_service_final_design.md | 7.2 为什么 Skill 需要单独的 Adapter | 重写，强调 LLM 驱动 |
| tool_service_final_design.md | 10. 关键概念深度解析 | 新增整章，详细解析 |
| skill_concept_clarification.md | 2.1 Skill 的组成 | 新增执行流程详解 |

---

## 七、关键要点总结

### 7.1 Skill 的三个关键点

1. **Skill 不是函数**：是 LLM Agent
2. **执行是动态的**：LLM 决定调用哪些工具
3. **结果是生成的**：LLM 综合信息生成

### 7.2 Internal MCP Adapter 的三个关键点

1. **本质是 HTTP Client**：底层使用 HTTP 调用微服务
2. **MCP 是协议抽象**：提供统一接口
3. **透传上下文**：tenant_id, user_id 等

### 7.3 架构清晰度

```
清晰的概念：
- MCP 用于对接外部 MCP Server（External MCP Adapter）
- HTTP Adapter 本质就是内部 MCP 的封装（Internal MCP Adapter）
- Skill 是基于 LLM 的复合能力（Skill Adapter）
```

---

## 八、下一步

### 8.1 文档已完成

- ✅ Skill 概念澄清
- ✅ Internal MCP Adapter 本质说明
- ✅ 完整架构设计文档更新

### 8.2 待实现

1. 实现 `core/tool_service/types.py` 的完整类型定义
2. 实现 `core/tool_service/adapters/base.py` 的 ToolAdapter 基类
3. 实现各个具体的 Adapter：
   - `external_mcp_adapter.py`
   - `internal_mcp_adapter.py`
   - `skill_adapter.py`
   - `function_adapter.py`
4. 重构 `core/tool_service/registry.py` 支持 Adapter 架构
5. 实现 `core/tool_service/router.py` 集成工具匹配能力
6. 更新 `app/gateway/lifespan.py` 的工具注册流程
7. 迁移现有业务工具到新架构

---

**文档维护者**：Agent Platform Team  
**最后更新**：2026-04-02  
**版本**：v5.0
