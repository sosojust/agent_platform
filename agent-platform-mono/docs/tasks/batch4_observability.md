# Batch 4 — 可观测性开发任务

## 概述

可观测性层包含 Langfuse Tracing 接入和核心链路指标，支持按租户、语言、场景等维度分析系统运行状况。

**前置依赖**: Batch 3 完成

---

## Task 4.1 — Langfuse Tracing 接入

**优先级**: P0  
**预计工时**: 3 天  
**依赖**: Batch 3 完成  
**被依赖**: 无

### 目标

完善 Langfuse Tracing，记录 LLM 调用、Prompt 版本、工具执行等关键信息，支持多维度分析。

### 实现清单

#### 1. LLM 调用 Tracing

`core/ai_core/llm/gateway.py`：

```python
class LLMGateway:
    async def complete(
        self,
        messages: list[dict],
        *,
        scene: str = "default",
        locale: str | None = None,
        **kwargs,
    ) -> dict:
        locale = locale or get_current_locale()
        
        # 构建 trace metadata
        metadata = {
            "tenant_id": get_current_tenant_id(),
            "user_id": get_current_user_id(),
            "channel_id": get_current_channel_id(),
            "locale": locale,
            "conversation_id": kwargs.get("conversation_id", ""),
            "scene": scene,
            "task_type": kwargs.get("task_type", "chat"),
        }
        
        # 创建 Langfuse generation
        generation = langfuse_client.generation(
            name=f"llm_{scene}",
            model=self._get_model_name(scene),
            input=messages,
            metadata=metadata,
        )
        
        start_time = time.time()
        try:
            result = await self._complete(messages, scene=scene, **kwargs)
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 记录成功结果
            generation.end(
                output=result.get("content", ""),
                usage={
                    "input_tokens": result.get("usage", {}).get("prompt_tokens", 0),
                    "output_tokens": result.get("usage", {}).get("completion_tokens", 0),
                    "total_tokens": result.get("usage", {}).get("total_tokens", 0),
                },
                metadata={
                    **metadata,
                    "latency_ms": duration_ms,
                    "cached": result.get("cached", False),
                    "fallback": result.get("fallback", False),
                },
            )
            
            return result
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            generation.end(
                level="ERROR",
                status_message=str(e),
                metadata={
                    **metadata,
                    "latency_ms": duration_ms,
                    "error_type": type(e).__name__,
                },
            )
            raise
```

#### 2. Prompt 版本 Tracing

`core/ai_core/prompt/gateway.py`：

```python
class PromptGateway:
    def get(
        self,
        name: str,
        variables: dict | None = None,
        locale: str | None = None,
        version: str | None = None,
    ) -> str:
        locale = locale or get_current_locale()
        
        # 获取 prompt
        prompt = self._get_prompt(name, locale, version)
        
        # 记录 prompt 使用
        langfuse_client.score(
            name="prompt_usage",
            value=1,
            data_type="NUMERIC",
            comment=f"Prompt: {name}, Locale: {locale}, Version: {version or 'latest'}",
        )
        
        return self._render(prompt, variables)
```

#### 3. 工具执行 Tracing

`core/tool_service/registry.py`：

```python
class ToolRegistry:
    async def invoke(
        self,
        tool_name: str,
        arguments: dict,
        *,
        tenant_id: str = "",
        timeout: float = 30.0,
    ) -> ToolInvokeResult:
        # 创建 Langfuse span
        span = langfuse_client.span(
            name=f"tool_{tool_name}",
            input=arguments,
            metadata={
                "tenant_id": tenant_id,
                "tool_name": tool_name,
                "timeout": timeout,
            },
        )
        
        start_time = time.time()
        try:
            result = await self._invoke_internal(tool_name, arguments, tenant_id, timeout)
            duration_ms = int((time.time() - start_time) * 1000)
            
            span.end(
                output=result.output,
                metadata={
                    "status": result.status,
                    "duration_ms": duration_ms,
                },
            )
            
            return result
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            span.end(
                level="ERROR",
                status_message=str(e),
                metadata={
                    "duration_ms": duration_ms,
                    "error_type": type(e).__name__,
                },
            )
            raise
```

#### 4. Agent 执行 Tracing

`core/agent_engine/agents.py`：

