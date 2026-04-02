# Skill 执行边界和约束规范

> 版本：v1.0  
> 日期：2026-04-02  
> 状态：规范定义

本文档定义 Skill 作为工具层概念的五个关键边界，确保 Skill 在 Tool Service 层的设计是合理和可控的。

---

## 核心原则

**Skill 是受限的 LLM Agent**：
- Skill 不是完整的 Agent，而是一个受限的、可预测的、可计量的工具
- Skill 必须有明确的边界和约束，防止失控
- Skill 的行为必须对调用方透明和可观测

---

## 边界 1：执行边界

### 1.1 禁止嵌套调用

**规则**：Skill 内部只能调用 Tool，不能调用其他 Skill。

**原因**：
- 防止递归调用导致的复杂度爆炸
- 避免上下文窗口无限膨胀
- 确保执行时间可预测

**实现约束**：

```python
# core/tool_service/skill/executor.py
class SkillExecutor:
    async def execute(
        self,
        skill_metadata: SkillToolMetadata,
        arguments: dict,
        context: ToolContext,
    ):
        """执行 Skill"""
        # 获取可用工具（只允许 Tool，不允许 Skill）
        tool_functions = []
        for tool_name in skill_metadata.available_tools:
            tool_entry = self.tool_gateway._tools.get(tool_name)
            if not tool_entry:
                continue
            
            # ✅ 关键检查：禁止 Skill 调用 Skill
            if tool_entry.metadata.type == ToolType.SKILL:
                logger.error(
                    "skill_cannot_call_skill",
                    skill_name=skill_metadata.name,
                    attempted_skill=tool_name,
                )
                raise ValueError(
                    f"Skill '{skill_metadata.name}' cannot call another Skill '{tool_name}'. "
                    f"Skills can only call Tools."
                )
            
            tool_functions.append(self._wrap_tool_for_agent(tool_entry, context))
        
        if not tool_functions:
            raise ValueError(f"No available tools for skill: {skill_metadata.name}")
        
        # ... 继续执行
```

### 1.2 独立的 max_steps 上限

**规则**：Skill 必须有独立的 `max_steps` 限制，默认 5 步，远低于主 Agent 的 12 步。

**原因**：
- 防止 Skill 执行时间过长
- 确保 Skill 是"轻量级"的工具
- 避免消耗过多 token

**实现**：

```python
@dataclass
class SkillToolMetadata(ToolMetadata):
    """Skill 工具元数据"""
    prompt_template: str = ""
    available_tools: list[str] = field(default_factory=list)
    llm_config: dict[str, Any] = field(default_factory=lambda: {
        "model": "gpt-4",
        "temperature": 0.3
    })
    
    # ✅ 执行边界配置
    max_steps: int = 5  # 默认最多 5 步
    timeout_seconds: int = 30  # 默认超时 30 秒
    
    def __post_init__(self):
        """确保类型和边界正确"""
        self.type = ToolType.SKILL
        self.adapter_type = AdapterType.SKILL
        
        # 验证边界
        if self.max_steps > 10:
            logger.warning(
                "skill_max_steps_too_high",
                skill_name=self.name,
                max_steps=self.max_steps,
            )
        
        if self.timeout_seconds > 60:
            logger.warning(
                "skill_timeout_too_high",
                skill_name=self.name,
                timeout_seconds=self.timeout_seconds,
            )
```

### 1.3 独立的 timeout 控制

**规则**：Skill 必须有独立的 `timeout_seconds`，超时直接抛异常，不静默挂起。

**实现**：

