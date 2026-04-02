# Skill 执行边界规范 - 快速参考

> 这是 `skill_execution_boundaries.md` 的快速参考版本

---

## 为什么需要边界？

Skill 是 LLM 驱动的工具，如果没有明确的边界约束，会导致：
- ❌ 递归调用，复杂度爆炸
- ❌ 执行时间不可控，资源泄露
- ❌ Token 消耗失控，成本暴涨
- ❌ 调试困难，无法追踪
- ❌ 上下文窗口膨胀，隐私泄露

**解决方案**：定义五大边界，让 Skill 成为受限的、可预测的、可计量的工具。

---

## 五大边界速查表

| 边界 | 核心约束 | 关键字段/方法 | 违反后果 |
|------|---------|--------------|---------|
| **1. 执行边界** | • 禁止嵌套（Skill 只能调用 Tool）<br>• max_steps ≤ 5<br>• timeout ≤ 30s | `max_steps`<br>`timeout_seconds`<br>`recursion_limit` | 复杂度爆炸<br>执行时间失控<br>Token 消耗失控 |
| **2. 治理归属** | • 独立计量<br>• 成本提示<br>• 指标透传 | `estimated_cost`<br>`is_llm_powered`<br>`SkillExecutionMetrics` | 成本不可控<br>账单暴涨<br>无法追踪消耗 |
| **3. 观测边界** | • 子事件上报<br>• 详细日志<br>• Trace 集成 | `tool_calls` 列表<br>OpenTelemetry Span<br>结构化日志 | 调试困难<br>问题排查困难<br>无法追踪调用链 |
| **4. 上下文隔离** | • 不继承主 Agent 历史<br>• 显式参数传递 | `prompt_template`<br>`input_schema`<br>只传入 Skill prompt | 上下文窗口膨胀<br>隐私信息泄露<br>行为不可预测 |
| **5. 降级边界** | • 统一错误结构<br>• 不抛异常<br>• 支持重试/降级 | `SkillExecutionResult`<br>`status` 字段<br>主 Agent 决策 | 错误处理不一致<br>无法降级<br>用户体验差 |

---

## 快速检查清单

在实现或审查 Skill 时，确保满足以下所有条件：

### ✅ 执行边界
```python
# 必须设置
max_steps: int = 5  # ≤ 5
timeout_seconds: int = 30  # ≤ 30

# 必须检查
if tool_entry.metadata.type == ToolType.SKILL:
    raise ValueError("Skill cannot call another Skill")

# 必须使用
await asyncio.wait_for(..., timeout=timeout_seconds)
config={"recursion_limit": max_steps}
```

### ✅ 治理归属
```python
# 必须包含
@dataclass
class SkillToolMetadata(ToolMetadata):
    estimated_cost: str = "high"  # low/medium/high
    estimated_duration_ms: int = 5000
    is_llm_powered: bool = True

# 必须返回
return {
    "skill": skill_name,
    "result": result,
    "metrics": SkillExecutionMetrics(...),  # 包含 token、step_count、duration
}
```

### ✅ 观测边界
```python
# 必须记录
logger.info("skill_execution_started", ...)
logger.info("skill_tool_call_started", ...)
logger.info("skill_tool_call_completed", ...)
logger.info("skill_execution_completed", ...)

# 必须返回
return {
    "tool_calls": [  # 详细的调用记录
        {
            "tool_name": "...",
            "arguments": {...},
            "result_summary": "...",
            "duration_ms": 123,
            "success": True,
        }
    ]
}

# 必须集成
with tracer.start_as_current_span(f"skill.execute.{skill_name}"):
    ...
```

### ✅ 上下文隔离
```python
# 必须：只传入 Skill prompt
result = await agent.ainvoke({
    "messages": [
        {"role": "user", "content": skill_prompt}  # 只有这一条
    ]
})

# 禁止：传入主 Agent 历史
result = await agent.ainvoke({
    "messages": main_agent_messages + [...]  # ❌ 错误
})

# 必须：显式定义参数
input_schema={
    "type": "object",
    "properties": {
        "policy_id": {"type": "string"},
        "user_id": {"type": "string"},  # 显式传递
    }
}
```