```python
async def run_agent(request: AgentRunRequest) -> AgentRunResponse:
    # 创建 Langfuse trace
    trace = langfuse_client.trace(
        name=f"agent_{request.agent_name}",
        user_id=get_current_user_id(),
        session_id=request.conversation_id,
        metadata={
            "tenant_id": get_current_tenant_id(),
            "channel_id": get_current_channel_id(),
            "locale": get_current_locale(),
            "agent_name": request.agent_name,
        },
    )
    
    try:
        result = await _run_agent_internal(request)
        
        trace.update(
            output=result.output,
            metadata={
                "step_count": result.metadata.get("step_count", 0),
                "tool_calls": result.metadata.get("tool_calls", 0),
            },
        )
        
        return result
    except Exception as e:
        trace.update(
            level="ERROR",
            status_message=str(e),
        )
        raise
```

### 验收标准

- [ ] Langfuse 控制台可按 `tenant_id` 过滤
- [ ] Langfuse 控制台可按 `locale` 过滤
- [ ] Langfuse 控制台可按 `scene` 过滤
- [ ] LLM 调用记录包含 `input_tokens`, `output_tokens`, `latency_ms`
- [ ] Prompt 使用记录包含 `name`, `locale`, `version`
- [ ] 工具执行记录包含 `tool_name`, `status`, `duration_ms`
- [ ] Agent 执行记录包含 `step_count`, `tool_calls`
- [ ] 错误调用记录包含 `error_type`, `status_message`

---

## Task 4.2 — 核心链路指标

**优先级**: P1  
**预计工时**: 3 天  
**依赖**: 4.1  
**被依赖**: 无

### 目标

建立核心链路指标体系，覆盖 LLM、检索、Memory、Tool 四大模块。

### 实现清单

#### 1. LLM 层指标

`core/ai_core/llm/metrics.py`：

```python
from prometheus_client import Counter, Histogram, Gauge

# LLM 调用次数
llm_requests_total = Counter(
    "llm_requests_total",
    "Total LLM requests",
    ["scene", "locale", "model", "status"],
)

# LLM 延迟
llm_latency_seconds = Histogram(
    "llm_latency_seconds",
    "LLM request latency",
    ["scene", "locale", "model"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

# LLM Token 使用
llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total tokens used",
    ["scene", "locale", "model", "type"],  # type: input/output
)

# LLM Fallback 次数
llm_fallback_total = Counter(
    "llm_fallback_total",
    "Total LLM fallback events",
    ["scene", "from_model", "to_model"],
)

# LLM Cache 命中率
llm_cache_hits_total = Counter(
    "llm_cache_hits_total",
    "Total LLM cache hits",
    ["scene"],
)

llm_cache_misses_total = Counter(
    "llm_cache_misses_total",
    "Total LLM cache misses",
    ["scene"],
)
```

在 `LLMGateway` 中埋点：

```python
class LLMGateway:
    async def complete(self, messages, *, scene, locale, **kwargs):
        start_time = time.time()
        try:
            result = await self._complete(messages, scene=scene, **kwargs)
            duration = time.time() - start_time
            
            # 记录指标
            llm_requests_total.labels(
                scene=scene,
                locale=locale,
                model=self._get_model_name(scene),
                status="success",
            ).inc()
            
            llm_latency_seconds.labels(
                scene=scene,
                locale=locale,
                model=self._get_model_name(scene),
            ).observe(duration)
            
            usage = result.get("usage", {})
            llm_tokens_total.labels(
                scene=scene,
                locale=locale,
                model=self._get_model_name(scene),
                type="input",
            ).inc(usage.get("prompt_tokens", 0))
            
            llm_tokens_total.labels(
                scene=scene,
                locale=locale,
                model=self._get_model_name(scene),
                type="output",
            ).inc(usage.get("completion_tokens", 0))
            
            if result.get("cached"):
                llm_cache_hits_total.labels(scene=scene).inc()
            else:
                llm_cache_misses_total.labels(scene=scene).inc()
            
            if result.get("fallback"):
                llm_fallback_total.labels(
                    scene=scene,
                    from_model=result.get("original_model", ""),
                    to_model=result.get("fallback_model", ""),
                ).inc()
            
            return result
        except Exception as e:
            llm_requests_total.labels(
                scene=scene,
                locale=locale,
                model=self._get_model_name(scene),
                status="error",
            ).inc()
            raise
```

#### 2. 检索层指标

`core/memory_rag/retrieval/metrics.py`：

