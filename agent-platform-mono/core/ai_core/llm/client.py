from __future__ import annotations

from dataclasses import dataclass
import json
from time import perf_counter
from time import time
from typing import Any, AsyncIterator, Mapping

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
try:
    from litellm import acompletion
except Exception:
    acompletion = None

from core.ai_core.routing.router import ModelSpec, select_model
from shared.config.settings import settings
from shared.logging.logger import get_logger
from shared.middleware.tenant import (
    get_current_conversation_id,
    get_current_tenant_id,
    get_current_thread_id,
    get_current_trace_id,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class UsageSummary:
    tenant_id: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class LLMResult:
    text: str
    usage: dict[str, int]
    finish_reason: str
    model: str
    cached: bool = False
    tool_calls: list[dict[str, Any]] | None = None


class LLMGatewayError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)


class LiteLLMChatAdapter:
    def __init__(
        self,
        gateway: LLMGateway,
        *,
        task_type: str = "complex",
        scene: str | None = None,
        tools: list[Any] | None = None,
    ) -> None:
        self._gateway = gateway
        self._task_type = task_type
        self._scene = scene
        self._tools = list(tools or [])

    def bind_tools(self, tools: list[Any]) -> LiteLLMChatAdapter:
        return LiteLLMChatAdapter(
            self._gateway,
            task_type=self._task_type,
            scene=self._scene,
            tools=list(tools or []),
        )

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        result = await self._gateway.complete(
            messages=messages,
            task_type=self._task_type,
            scene=self._scene,
            tools=self._tools,
        )
        return AIMessage(
            content=result.text,
            tool_calls=list(result.tool_calls or []),
            additional_kwargs={"model": result.model, "finish_reason": result.finish_reason},
        )