```python
class SkillExecutor:
    async def execute(
        self,
        skill_metadata: SkillToolMetadata,
        arguments: dict,
        context: ToolContext,
    ):
        """执行 Skill（带超时控制）"""
        import asyncio
        
        try:
            # ✅ 使用 asyncio.wait_for 实现超时控制
            result = await asyncio.wait_for(
                self._execute_internal(skill_metadata, arguments, context),
                timeout=skill_metadata.timeout_seconds,
            )
            return result
        
        except asyncio.TimeoutError:
            logger.error(
                "skill_execution_timeout",
                skill_name=skill_metadata.name,
                timeout_seconds=skill_metadata.timeout_seconds,
                tenant_id=context.tenant_id,
            )
            # ✅ 超时直接抛异常，不静默挂起
            raise TimeoutError(
                f"Skill '{skill_metadata.name}' execution timeout after "
                f"{skill_metadata.timeout_seconds} seconds"
            )
    
    async def _execute_internal(
        self,
        skill_metadata: SkillToolMetadata,
        arguments: dict,
        context: ToolContext,
    ):
        """内部执行逻辑"""
        # 1. 渲染 prompt
        prompt = self._render_prompt(skill_metadata.prompt_template, arguments)
        
        # 2. 获取工具
        tool_functions = self._get_tool_functions(skill_metadata, context)
        
        # 3. 创建 LLM Agent（带 max_steps 限制）
        llm = llm_gateway.get_chat([], scene="skill_execution")
        
        agent = create_react_agent(
            model=llm,
            tools=tool_functions,
        )
        
        # 4. 执行 Agent（带 step 限制）
        logger.info(
            "skill_executing",
            skill_name=skill_metadata.name,
            max_steps=skill_metadata.max_steps,
            timeout_seconds=skill_metadata.timeout_seconds,
            tenant_id=context.tenant_id,
        )
        
        # ✅ 使用 recursion_limit 限制步数
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": prompt}]},
            config={"recursion_limit": skill_metadata.max_steps},
        )
        
        # 5. 提取结果
        return self._extract_result(result, skill_metadata)
```

---

## 边界 2：治理归属

### 2.1 独立计量

**规则**：Skill 的 `step_count`、`token` 消耗、延迟需要单独计量并透传给上层。

**实现**：

```python
@dataclass
class SkillExecutionMetrics:
    """Skill 执行指标"""
    skill_name: str
    step_count: int  # 实际执行步数
    tool_calls: list[dict]  # 调用的工具列表
    total_tokens: int  # 总 token 消耗
    prompt_tokens: int  # prompt token
    completion_tokens: int  # completion token
    duration_ms: int  # 执行时长（毫秒）
    success: bool  # 是否成功
    error_message: str | None = None


class SkillExecutor:
    async def _execute_internal(
        self,
        skill_metadata: SkillToolMetadata,
        arguments: dict,
        context: ToolContext,
    ):
        """内部执行逻辑（带指标收集）"""
        import time
        
        start_time = time.time()
        step_count = 0
        tool_calls = []
        total_tokens = 0
        
        try:
            # ... 执行逻辑
            
            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": prompt}]},
                config={"recursion_limit": skill_metadata.max_steps},
            )
            
            # ✅ 收集指标
            messages = result.get("messages", [])
            for msg in messages:
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    step_count += 1
                    for tool_call in msg.tool_calls:
                        tool_calls.append({
                            "tool_name": tool_call.get("name"),
                            "arguments": tool_call.get("args"),
                        })
                
                # 收集 token 消耗（如果 LLM 返回了）
                if hasattr(msg, "usage_metadata"):
                    total_tokens += msg.usage_metadata.get("total_tokens", 0)
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            # ✅ 构建带指标的返回结果
            metrics = SkillExecutionMetrics(
                skill_name=skill_metadata.name,
                step_count=step_count,
                tool_calls=tool_calls,
                total_tokens=total_tokens,
                prompt_tokens=0,  # 需要从 LLM 获取
                completion_tokens=0,  # 需要从 LLM 获取
                duration_ms=duration_ms,
                success=True,
            )
            
            final_message = messages[-1]
            
            return {
                "skill": skill_metadata.name,
                "result": final_message.content,
                "metrics": metrics,  # ✅ 透传指标
            }
        
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            
            metrics = SkillExecutionMetrics(
                skill_name=skill_metadata.name,
                step_count=step_count,
                tool_calls=tool_calls,
                total_tokens=total_tokens,
                prompt_tokens=0,
                completion_tokens=0,
                duration_ms=duration_ms,
                success=False,
                error_message=str(e),
            )
            
            return {
                "skill": skill_metadata.name,
                "result": None,
                "metrics": metrics,
                "error": str(e),
            }
```

### 2.2 成本提示

**规则**：在 `ToolMetadata.type == SKILL` 时，`list_tools()` 的返回结果里要附带成本提示字段。

**实现**：

