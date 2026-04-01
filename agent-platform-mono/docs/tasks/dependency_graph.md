# 任务依赖关系图

## 完整依赖关系

```
Batch 1（基础层，严格顺序）
  1.1 Middleware 扩展（Authorization Bearer）
    └── 被 1.7 / 2.1 / 3.2 / 3.3 依赖
  
  1.2 i18n 基础层
    └── 被 1.6 / 1.7 / 2.2 / 3.1 / 3.3 依赖
  
  1.3 数据分层模型
    └── 被 1.4 / 1.5 / 1.6 / 1.7 依赖
  
  1.4 向量库适配层
    └── 被 1.4.5 / 1.5 / 1.6 / 1.7 依赖
  
  1.4.5 shared/libs 基础工具库（PDF 解析接口）
    └── 被 1.5 依赖
  
  1.5 IngestGateway
    └── 被 1.7 依赖
  
  1.6 LayeredRetrievalGateway
    └── 被 1.7 / 3.3 依赖
  
  1.7 Memory 层重写
    └── 被 3.3 依赖

Batch 2（Tool Service 层，Batch 1 完成后）
  2.1 tool_service 注册表强化
    └── 被 2.2 / 2.3 / 2.4 / 3.3 依赖
  
  2.2 ToolExecutorGateway + ToolResultAggregator
    └── 被 2.3 / 2.4 依赖
  
  2.3 plan_execute 集成 tools executor
    └── 依赖 2.1 / 2.2
  
  2.4 command graph ReAct 模式对齐
    └── 依赖 2.1

Batch 3（AI 能力层，Batch 1 + 2 完成后）
  3.1 PromptGateway 多语扩展
    └── 依赖 1.2；被 3.3 依赖
  
  3.2 LLM Gateway 补齐
    └── 依赖 1.2
  
  3.3 Agent State + 节点重构
    └── 依赖 1.1 / 1.2 / 1.6 / 1.7 / 2.1 / 3.1

Batch 4（依赖 Batch 3 完成）
  4.1 Langfuse Tracing
  4.2 指标补齐（含 tool 维度）

Batch 5（依赖 Batch 1 完成，可与 Batch 2-4 并行）
  5.1 语义去重
  5.2 时间衰减
  5.3 Context 融合权重
```

---

## 关键路径分析

### 最长路径（关键路径）

```
1.1 → 1.2 → 1.3 → 1.4 → 1.4.5 → 1.5 → 1.6 → 1.7 → 2.1 → 2.2 → 2.3 → 3.1 → 3.3 → 4.1 → 4.2
```

**总工时**: 50 天

### 可并行路径

```
主路径: 1.1-1.7 → 2.1-2.4 → 3.1-3.3 → 4.1-4.2
并行路径: 1.1-1.7 → 5.1-5.3
```

**优化后总工时**: 44 天（Batch 5 与 Batch 2-4 并行）

---

## 按模块分组

### 基础设施模块

```
1.1 Middleware 扩展
  ↓
1.2 i18n 基础层
  ↓
1.3 数据分层模型
  ↓
1.4 向量库适配层
  ↓
1.4.5 shared/libs 基础工具库
```

**工时**: 11 天  
**产出**: 上下文管理、国际化、数据模型、向量库接口、基础工具库结构

---

### 数据层模块

```
1.4 向量库适配层
  ↓
1.4.5 shared/libs 基础工具库
  ↓
1.5 IngestGateway
  ↓
1.6 LayeredRetrievalGateway
  ↓
1.7 Memory 层重写
```

**工时**: 15 天  
**产出**: 写入、检索、Memory 完整能力，PDF 解析接口

---

### Tool 模块

```
2.1 tool_service 注册表强化
  ↓
2.2 ToolExecutorGateway
  ├→ 2.3 plan_execute 集成
  └→ 2.4 command graph 对齐
```

**工时**: 12 天  
**产出**: 统一工具注册、执行、两种模式集成

---

### AI 能力模块

```
3.1 PromptGateway 多语扩展
  ↓
3.2 LLM Gateway 补齐
  ↓
3.3 Agent State 重构
```

**工时**: 10 天  
**产出**: 多语言 Prompt、LLM 国际化、完整 State

---

### 可观测性模块

```
4.1 Langfuse Tracing
  ↓
4.2 核心链路指标
```

**工时**: 6 天  
**产出**: Tracing、Metrics、Dashboard

---

### Memory 增强模块（可并行）

```
5.1 语义去重
  ↓
5.2 时间衰减
  ↓
5.3 权重治理
```

**工时**: 8 天  
**产出**: 去重、衰减、动态权重

---

## 资源分配建议