class LLMGateway:
    def __init__(self) -> None:
        self._tenant_usage: dict[str, dict[str, int]] = {}
        self._conversation_usage: dict[str, int] = {}
        self._router_cursor: dict[str, int] = {}
        self._router_unhealthy_until: dict[str, float] = {}
        self._router_raw: str = ""
        self._router_parsed: dict[str, list[dict[str, Any]]] = {}
        self._cache_data: dict[str, tuple[float, LLMResult]] = {}
        self._cache_scene_raw: str = ""
        self._cache_task_raw: str = ""
        self._cache_scene_map: dict[str, int] = {}
        self._cache_task_map: dict[str, int] = {}

    def get_chat(
        self,
        tools: list[Any],
        task_type: str = "complex",
        *,
        scene: str | None = None,
    ) -> LiteLLMChatAdapter:
        return LiteLLMChatAdapter(self, task_type=task_type, scene=scene).bind_tools(tools)

    async def complete(
        self,
        messages: list[Any],
        task_type: str = "complex",
        *,
        scene: str | None = None,
        tools: list[Any] | None = None,
        tenant_id: str | None = None,
        conversation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LLMResult:
        self._ensure_provider_ready()
        started = perf_counter()
        tenant = str(tenant_id or get_current_tenant_id() or "unknown")
        conversation = str(conversation_id or get_current_conversation_id() or "")
        await self._check_budget(tenant, conversation)
        spec = select_model(task_type=task_type, scene=scene)
        payload = self._to_openai_messages(messages)
        tool_payload = self._to_openai_tools(list(tools or []))
        cache_ttl = self._cache_ttl_seconds(spec.scene, spec.task_type)
        cache_key = self._cache_key(spec, tenant, payload) if cache_ttl > 0 and not tool_payload else ""
        if cache_key:
            cached_result = self._cache_get(cache_key)
            if cached_result is not None:
                logger.info(
                    "llm_complete_cache_hit",
                    model=spec.model,
                    task_type=spec.task_type,
                    scene=spec.scene,
                    tenant_id=tenant,
                    conversation_id=conversation,
                    trace_id=get_current_trace_id(),
                    thread_id=get_current_thread_id(),
                    fallback=False,
                )
                return cached_result
        response: Any | None = None
        deployment_id = "default"
        last_error: LLMGatewayError | None = None
        candidates = self._provider_param_candidates(spec)
        attempt_limit = min(len(candidates), max(1, int(settings.llm.router_max_attempts)))
        for idx in range(attempt_limit):
            deployment_id, provider_params = candidates[idx]
            params: dict[str, Any] = {
                **provider_params,
                "messages": payload,
                "stream": False,
                "timeout": settings.llm.request_timeout_seconds,
                "num_retries": settings.llm.max_retries,
                "metadata": self._build_metadata(metadata, tenant, conversation, spec.scene, spec.task_type),
            }
            if tool_payload:
                params["tools"] = tool_payload
                params["tool_choice"] = "auto"
            try:
                response = await acompletion(**params)
                self._mark_router_success(deployment_id)
                break
            except Exception as exc:
                self._mark_router_failure(deployment_id)
                mapped = self._map_provider_error(exc)
                last_error = mapped
                logger.warning(
                    "llm_complete_failed",
                    model=spec.model,
                    task_type=spec.task_type,
                    scene=spec.scene,
                    deployment_id=deployment_id,
                    tenant_id=tenant,
                    conversation_id=conversation,
                    trace_id=get_current_trace_id(),
                    thread_id=get_current_thread_id(),
                    latency_ms=int((perf_counter() - started) * 1000),
                    fallback=False,
                    error_code=mapped.code,
                    error_message=mapped.message,
                )
        if response is None:
            if last_error is not None:
                raise last_error
            raise LLMGatewayError("provider_call_failed", "no available llm deployment")
        choice = response.choices[0]
        usage = self._normalize_usage(getattr(response, "usage", {}))
        text = self._normalize_text(getattr(choice.message, "content", ""))
        finish_reason = str(getattr(choice, "finish_reason", "stop"))
        tool_calls = self._normalize_tool_calls(getattr(choice.message, "tool_calls", None))
        self._track_usage(tenant, conversation, usage)
        logger.info(
            "llm_complete",
            model=spec.model,
            task_type=spec.task_type,
            scene=spec.scene,
            deployment_id=deployment_id,
            tenant_id=tenant,
            conversation_id=conversation,
            trace_id=get_current_trace_id(),
            thread_id=get_current_thread_id(),
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            total_tokens=usage["total_tokens"],
            finish_reason=finish_reason,
            latency_ms=int((perf_counter() - started) * 1000),
            fallback=False,
        )
        result = LLMResult(
            text=text,
            usage=usage,
            finish_reason=finish_reason,
            model=spec.model,
            cached=bool(getattr(response, "cache_hit", False)),
            tool_calls=tool_calls,
        )
        if cache_key and not tool_calls:
            self._cache_set(cache_key, result, cache_ttl)
        return result

    async def stream(
        self,
        messages: list[Any],
        task_type: str = "complex",
        *,
        scene: str | None = None,
        tools: list[Any] | None = None,
        tenant_id: str | None = None,
        conversation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        self._ensure_provider_ready()
        started = perf_counter()
        tenant = str(tenant_id or get_current_tenant_id() or "unknown")
        conversation = str(conversation_id or get_current_conversation_id() or "")
        await self._check_budget(tenant, conversation)
        spec = select_model(task_type=task_type, scene=scene)
        payload = self._to_openai_messages(messages)
        tool_payload = self._to_openai_tools(list(tools or []))
        emitted_chars = 0
        candidates = self._provider_param_candidates(spec)
        attempt_limit = min(len(candidates), max(1, int(settings.llm.router_max_attempts)))
        stream_ok = False
        for idx in range(attempt_limit):
            deployment_id, provider_params = candidates[idx]
            params: dict[str, Any] = {
                **provider_params,
                "messages": payload,
                "stream": True,
                "timeout": settings.llm.request_timeout_seconds,
                "num_retries": settings.llm.max_retries,
                "metadata": self._build_metadata(metadata, tenant, conversation, spec.scene, spec.task_type),
            }
            if tool_payload:
                params["tools"] = tool_payload
                params["tool_choice"] = "auto"
            try:
                chunks = await acompletion(**params)
                async for chunk in chunks:
                    choice = chunk.choices[0]
                    delta = getattr(choice, "delta", None)
                    content = self._normalize_text(getattr(delta, "content", ""))
                    if content:
                        emitted_chars += len(content)
                        yield content
                self._mark_router_success(deployment_id)
                logger.info(
                    "llm_stream",
                    model=spec.model,
                    task_type=spec.task_type,
                    scene=spec.scene,
                    deployment_id=deployment_id,
                    tenant_id=tenant,
                    conversation_id=conversation,
                    trace_id=get_current_trace_id(),
                    thread_id=get_current_thread_id(),
                    emitted_chars=emitted_chars,
                    latency_ms=int((perf_counter() - started) * 1000),
                    fallback=False,
                )
                stream_ok = True
                break
            except Exception:
                self._mark_router_failure(deployment_id)
                continue
        if stream_ok:
            return
        logger.warning(
            "llm_stream_fallback",
            model=spec.model,
            task_type=spec.task_type,
            scene=spec.scene,
            tenant_id=tenant,
            conversation_id=conversation,
            trace_id=get_current_trace_id(),
            thread_id=get_current_thread_id(),
            emitted_chars=emitted_chars,
            latency_ms=int((perf_counter() - started) * 1000),
            fallback=True,
        )
        fallback = await self.complete(
            messages=messages,
            task_type=task_type,
            scene=scene,
            tools=tools,
            tenant_id=tenant,
            conversation_id=conversation,
            metadata=metadata,
        )
        if fallback.text:
            yield fallback.text

    async def get_tenant_usage(self, tenant_id: str) -> UsageSummary:
        raw = self._tenant_usage.get(str(tenant_id), {})
        return UsageSummary(
            tenant_id=str(tenant_id),
            prompt_tokens=int(raw.get("prompt_tokens", 0)),
            completion_tokens=int(raw.get("completion_tokens", 0)),
            total_tokens=int(raw.get("total_tokens", 0)),
        )

    async def reset_tenant_budget(self, tenant_id: str) -> None:
        self._tenant_usage.pop(str(tenant_id), None)

    async def _check_budget(self, tenant_id: str, conversation_id: str) -> None:
        tenant_budget = int(settings.llm.tenant_token_budget)
        if tenant_budget > 0:
            total = int(self._tenant_usage.get(tenant_id, {}).get("total_tokens", 0))
            if total >= tenant_budget:
                raise LLMGatewayError("tenant_budget_exceeded", "tenant token budget exceeded")
        conversation_budget = int(settings.llm.conversation_token_budget)
        if conversation_budget > 0 and conversation_id:
            used = int(self._conversation_usage.get(conversation_id, 0))
            if used >= conversation_budget:
                raise LLMGatewayError("conversation_budget_exceeded", "conversation token budget exceeded")

    def _ensure_provider_ready(self) -> None:
        if acompletion is None:
            raise LLMGatewayError("provider_not_ready", "litellm is not installed")

    def _map_provider_error(self, exc: Exception) -> LLMGatewayError:
        text = str(exc).lower()
        if "timeout" in text:
            return LLMGatewayError("provider_timeout", str(exc))
        if "rate" in text and "limit" in text:
            return LLMGatewayError("provider_rate_limited", str(exc))
        if "auth" in text or "api key" in text or "unauthorized" in text:
            return LLMGatewayError("provider_auth_failed", str(exc))
        return LLMGatewayError("provider_call_failed", str(exc))

    def _provider_params(self, spec: ModelSpec) -> dict[str, Any]:
        model = str(spec.model)
        provider = model.split("/", 1)[0] if "/" in model else "openai"
        params: dict[str, Any] = {"model": model}
        if provider == "openai" and settings.llm.openai_api_key:
            params["api_key"] = settings.llm.openai_api_key
        if provider == "anthropic" and settings.llm.anthropic_api_key:
            params["api_key"] = settings.llm.anthropic_api_key
        if provider == "ollama" and settings.llm.local_model_base_url:
            params["api_base"] = settings.llm.local_model_base_url
        return params

    def _provider_param_candidates(self, spec: ModelSpec) -> list[tuple[str, dict[str, Any]]]:
        base = self._provider_params(spec)
        deployments = self._router_deployments(str(spec.model))
        if not deployments:
            return [("default", base)]
        now = time()
        available = [d for d in deployments if now >= float(self._router_unhealthy_until.get(str(d.get("id", "")), 0))]
        if not available:
            available = deployments
        start = int(self._router_cursor.get(spec.model, 0))
        ordered = available[start:] + available[:start]
        self._router_cursor[spec.model] = (start + 1) % max(1, len(available))
        out: list[tuple[str, dict[str, Any]]] = []
        for item in ordered:
            deployment_id = str(item.get("id", "default"))
            params = dict(base)
            if item.get("model"):
                params["model"] = str(item["model"])
            if item.get("api_key"):
                params["api_key"] = str(item["api_key"])
            if item.get("api_base"):
                params["api_base"] = str(item["api_base"])
            out.append((deployment_id, params))
        out.append(("default", base))
        return out

    def _router_deployments(self, model: str) -> list[dict[str, Any]]:
        raw = str(settings.llm.router_deployments or "").strip()
        if raw == self._router_raw:
            return list(self._router_parsed.get(model, []))
        self._router_raw = raw
        parsed: dict[str, list[dict[str, Any]]] = {}
        if raw:
            try:
                data = json.loads(raw)
                if isinstance(data, Mapping):
                    for key, value in data.items():
                        if not isinstance(value, list):
                            continue
                        deployments: list[dict[str, Any]] = []
                        for idx, item in enumerate(value):
                            if not isinstance(item, Mapping):
                                continue
                            deployments.append(
                                {
                                    "id": str(item.get("id", f"{key}#{idx}")),
                                    "model": str(item.get("model", key)),
                                    "api_key": str(item.get("api_key", "")),
                                    "api_base": str(item.get("api_base", "")),
                                }
                            )
                        if deployments:
                            parsed[str(key)] = deployments
            except Exception:
                parsed = {}
        self._router_parsed = parsed
        return list(self._router_parsed.get(model, []))

    def _mark_router_failure(self, deployment_id: str) -> None:
        if deployment_id == "default":
            return
        cooldown = max(1, int(settings.llm.router_cooldown_seconds))
        self._router_unhealthy_until[deployment_id] = time() + float(cooldown)

    def _mark_router_success(self, deployment_id: str) -> None:
        if deployment_id == "default":
            return
        self._router_unhealthy_until.pop(deployment_id, None)

    def _to_openai_tools(self, tools: list[Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for tool in tools:
            if isinstance(tool, Mapping):
                out.append(dict(tool))
                continue
            try:
                out.append(dict(convert_to_openai_tool(tool)))
            except Exception:
                continue
        return out

    def _to_openai_messages(self, messages: list[Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for message in messages:
            converted = self._to_openai_message(message)
            if converted is not None:
                out.append(converted)
        return out

    def _to_openai_message(self, message: Any) -> dict[str, Any] | None:
        if isinstance(message, Mapping):
            role = str(message.get("role", "user"))
            content = self._normalize_text(message.get("content", ""))
            out: dict[str, Any] = {"role": role, "content": content}
            if "tool_call_id" in message:
                out["tool_call_id"] = str(message["tool_call_id"])
            if "tool_calls" in message:
                out["tool_calls"] = message["tool_calls"]
            return out
        if isinstance(message, SystemMessage):
            return {"role": "system", "content": self._normalize_text(message.content)}
        if isinstance(message, HumanMessage):
            return {"role": "user", "content": self._normalize_text(message.content)}
        if isinstance(message, ToolMessage):
            return {
                "role": "tool",
                "content": self._normalize_text(message.content),
                "tool_call_id": str(message.tool_call_id),
            }
        if isinstance(message, AIMessage):
            out = {"role": "assistant", "content": self._normalize_text(message.content)}
            if message.tool_calls:
                out["tool_calls"] = self._to_openai_tool_calls(message.tool_calls)
            return out
        if isinstance(message, BaseMessage):
            return {"role": "user", "content": self._normalize_text(message.content)}
        return None

    def _to_openai_tool_calls(self, tool_calls: list[Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for idx, call in enumerate(tool_calls):
            if isinstance(call, Mapping):
                name = str(call.get("name", ""))
                args = call.get("args", {})
                call_id = str(call.get("id", f"call_{idx}"))
            else:
                name = str(getattr(call, "name", ""))
                args = getattr(call, "args", {})
                call_id = str(getattr(call, "id", f"call_{idx}"))
            out.append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": json.dumps(args, ensure_ascii=False),
                    },
                }
            )
        return out

    def _normalize_tool_calls(self, raw_tool_calls: Any) -> list[dict[str, Any]]:
        if not raw_tool_calls:
            return []
        out: list[dict[str, Any]] = []
        for idx, call in enumerate(raw_tool_calls):
            func = getattr(call, "function", None)
            if func is None and isinstance(call, Mapping):
                func = call.get("function")
            name = getattr(func, "name", None) if func is not None else None
            if name is None and isinstance(func, Mapping):
                name = func.get("name")
            arguments = getattr(func, "arguments", None) if func is not None else None
            if arguments is None and isinstance(func, Mapping):
                arguments = func.get("arguments", "{}")
            args = self._loads_json(arguments)
            out.append(
                {
                    "id": str(getattr(call, "id", None) or (call.get("id") if isinstance(call, Mapping) else f"call_{idx}")),
                    "name": str(name or ""),
                    "args": args,
                    "type": "tool_call",
                }
            )
        return out

    def _normalize_usage(self, usage: Any) -> dict[str, int]:
        if isinstance(usage, Mapping):
            prompt_tokens = int(usage.get("prompt_tokens", 0))
            completion_tokens = int(usage.get("completion_tokens", 0))
            total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens))
            return {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0))
        completion_tokens = int(getattr(usage, "completion_tokens", 0))
        total_tokens = int(getattr(usage, "total_tokens", prompt_tokens + completion_tokens))
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }

    def _track_usage(self, tenant_id: str, conversation_id: str, usage: dict[str, int]) -> None:
        record = self._tenant_usage.setdefault(
            tenant_id, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        )
        record["prompt_tokens"] += int(usage["prompt_tokens"])
        record["completion_tokens"] += int(usage["completion_tokens"])
        record["total_tokens"] += int(usage["total_tokens"])
        if conversation_id:
            self._conversation_usage[conversation_id] = (
                int(self._conversation_usage.get(conversation_id, 0)) + int(usage["total_tokens"])
            )

    def _build_metadata(
        self,
        metadata: dict[str, Any] | None,
        tenant_id: str,
        conversation_id: str,
        scene: str | None,
        task_type: str,
    ) -> dict[str, Any]:
        base = dict(metadata or {})
        for key in (
            "cache",
            "caching",
            "cache_ttl",
            "cache_key",
            "cache_policy",
            "no_cache",
            "disable_cache",
        ):
            base.pop(key, None)
        base.setdefault("tenant_id", tenant_id)
        if conversation_id:
            base.setdefault("conversation_id", conversation_id)
        if scene:
            base.setdefault("scene", scene)
        base.setdefault("task_type", task_type)
        trace_id = get_current_trace_id()
        thread_id = get_current_thread_id()
        if trace_id:
            base.setdefault("trace_id", trace_id)
        if thread_id:
            base.setdefault("thread_id", thread_id)
        return base

    def _cache_ttl_seconds(self, scene: str | None, task_type: str) -> int:
        if not bool(settings.llm.cache_enabled):
            return 0
        if scene:
            scene_map = self._cache_scene_ttl_map()
            if scene in scene_map:
                return max(0, int(scene_map[scene]))
        task_map = self._cache_task_ttl_map()
        if task_type in task_map:
            return max(0, int(task_map[task_type]))
        return max(0, int(settings.llm.cache_default_ttl_seconds))

    def _cache_scene_ttl_map(self) -> dict[str, int]:
        raw = str(settings.llm.cache_scene_ttl or "").strip()
        if raw == self._cache_scene_raw:
            return dict(self._cache_scene_map)
        self._cache_scene_raw = raw
        self._cache_scene_map = self._loads_int_map(raw)
        return dict(self._cache_scene_map)

    def _cache_task_ttl_map(self) -> dict[str, int]:
        raw = str(settings.llm.cache_task_ttl or "").strip()
        if raw == self._cache_task_raw:
            return dict(self._cache_task_map)
        self._cache_task_raw = raw
        self._cache_task_map = self._loads_int_map(raw)
        return dict(self._cache_task_map)

    def _loads_int_map(self, raw: str) -> dict[str, int]:
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            if not isinstance(data, Mapping):
                return {}
            out: dict[str, int] = {}
            for key, value in data.items():
                out[str(key)] = max(0, int(value))
            return out
        except Exception:
            return {}

    def _cache_key(self, spec: ModelSpec, tenant_id: str, payload: list[dict[str, Any]]) -> str:
        raw = json.dumps(
            {
                "tenant_id": tenant_id,
                "model": spec.model,
                "task_type": spec.task_type,
                "scene": spec.scene,
                "messages": payload,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return raw

    def _cache_get(self, key: str) -> LLMResult | None:
        record = self._cache_data.get(key)
        if record is None:
            return None
        expires_at, result = record
        if time() > expires_at:
            self._cache_data.pop(key, None)
            return None
        return LLMResult(
            text=result.text,
            usage=dict(result.usage),
            finish_reason=result.finish_reason,
            model=result.model,
            cached=True,
            tool_calls=list(result.tool_calls or []),
        )

    def _cache_set(self, key: str, result: LLMResult, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        max_entries = max(1, int(settings.llm.cache_max_entries))
        if len(self._cache_data) >= max_entries:
            oldest_key = next(iter(self._cache_data.keys()), "")
            if oldest_key:
                self._cache_data.pop(oldest_key, None)
        self._cache_data[key] = (
            time() + float(ttl_seconds),
            LLMResult(
                text=result.text,
                usage=dict(result.usage),
                finish_reason=result.finish_reason,
                model=result.model,
                cached=True,
                tool_calls=list(result.tool_calls or []),
            ),
        )

    def _normalize_text(self, content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, Mapping) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif isinstance(item, str):
                    parts.append(item)
            return "".join(parts)
        return str(content)

    def _loads_json(self, raw: Any) -> dict[str, Any]:
        if isinstance(raw, Mapping):
            return dict(raw)
        if not raw:
            return {}
        try:
            data = json.loads(str(raw))
            if isinstance(data, Mapping):
                return dict(data)
        except Exception:
            return {}
        return {}


llm_gateway = LLMGateway()