```python
@dataclass
class SkillToolMetadata(ToolMetadata):
    """Skill 工具元数据"""
    # ... 其他字段
    
    # ✅ 成本提示
    estimated_cost: str = "high"  # "low" | "medium" | "high"
    estimated_duration_ms: int = 5000  # 预估执行时长
    is_llm_powered: bool = True  # 标识这是 LLM 驱动的工具
    
    def __post_init__(self):
        """确保类型和提示正确"""
        self.type = ToolType.SKILL
        self.adapter_type = AdapterType.SKILL
        self.is_llm_powered = True  # Skill 总是 LLM 驱动的
        
        # 根据 max_steps 估算成本
        if self.max_steps <= 3:
            self.estimated_cost = "medium"
        elif self.max_steps <= 5:
            self.estimated_cost = "high"
        else:
            self.estimated_cost = "very_high"


# ToolGateway 在列出工具时提供成本信息
class ToolGateway:
    def list_tools(
        self,
        context: ToolContext,
        include_cost_info: bool = True,  # ✅ 可选包含成本信息
    ) -> List[dict]:
        """列出可用工具（带成本信息）"""
        tools = []
        
        for name, entry in self._tools.items():
            # 权限检查
            has_permission, _ = await self.permission_checker.check_permission(
                entry.metadata,
                context,
            )
            
            if not has_permission:
                continue
            
            tool_info = {
                "name": entry.metadata.name,
                "description": entry.metadata.description,
                "type": entry.metadata.type.value,
                "input_schema": entry.metadata.input_schema,
            }
            
            # ✅ 如果是 Skill，添加成本信息
            if include_cost_info and entry.metadata.type == ToolType.SKILL:
                skill_meta = entry.metadata  # SkillToolMetadata
                tool_info["cost_info"] = {
                    "is_llm_powered": skill_meta.is_llm_powered,
                    "estimated_cost": skill_meta.estimated_cost,
                    "estimated_duration_ms": skill_meta.estimated_duration_ms,
                    "max_steps": skill_meta.max_steps,
                    "warning": "This tool uses LLM and may incur significant costs",
                }
            
            tools.append(tool_info)
        
        return tools
```


---

## 边界 3：观测边界

### 3.1 子事件上报

**规则**：Skill 内部的每次工具调用需要作为子事件上报，而不是整个 Skill 作为一个黑盒。

**原因**：
- 主 Agent 需要知道 Skill 内部发生了什么
- 便于调试和问题排查
- 支持完整的调用链追踪

**实现**：

```python
class SkillExecutor:
    async def _execute_internal(
        self,
        skill_metadata: SkillToolMetadata,
        arguments: dict,
        context: ToolContext,
    ):
        """内部执行逻辑（带详细日志）"""
        import time
        
        start_time = time.time()
        tool_calls_detail = []  # ✅ 详细的工具调用记录
        
        # 记录 Skill 开始
        logger.info(
            "skill_execution_started",
            skill_name=skill_metadata.name,
            arguments=arguments,
            tenant_id=context.tenant_id,
            request_id=context.request_id,
            max_steps=skill_metadata.max_steps,
        )
        
        try:
            # 创建带日志的工具包装器
            tool_functions = []
            for tool_name in skill_metadata.available_tools:
                tool_entry = self.tool_gateway._tools.get(tool_name)
                if tool_entry:
                    # ✅ 包装工具，记录每次调用
                    wrapped_tool = self._wrap_tool_with_logging(
                        tool_entry,
                        context,
                        tool_calls_detail,  # 传入列表，记录调用
                    )
                    tool_functions.append(wrapped_tool)
            
            # 执行 Agent
            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": prompt}]},
                config={"recursion_limit": skill_metadata.max_steps},
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            # ✅ 记录 Skill 完成（包含所有子调用）
            logger.info(
                "skill_execution_completed",
                skill_name=skill_metadata.name,
                duration_ms=duration_ms,
                step_count=len(tool_calls_detail),
                tool_calls=tool_calls_detail,  # ✅ 详细的调用记录
                tenant_id=context.tenant_id,
                request_id=context.request_id,
            )
            
            final_message = result["messages"][-1]
            
            return {
                "skill": skill_metadata.name,
                "result": final_message.content,
                "tool_calls": tool_calls_detail,  # ✅ 返回给调用方
                "step_count": len(tool_calls_detail),
                "duration_ms": duration_ms,
            }
        
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            
            # ✅ 记录 Skill 失败
            logger.error(
                "skill_execution_failed",
                skill_name=skill_metadata.name,
                duration_ms=duration_ms,
                step_count=len(tool_calls_detail),
                tool_calls=tool_calls_detail,
                error=str(e),
                tenant_id=context.tenant_id,
                request_id=context.request_id,
            )
            
            raise
    
    def _wrap_tool_with_logging(
        self,
        tool_entry,
        context: ToolContext,
        tool_calls_detail: list,  # 用于记录调用
    ):
        """包装工具，记录每次调用"""
        from langchain_core.tools import tool as langchain_tool
        import time
        
        async def wrapped_func(**kwargs):
            tool_name = tool_entry.metadata.name
            call_start = time.time()
            
            # ✅ 记录工具调用开始
            logger.info(
                "skill_tool_call_started",
                tool_name=tool_name,
                arguments=kwargs,
                tenant_id=context.tenant_id,
                request_id=context.request_id,
            )
            
            try:
                # 调用实际工具
                result = await self.tool_gateway.invoke(
                    tool_name=tool_name,
                    arguments=kwargs,
                    context=context,
                )
                
                call_duration_ms = int((time.time() - call_start) * 1000)
                
                # ✅ 记录工具调用成功
                logger.info(
                    "skill_tool_call_completed",
                    tool_name=tool_name,
                    duration_ms=call_duration_ms,
                    result_summary=str(result)[:100],  # 结果摘要
                    tenant_id=context.tenant_id,
                    request_id=context.request_id,
                )
                
                # ✅ 添加到详细记录
                tool_calls_detail.append({
                    "tool_name": tool_name,
                    "arguments": kwargs,
                    "result_summary": str(result)[:100],
                    "duration_ms": call_duration_ms,
                    "success": True,
                })
                
                return result
            
            except Exception as e:
                call_duration_ms = int((time.time() - call_start) * 1000)
                
                # ✅ 记录工具调用失败
                logger.error(
                    "skill_tool_call_failed",
                    tool_name=tool_name,
                    duration_ms=call_duration_ms,
                    error=str(e),
                    tenant_id=context.tenant_id,
                    request_id=context.request_id,
                )
                
                # ✅ 添加到详细记录
                tool_calls_detail.append({
                    "tool_name": tool_name,
                    "arguments": kwargs,
                    "error": str(e),
                    "duration_ms": call_duration_ms,
                    "success": False,
                })
                
                raise
        
        wrapped_func.__name__ = tool_entry.metadata.name
        wrapped_func.__doc__ = tool_entry.metadata.description
        
        return langchain_tool(wrapped_func)
```