```python
# 检索调用次数
retrieval_requests_total = Counter(
    "retrieval_requests_total",
    "Total retrieval requests",
    ["scope", "data_type"],
)

# 检索延迟
retrieval_latency_seconds = Histogram(
    "retrieval_latency_seconds",
    "Retrieval latency",
    ["scope"],
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0],
)

# 召回数量
retrieval_recall_count = Histogram(
    "retrieval_recall_count",
    "Number of recalled chunks",
    ["scope"],
    buckets=[0, 5, 10, 20, 50, 100],
)

# Rerank 耗时
retrieval_rerank_latency_seconds = Histogram(
    "retrieval_rerank_latency_seconds",
    "Rerank latency",
    ["scope"],
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0],
)

# Cache 命中率
retrieval_cache_hits_total = Counter(
    "retrieval_cache_hits_total",
    "Total retrieval cache hits",
    ["scope"],
)

retrieval_cache_misses_total = Counter(
    "retrieval_cache_misses_total",
    "Total retrieval cache misses",
    ["scope"],
)
```

#### 3. Memory 层指标

`core/memory_rag/memory/metrics.py`：

```python
# Memory 操作次数
memory_operations_total = Counter(
    "memory_operations_total",
    "Total memory operations",
    ["operation", "status"],  # operation: append/get/consolidate
)

# Noise 过滤率
memory_noise_filtered_total = Counter(
    "memory_noise_filtered_total",
    "Total noise filtered messages",
)

# Dedup 命中率
memory_dedup_hits_total = Counter(
    "memory_dedup_hits_total",
    "Total dedup hits",
)

# Consolidate 触发次数
memory_consolidate_total = Counter(
    "memory_consolidate_total",
    "Total consolidate operations",
)

# 短期记忆长度
memory_short_term_length = Histogram(
    "memory_short_term_length",
    "Short-term memory length",
    buckets=[0, 5, 10, 20, 50, 100],
)
```

#### 4. Tool 层指标

`core/tool_service/metrics.py`：

```python
# 工具调用次数
tool_invocations_total = Counter(
    "tool_invocations_total",
    "Total tool invocations",
    ["tool_name", "status"],
)

# 工具执行延迟
tool_execution_latency_seconds = Histogram(
    "tool_execution_latency_seconds",
    "Tool execution latency",
    ["tool_name"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

# 工具超时次数
tool_timeout_total = Counter(
    "tool_timeout_total",
    "Total tool timeout events",
    ["tool_name"],
)

# 工具错误次数
tool_errors_total = Counter(
    "tool_errors_total",
    "Total tool errors",
    ["tool_name", "error_type"],
)
```

#### 5. Prometheus Exporter

`app/gateway/routers/metrics.py`：

```python
from fastapi import APIRouter
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

router = APIRouter()

@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
```

#### 6. Grafana Dashboard 配置

创建 `docs/observability/grafana_dashboard.json`：

```json
{
  "dashboard": {
    "title": "Agent Platform Metrics",
    "panels": [
      {
        "title": "LLM Requests by Scene",
        "targets": [
          {
            "expr": "rate(llm_requests_total[5m])",
            "legendFormat": "{{scene}}"
          }
        ]
      },
      {
        "title": "LLM P95 Latency by Scene",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(llm_latency_seconds_bucket[5m]))",
            "legendFormat": "{{scene}}"
          }
        ]
      },
      {
        "title": "Tool Success Rate",
        "targets": [
          {
            "expr": "rate(tool_invocations_total{status=\"success\"}[5m]) / rate(tool_invocations_total[5m])",
            "legendFormat": "{{tool_name}}"
          }
        ]
      },
      {
        "title": "Retrieval Cache Hit Rate",
        "targets": [
          {
            "expr": "rate(retrieval_cache_hits_total[5m]) / (rate(retrieval_cache_hits_total[5m]) + rate(retrieval_cache_misses_total[5m]))",
            "legendFormat": "{{scope}}"
          }
        ]
      }
    ]
  }
}
```

### 验收标准

- [ ] Prometheus `/metrics` 端点可访问
- [ ] LLM 指标：按 scene 统计 QPS、P95 延迟、token 使用
- [ ] 检索指标：各层召回数、rerank 耗时、cache 命中率
- [ ] Memory 指标：noise 过滤率、dedup 命中率、consolidate 频率
- [ ] Tool 指标：按 tool_name 统计成功率、P95 执行耗时
- [ ] Grafana Dashboard 可正常展示所有指标
- [ ] 压测验证：1000 QPS 下指标正常采集

---

## 架构防腐门禁

每个 Task 完成时检查：

- [ ] 指标采集不影响主流程性能（P95 延迟增加 < 5ms）
- [ ] Langfuse 调用异步化，不阻塞主流程
- [ ] 指标标签数量控制（避免高基数）

---

## Batch 4 完成标志

- [ ] 所有 Task 验收标准通过
- [ ] Langfuse 控制台可按多维度分析
- [ ] Grafana Dashboard 完整展示核心指标
- [ ] 文档：可观测性接入指南