### 阶段一：Batch 1（3 周）

**团队配置**:

- 2 人：基础设施模块（1.1-1.4.5）
- 2 人：数据层模块（1.5-1.7）

**并行策略**:

- Week 1: 1.1-1.2 并行 1.3-1.4
- Week 2: 1.4.5-1.5 并行 1.6
- Week 3: 1.7 + 集成测试

---

### 阶段二：Batch 2 + Batch 5（2 周）

**团队配置**:

- 2 人：Tool 模块（2.1-2.4）
- 1 人：Memory 增强模块（5.1-5.3）

**并行策略**:

- Week 1: 2.1-2.2 并行 5.1-5.2
- Week 2: 2.3-2.4 并行 5.3

---

### 阶段三：Batch 3（2 周）

**团队配置**:

- 2 人：AI 能力模块（3.1-3.3）

**并行策略**:

- Week 1: 3.1 并行 3.2
- Week 2: 3.3 + 集成测试

---

### 阶段四：Batch 4（1 周）

**团队配置**:

- 1 人：Tracing（4.1）
- 1 人：Metrics（4.2）

**并行策略**:

- 4.1 和 4.2 完全并行

---

## 风险依赖分析

### 高风险依赖

1. **1.4 向量库适配层** → 影响 1.5 / 1.6 / 1.7
   - 风险：Filter DSL 实现复杂度
   - 缓解：提前 POC，预留 buffer

2. **2.1 tool_service 注册表** → 影响 2.2 / 2.3 / 2.4 / 3.3
   - 风险：domain_agents 工具迁移工作量
   - 缓解：先迁移一个 domain 验证方案

3. **3.3 Agent State 重构** → 影响所有 Agent 流程
   - 风险：State 字段变更影响面大
   - 缓解：向后兼容，分阶段迁移

### 中风险依赖

1. **1.6 LayeredRetrievalGateway** → 影响 1.7 / 3.3
   - 风险：四层检索性能优化
   - 缓解：并发执行 + cache

2. **3.1 PromptGateway** → 影响 3.3
   - 风险：硬编码 Prompt 迁移遗漏
   - 缓解：代码扫描 + checklist

### 低风险依赖

1. **4.1 / 4.2 可观测性** → 不影响主流程
2. **5.1-5.3 Memory 增强** → 可选特性

---

## 里程碑检查点

### M1: 基础设施完成（Week 3）

- [ ] 上下文管理支持 6 个新字段
- [ ] i18n 支持 3 种语言
- [ ] 向量库适配层通过所有单测
- [ ] 数据分层模型完整定义
- [ ] shared/libs 目录结构建立，PDF 解析接口定义完成

### M2: 数据层完成（Week 5）

- [ ] 写入层支持幂等更新
- [ ] 检索层支持四层并发
- [ ] Memory 层支持短期 + 长期

### M3: Tool 层完成（Week 7）

- [ ] 工具注册表统一 Skill + MCP
- [ ] 工具执行层支持批量并发
- [ ] plan_execute 支持 tools 模式

### M4: AI 能力完成（Week 9）

- [ ] Prompt 多语言支持
- [ ] 所有硬编码 Prompt 消除
- [ ] Agent State 支持完整上下文

### M5: 可观测性完成（Week 10）

- [ ] Langfuse Tracing 完整接入
- [ ] Prometheus Metrics 完整采集
- [ ] Grafana Dashboard 可用

---

## 依赖解耦建议

### 接口先行

1. 先定义接口（抽象类 / Protocol）
2. 提供 Mock 实现
3. 下游基于接口开发
4. 上游完成后替换 Mock

### 示例：向量库适配层

```python
# 1. 定义接口
class VectorAdapter(ABC):
    @abstractmethod
    def search(self, ...): ...

# 2. 提供 Mock
class MockVectorAdapter(VectorAdapter):
    def search(self, ...):
        return [{"text": "mock", "score": 0.9}]

# 3. 下游使用
retrieval_gateway = LayeredRetrievalGateway(
    vector_adapter=MockVectorAdapter()  # 先用 Mock
)

# 4. 上游完成后替换
retrieval_gateway = LayeredRetrievalGateway(
    vector_adapter=QdrantAdapter()  # 替换为真实实现
)
```

---

## 总结

- **关键路径**: 50 天（串行）
- **优化路径**: 44 天（Batch 5 并行）
- **高风险点**: 向量库适配层、tool_service 注册表、Agent State 重构
- **并行机会**: Batch 5 可与 Batch 2-4 并行
- **资源需求**: 2-3 人，持续 10 周
- **新增内容**: shared/libs 基础工具库（PDF/Excel/OCR 接口定义）