### 3.2 Trace 集成

**规则**：Skill 的执行应该集成到分布式追踪系统（如 OpenTelemetry）。

**实现**：

```python
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

tracer = trace.get_tracer(__name__)


class SkillExecutor:
    async def execute(
        self,
        skill_metadata: SkillToolMetadata,
        arguments: dict,
        context: ToolContext,
    ):
        """执行 Skill（带 Trace）"""
        # ✅ 创建 Skill 执行的 Span
        with tracer.start_as_current_span(
            f"skill.execute.{skill_metadata.name}",
            attributes={
                "skill.name": skill_metadata.name,
                "skill.max_steps": skill_metadata.max_steps,
                "skill.timeout_seconds": skill_metadata.timeout_seconds,
                "tenant.id": context.tenant_id,
                "request.id": context.request_id or "",
            },
        ) as span:
            try:
                result = await asyncio.wait_for(
                    self._execute_internal(skill_metadata, arguments, context),
                    timeout=skill_metadata.timeout_seconds,
                )
                
                # ✅ 记录成功指标
                span.set_attribute("skill.step_count", result.get("step_count", 0))
                span.set_attribute("skill.duration_ms", result.get("duration_ms", 0))
                span.set_status(Status(StatusCode.OK))
                
                return result
            
            except asyncio.TimeoutError as e:
                span.set_status(Status(StatusCode.ERROR, "Timeout"))
                span.record_exception(e)
                raise
            
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
    
    def _wrap_tool_with_logging(
        self,
        tool_entry,
        context: ToolContext,
        tool_calls_detail: list,
    ):
        """包装工具（带 Trace）"""
        from langchain_core.tools import tool as langchain_tool
        import time
        
        async def wrapped_func(**kwargs):
            tool_name = tool_entry.metadata.name
            
            # ✅ 为每个工具调用创建子 Span
            with tracer.start_as_current_span(
                f"skill.tool_call.{tool_name}",
                attributes={
                    "tool.name": tool_name,
                    "tool.type": tool_entry.metadata.type.value,
                },
            ) as span:
                call_start = time.time()
                
                try:
                    result = await self.tool_gateway.invoke(
                        tool_name=tool_name,
                        arguments=kwargs,
                        context=context,
                    )
                    
                    call_duration_ms = int((time.time() - call_start) * 1000)
                    
                    span.set_attribute("tool.duration_ms", call_duration_ms)
                    span.set_status(Status(StatusCode.OK))
                    
                    tool_calls_detail.append({
                        "tool_name": tool_name,
                        "arguments": kwargs,
                        "result_summary": str(result)[:100],
                        "duration_ms": call_duration_ms,
                        "success": True,
                    })
                    
                    return result
                
                except Exception as e:
                    call_duration_ms = int((time.time() - call_start) * 1000)
                    
                    span.set_attribute("tool.duration_ms", call_duration_ms)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    
                    tool_calls_detail.append({
                        "tool_name": tool_name,
                        "arguments": kwargs,
                        "error": str(e),
                        "duration_ms": call_duration_ms,
                        "success": False,
                    })
                    
                    raise
        
        wrapped_func.__name__ = tool_entry.metadata.name
        wrapped_func.__doc__ = tool_entry.metadata.description
        
        return langchain_tool(wrapped_func)
```