### ✅ 降级边界
```python
# 必须：返回统一结构
@dataclass
class SkillExecutionResult:
    skill_name: str
    status: str  # "success" | "error" | "timeout"
    result: Any | None
    error: str | None
    error_type: str | None
    tool_calls: list[dict]
    step_count: int
    duration_ms: int

# 必须：不抛异常（除非致命错误）
async def execute(...) -> SkillExecutionResult:
    try:
        ...
        return SkillExecutionResult(status="success", ...)
    except TimeoutError:
        return SkillExecutionResult(status="timeout", ...)
    except Exception as e:
        return SkillExecutionResult(status="error", ...)
```

---

## 常见反模式

### ❌ 反模式 1：Skill 调用 Skill
```python
# ❌ 错误
available_tools=["analyze_policy_risk"]  # 这是 Skill，不是 Tool
```

### ❌ 反模式 2：max_steps 过大
```python
# ❌ 错误
max_steps=50  # 太大了，应该 ≤ 5
```

### ❌ 反模式 3：没有超时
```python
# ❌ 错误
timeout_seconds=None  # 必须设置
```

### ❌ 反模式 4：继承主 Agent 历史
```python
# ❌ 错误
messages = main_agent_messages + [skill_prompt]
```

### ❌ 反模式 5：直接抛异常
```python
# ❌ 错误
if error:
    raise Exception("Skill failed")  # 应该返回 SkillExecutionResult
```

---

## 完整示例

```python
# 1. 定义 Skill（符合所有边界）
skill_metadata = SkillToolMetadata(
    name="analyze_policy_risk",
    description="分析保单风险",
    category="policy",
    
    # 上下文隔离
    prompt_template="请分析保单 {policy_id} 的风险...",
    input_schema={
        "type": "object",
        "properties": {"policy_id": {"type": "string"}},
        "required": ["policy_id"],
    },
    
    # 执行边界
    available_tools=["query_policy_basic", "calculate_risk_score"],  # 只有 Tool
    max_steps=5,
    timeout_seconds=30,
    
    # 治理归属
    estimated_cost="high",
    estimated_duration_ms=5000,
    is_llm_powered=True,
)

# 2. 执行 Skill（带所有边界检查）
async def execute(skill_metadata, arguments, context) -> SkillExecutionResult:
    try:
        # 执行边界：超时控制
        result = await asyncio.wait_for(
            _execute_internal(skill_metadata, arguments, context),
            timeout=skill_metadata.timeout_seconds,
        )
        
        # 治理归属：返回指标
        return SkillExecutionResult(
            status="success",
            result=result["result"],
            metrics=result["metrics"],
            tool_calls=result["tool_calls"],  # 观测边界
        )
    
    except asyncio.TimeoutError:
        # 降级边界：统一错误结构
        return SkillExecutionResult(
            status="timeout",
            error="Execution timeout",
        )

# 3. 主 Agent 调用（带降级处理）
result = await tool_gateway.invoke("analyze_policy_risk", {...}, context)

if result.status == "success":
    return result.result
elif result.status == "timeout":
    # 降级到简单工具
    return await tool_gateway.invoke("query_policy_basic", {...}, context)
```

---

## 相关文档

- **详细规范**：`skill_execution_boundaries.md`（完整的设计和实现）
- **主设计文档**：`tool_service_final_design.md`
- **架构修正**：`tool_service_architecture_fixes.md`
- **变更日志**：`tool_service_changelog.md`

---

**记住**：Skill 是受限的 LLM Agent，不是完整的 Agent。五大边界确保 Skill 是可控的、可预测的、可计量的工具。

**文档维护者**：Agent Platform Team  
**最后更新**：2026-04-02