---

## 边界 4：上下文隔离边界

### 4.1 不继承主 Agent 历史

**规则**：Skill 内部的 LLM Agent 不应该继承主 Agent 的完整 messages 历史，只接收 Skill 的输入参数和渲染后的 prompt。

**原因**：
- 防止上下文窗口双倍膨胀
- 避免主对话的隐私信息流入 Skill
- 确保 Skill 的行为可预测

**实现**：

```python
class SkillExecutor:
    async def _execute_internal(
        self,
        skill_metadata: SkillToolMetadata,
        arguments: dict,
        context: ToolContext,
    ):
        """内部执行逻辑（上下文隔离）"""
        # 1. 渲染 prompt（只使用输入参数）
        prompt = self._render_prompt(skill_metadata.prompt_template, arguments)
        
        # 2. 获取工具
        tool_functions = self._get_tool_functions(skill_metadata, context)
        
        # 3. 创建 LLM Agent
        llm = llm_gateway.get_chat([], scene="skill_execution")
        
        agent = create_react_agent(
            model=llm,
            tools=tool_functions,
        )
        
        # 4. 执行 Agent
        # ✅ 只传入 Skill 的 prompt，不传入主 Agent 的历史
        result = await agent.ainvoke(
            {
                "messages": [
                    # ✅ 只有一条消息：Skill 的 prompt
                    {"role": "user", "content": prompt}
                ]
            },
            config={"recursion_limit": skill_metadata.max_steps},
        )
        
        return self._extract_result(result, skill_metadata)
    
    def _render_prompt(self, template: str, arguments: dict) -> str:
        """
        渲染 prompt 模板。
        
        ✅ 只使用 Skill 的输入参数，不访问主 Agent 的上下文。
        """
        try:
            return template.format(**arguments)
        except KeyError as e:
            raise ValueError(f"Prompt template missing argument: {e}")
```

### 4.2 上下文传递规范

**规则**：如果 Skill 确实需要一些上下文信息，必须通过显式的参数传递。

**示例**：

```python
# ❌ 错误：隐式访问主 Agent 的上下文
skill_def = SkillToolMetadata(
    name="analyze_policy_risk",
    prompt_template="请分析保单 {policy_id} 的风险。",  # 只有 policy_id
    # ...
)

# ✅ 正确：显式传递需要的上下文
skill_def = SkillToolMetadata(
    name="analyze_policy_risk",
    prompt_template="""
请分析保单 {policy_id} 的风险。

用户背景：
- 用户 ID: {user_id}
- 租户 ID: {tenant_id}
- 渠道: {channel_id}

请考虑以下因素：
1. 保额是否合理
2. 保费是否异常
3. 投保人信息是否完整
""",
    input_schema={
        "type": "object",
        "properties": {
            "policy_id": {"type": "string", "description": "保单 ID"},
            "user_id": {"type": "string", "description": "用户 ID"},
            "tenant_id": {"type": "string", "description": "租户 ID"},
            "channel_id": {"type": "string", "description": "渠道 ID"},
        },
        "required": ["policy_id"],  # 只有 policy_id 是必需的
    },
)

# 调用时显式传递
result = await tool_gateway.invoke(
    tool_name="analyze_policy_risk",
    arguments={
        "policy_id": "POL123",
        "user_id": context.user_id,  # ✅ 显式传递
        "tenant_id": context.tenant_id,  # ✅ 显式传递
        "channel_id": context.channel_id,  # ✅ 显式传递
    },
    context=context,
)
```

---

## 边界 5：降级边界

### 5.1 统一错误处理

**规则**：Skill 执行失败时，返回结构化的错误对象，而不是让 exception 直接冒泡。

**原因**：
- 让主 Agent 自行决定是否重试或降级
- 提供更好的错误信息
- 支持部分成功的场景

**实现**：

```python
@dataclass
class SkillExecutionResult:
    """Skill 执行结果（统一结构）"""
    skill_name: str
    status: str  # "success" | "error" | "timeout" | "partial_success"
    result: Any | None  # 成功时的结果
    error: str | None  # 失败时的错误信息
    error_type: str | None  # 错误类型
    tool_calls: list[dict]  # 工具调用记录
    step_count: int  # 实际步数
    duration_ms: int  # 执行时长
    metrics: SkillExecutionMetrics | None  # 详细指标


class SkillExecutor:
    async def execute(
        self,
        skill_metadata: SkillToolMetadata,
        arguments: dict,
        context: ToolContext,
    ) -> SkillExecutionResult:
        """
        执行 Skill（统一返回结构）。
        
        ✅ 总是返回 SkillExecutionResult，不抛异常。
        """
        import time
        import asyncio
        
        start_time = time.time()
        
        try:
            # 执行 Skill（带超时）
            result_dict = await asyncio.wait_for(
                self._execute_internal(skill_metadata, arguments, context),
                timeout=skill_metadata.timeout_seconds,
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            # ✅ 成功：返回结构化结果
            return SkillExecutionResult(
                skill_name=skill_metadata.name,
                status="success",
                result=result_dict.get("result"),
                error=None,
                error_type=None,
                tool_calls=result_dict.get("tool_calls", []),
                step_count=result_dict.get("step_count", 0),
                duration_ms=duration_ms,
                metrics=result_dict.get("metrics"),
            )
        
        except asyncio.TimeoutError:
            duration_ms = int((time.time() - start_time) * 1000)
            
            logger.error(
                "skill_execution_timeout",
                skill_name=skill_metadata.name,
                timeout_seconds=skill_metadata.timeout_seconds,
                tenant_id=context.tenant_id,
            )
            
            # ✅ 超时：返回结构化错误
            return SkillExecutionResult(
                skill_name=skill_metadata.name,
                status="timeout",
                result=None,
                error=f"Execution timeout after {skill_metadata.timeout_seconds} seconds",
                error_type="TimeoutError",
                tool_calls=[],
                step_count=0,
                duration_ms=duration_ms,
                metrics=None,
            )
        
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            
            logger.error(
                "skill_execution_error",
                skill_name=skill_metadata.name,
                error=str(e),
                error_type=type(e).__name__,
                tenant_id=context.tenant_id,
            )
            
            # ✅ 错误：返回结构化错误
            return SkillExecutionResult(
                skill_name=skill_metadata.name,
                status="error",
                result=None,
                error=str(e),
                error_type=type(e).__name__,
                tool_calls=[],
                step_count=0,
                duration_ms=duration_ms,
                metrics=None,
            )
```

### 5.2 主 Agent 的降级处理

**规则**：主 Agent 应该能够根据 Skill 的返回结果决定如何处理。

**示例**：

```python
# 主 Agent 调用 Skill
async def main_agent_call_skill():
    result = await tool_gateway.invoke(
        tool_name="analyze_policy_risk",
        arguments={"policy_id": "POL123"},
        context=context,
    )
    
    # ✅ 根据 status 决定如何处理
    if result.status == "success":
        # 成功：使用结果
        return result.result
    
    elif result.status == "timeout":
        # 超时：降级到简单工具
        logger.warning(
            "skill_timeout_fallback_to_simple_tool",
            skill_name=result.skill_name,
        )
        return await tool_gateway.invoke(
            tool_name="query_policy_basic",  # 降级到简单工具
            arguments={"policy_id": "POL123"},
            context=context,
        )
    
    elif result.status == "error":
        # 错误：根据错误类型决定
        if result.error_type == "PermissionError":
            # 权限错误：不重试
            raise PermissionError(result.error)
        else:
            # 其他错误：重试一次
            logger.warning(
                "skill_error_retry",
                skill_name=result.skill_name,
                error=result.error,
            )
            return await tool_gateway.invoke(
                tool_name="analyze_policy_risk",
                arguments={"policy_id": "POL123"},
                context=context,
            )
```


---

## 总结：五大边界对比

| 边界 | 约束 | 实现要点 | 违反后果 |
|------|------|---------|---------|
| **执行边界** | - 禁止嵌套调用<br>- max_steps ≤ 5<br>- timeout_seconds ≤ 30 | - 类型检查<br>- recursion_limit<br>- asyncio.wait_for | - 复杂度爆炸<br>- 执行时间不可控<br>- token 消耗失控 |
| **治理归属** | - 独立计量<br>- 成本提示<br>- 指标透传 | - SkillExecutionMetrics<br>- estimated_cost 字段<br>- 返回结果包含 metrics | - 成本不可控<br>- 账单暴涨<br>- 无法追踪消耗 |
| **观测边界** | - 子事件上报<br>- 详细日志<br>- Trace 集成 | - 包装工具记录调用<br>- 结构化日志<br>- OpenTelemetry Span | - 调试困难<br>- 问题排查困难<br>- 无法追踪调用链 |
| **上下文隔离** | - 不继承主 Agent 历史<br>- 显式参数传递 | - 只传入 Skill prompt<br>- 通过 input_schema 定义参数 | - 上下文窗口膨胀<br>- 隐私信息泄露<br>- 行为不可预测 |
| **降级边界** | - 统一错误结构<br>- 不抛异常<br>- 支持重试/降级 | - SkillExecutionResult<br>- status 字段<br>- 主 Agent 决策 | - 错误处理不一致<br>- 无法降级<br>- 用户体验差 |

---

## 配置示例

### 完整的 Skill 定义

```python
# 符合所有边界约束的 Skill 定义
skill_metadata = SkillToolMetadata(
    # 基本信息
    name="analyze_policy_risk",
    description="分析保单风险，考虑保额、保费、投保人信息等因素",
    category="policy",
    
    # Prompt 模板（上下文隔离）
    prompt_template="""
请分析保单 {policy_id} 的风险。

考虑以下因素：
1. 保额是否合理
2. 保费是否异常
3. 投保人信息是否完整

请使用提供的工具获取必要信息，并给出风险评估结果。
""",
    
    # 可用工具（执行边界：只能是 Tool，不能是 Skill）
    available_tools=[
        "query_policy_basic",
        "query_policy_claims",
        "calculate_risk_score",
    ],
    
    # LLM 配置
    llm_config={
        "model": "gpt-4",
        "temperature": 0.3,
    },
    
    # 输入 Schema（上下文隔离：显式定义参数）
    input_schema={
        "type": "object",
        "properties": {
            "policy_id": {
                "type": "string",
                "description": "保单 ID",
            },
        },
        "required": ["policy_id"],
    },
    
    # 执行边界
    max_steps=5,  # 最多 5 步
    timeout_seconds=30,  # 超时 30 秒
    
    # 治理归属
    estimated_cost="high",  # 成本提示
    estimated_duration_ms=5000,  # 预估 5 秒
    is_llm_powered=True,  # LLM 驱动
    
    # 其他元数据
    tags=["skill", "policy", "risk"],
    version="1.0.0",
)
```

### 调用示例

```python
# 主 Agent 调用 Skill
async def analyze_policy(policy_id: str, context: ToolContext):
    """主 Agent 调用 Skill 的示例"""
    
    # 1. 调用 Skill
    result = await tool_gateway.invoke(
        tool_name="analyze_policy_risk",
        arguments={"policy_id": policy_id},
        context=context,
    )
    
    # 2. 检查结果状态（降级边界）
    if result.status == "success":
        # 成功：记录指标并返回结果
        logger.info(
            "skill_call_success",
            skill_name=result.skill_name,
            step_count=result.step_count,
            duration_ms=result.duration_ms,
            tool_calls_count=len(result.tool_calls),
        )
        
        # 观测边界：记录详细的工具调用
        for tool_call in result.tool_calls:
            logger.debug(
                "skill_tool_call_detail",
                tool_name=tool_call["tool_name"],
                duration_ms=tool_call["duration_ms"],
                success=tool_call["success"],
            )
        
        return result.result
    
    elif result.status == "timeout":
        # 超时：降级到简单工具
        logger.warning(
            "skill_timeout_fallback",
            skill_name=result.skill_name,
            timeout_seconds=30,
        )
        
        # 降级：使用简单工具
        basic_info = await tool_gateway.invoke(
            tool_name="query_policy_basic",
            arguments={"policy_id": policy_id},
            context=context,
        )
        
        return f"无法完成完整分析（超时），基本信息：{basic_info}"
    
    elif result.status == "error":
        # 错误：根据错误类型决定
        logger.error(
            "skill_call_error",
            skill_name=result.skill_name,
            error=result.error,
            error_type=result.error_type,
        )
        
        if result.error_type == "PermissionError":
            # 权限错误：不重试
            raise PermissionError(f"无权限调用 Skill: {result.error}")
        else:
            # 其他错误：返回错误信息
            return f"分析失败：{result.error}"
```

---

## 验证清单

在实现 Skill 时，请确保满足以下所有条件：

### 执行边界
- [ ] Skill 只能调用 Tool，不能调用其他 Skill
- [ ] 设置了 `max_steps`（建议 ≤ 5）
- [ ] 设置了 `timeout_seconds`（建议 ≤ 30）
- [ ] 超时会抛出异常，不会静默挂起

### 治理归属
- [ ] 返回结果包含 `step_count`
- [ ] 返回结果包含 `tool_calls` 列表
- [ ] 返回结果包含 `duration_ms`
- [ ] 返回结果包含 `metrics`（token 消耗等）
- [ ] `SkillToolMetadata` 包含 `estimated_cost` 字段
- [ ] `SkillToolMetadata` 包含 `is_llm_powered = True`

### 观测边界
- [ ] 每次工具调用都有独立的日志
- [ ] 日志包含工具名称、参数、结果摘要、耗时
- [ ] 集成了分布式追踪（OpenTelemetry）
- [ ] 返回结果包含详细的 `tool_calls` 列表

### 上下文隔离
- [ ] Skill 不继承主 Agent 的 messages 历史
- [ ] Skill 只接收 `prompt_template` 和 `arguments`
- [ ] 需要的上下文信息通过 `input_schema` 显式定义
- [ ] 不访问主 Agent 的全局状态

### 降级边界
- [ ] 返回统一的 `SkillExecutionResult` 结构
- [ ] 包含 `status` 字段（success/error/timeout）
- [ ] 错误时包含 `error` 和 `error_type`
- [ ] 不直接抛出异常（除非是致命错误）
- [ ] 主 Agent 可以根据 `status` 决定降级策略

---

## 反模式警告

### ❌ 反模式 1：Skill 调用 Skill

```python
# ❌ 错误：Skill 调用另一个 Skill
skill_metadata = SkillToolMetadata(
    name="comprehensive_analysis",
    available_tools=[
        "analyze_policy_risk",  # ❌ 这是一个 Skill，不是 Tool
        "query_policy_basic",
    ],
)
```

**后果**：递归调用、复杂度爆炸、执行时间不可控。

### ❌ 反模式 2：无限制的 max_steps

```python
# ❌ 错误：max_steps 过大
skill_metadata = SkillToolMetadata(
    name="analyze_policy_risk",
    max_steps=50,  # ❌ 太大了
)
```

**后果**：执行时间过长、token 消耗过多、成本失控。

### ❌ 反模式 3：没有超时控制

```python
# ❌ 错误：没有设置 timeout
skill_metadata = SkillToolMetadata(
    name="analyze_policy_risk",
    timeout_seconds=None,  # ❌ 没有超时
)
```

**后果**：可能永久挂起、资源泄露。

### ❌ 反模式 4：继承主 Agent 历史

```python
# ❌ 错误：传入主 Agent 的完整历史
result = await agent.ainvoke({
    "messages": main_agent_messages + [  # ❌ 继承了主 Agent 历史
        {"role": "user", "content": skill_prompt}
    ]
})
```

**后果**：上下文窗口膨胀、隐私信息泄露。

### ❌ 反模式 5：直接抛出异常

```python
# ❌ 错误：直接抛出异常
async def execute(self, ...):
    if error:
        raise Exception("Skill failed")  # ❌ 直接抛异常
```

**后果**：主 Agent 无法降级、用户体验差。

---

## 附录：配置模板

### Skill 配置文件模板（YAML）

```yaml
# config/skills/policy_skills.yaml
skills:
  - name: analyze_policy_risk
    description: 分析保单风险
    category: policy
    
    # Prompt 模板
    prompt_template: |
      请分析保单 {policy_id} 的风险。
      
      考虑以下因素：
      1. 保额是否合理
      2. 保费是否异常
      3. 投保人信息是否完整
    
    # 可用工具（只能是 Tool）
    available_tools:
      - query_policy_basic
      - query_policy_claims
      - calculate_risk_score
    
    # LLM 配置
    llm_config:
      model: gpt-4
      temperature: 0.3
    
    # 输入 Schema
    input_schema:
      type: object
      properties:
        policy_id:
          type: string
          description: 保单 ID
      required:
        - policy_id
    
    # 执行边界
    max_steps: 5
    timeout_seconds: 30
    
    # 治理归属
    estimated_cost: high
    estimated_duration_ms: 5000
    
    # 元数据
    version: "1.0.0"
    tags:
      - skill
      - policy
      - risk
```

---

**文档维护者**：Agent Platform Team  
**最后更新**：2026-04-02  
**版本**：v1.0（Skill 执行边界规范）

**相关文档**：
- `tool_service_final_design.md`：Tool Service 主设计文档
- `tool_service_architecture_fixes.md`：架构问题修正
- `skill_concept_clarification.md`：Skill 概念澄清
