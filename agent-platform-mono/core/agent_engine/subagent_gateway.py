from __future__ import annotations

import asyncio
import inspect
from time import perf_counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

from langchain_core.callbacks.manager import adispatch_custom_event
from langchain_core.messages import HumanMessage
from langchain_core.runnables.config import RunnableConfig

from core.agent_engine.agents.registry import AgentRegistry, agent_gateway
from core.agent_engine.checkpoints.redis_checkpoint import get_checkpointer
from core.agent_engine.workflows.state import make_initial_state
from shared.config.settings import settings
from shared.logging.logger import get_logger
from shared.middleware.tenant import set_current_conversation_id, set_current_thread_id
from shared.observability.metrics_gateway import metrics_gateway

logger = get_logger(__name__)


@dataclass(slots=True, frozen=True)
class SubagentTask:
    agent_id: str
    user_input: str
    task_id: str = ""
    conversation_id: str | None = None
    shared_context: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SubagentResult:
    task_id: str
    agent_id: str
    conversation_id: str
    status: Literal["success", "error"]
    output: str
    step_count: int
    mode: str
    error: str = ""
    duration_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "conversation_id": self.conversation_id,
            "status": self.status,
            "output": self.output,
            "step_count": self.step_count,
            "mode": self.mode,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }


SubagentTaskBuilder: TypeAlias = Callable[
    [Mapping[str, Any]],
    Sequence[SubagentTask] | Awaitable[Sequence[SubagentTask]],
]
SharedContextBuilder: TypeAlias = Callable[[Mapping[str, Any]], str]


class SubagentGateway:
    def __init__(self, registry: AgentRegistry | None = None) -> None:
        self._registry = registry or agent_gateway

    def build_child_thread_id(self, parent_conversation_id: str, task: SubagentTask) -> str:
        if task.conversation_id:
            return task.conversation_id
        suffix = task.task_id or task.agent_id
        return f"{parent_conversation_id}:{suffix}"

    async def run_batch(
        self,
        tasks: Sequence[SubagentTask],
        *,
        tenant_id: str,
        parent_conversation_id: str,
        parent_agent_id: str = "",
        shared_context: str = "",
        checkpointer: Any | None = None,
        max_concurrency: int | None = None,
        timeout_seconds: float | None = None,
        event_config: RunnableConfig | None = None,
    ) -> list[SubagentResult]:
        if not tasks:
            return []

        batch_started_at = perf_counter()
        resolved_checkpointer = checkpointer if checkpointer is not None else await get_checkpointer()
        concurrency = max(
            1,
            int(max_concurrency or settings.orch_subagent_max_concurrency),
        )
        timeout = float(timeout_seconds or settings.orch_subagent_timeout_seconds)
        semaphore = asyncio.Semaphore(concurrency)
        await _emit_custom_event(
            "subagent.batch.started",
            {
                "parent_conversation_id": parent_conversation_id,
                "parent_agent_id": parent_agent_id,
                "tenant_id": tenant_id,
                "task_count": len(tasks),
                "max_concurrency": concurrency,
                "timeout_seconds": timeout,
            },
            config=event_config,
        )

        async def _guarded(task: SubagentTask) -> SubagentResult:
            async with semaphore:
                return await self._run_single(
                    task=task,
                    tenant_id=tenant_id,
                    parent_conversation_id=parent_conversation_id,
                    parent_agent_id=parent_agent_id,
                    shared_context=shared_context,
                    checkpointer=resolved_checkpointer,
                    timeout_seconds=timeout,
                    event_config=event_config,
                )

        results = list(await asyncio.gather(*(_guarded(task) for task in tasks)))
        batch_duration_ms = int((perf_counter() - batch_started_at) * 1000)
        success_count = sum(1 for result in results if result.status == "success")
        error_count = len(results) - success_count
        logger.info(
            "subagent_batch_completed",
            tenant_id=tenant_id,
            parent_conversation_id=parent_conversation_id,
            parent_agent_id=parent_agent_id,
            task_count=len(tasks),
            success_count=success_count,
            error_count=error_count,
            batch_duration_ms=batch_duration_ms,
        )
        metrics_gateway.record_batch(
            {
                "tenant_id": tenant_id,
                "parent_conversation_id": parent_conversation_id,
                "parent_agent_id": parent_agent_id,
                "task_count": len(tasks),
                "success_count": success_count,
                "error_count": error_count,
                "batch_duration_ms": batch_duration_ms,
            }
        )
        await _emit_custom_event(
            "subagent.batch.completed",
            {
                "parent_conversation_id": parent_conversation_id,
                "parent_agent_id": parent_agent_id,
                "tenant_id": tenant_id,
                "task_count": len(tasks),
                "success_count": success_count,
                "error_count": error_count,
                "batch_duration_ms": batch_duration_ms,
            },
            config=event_config,
        )
        return results

    async def _run_single(
        self,
        *,
        task: SubagentTask,
        tenant_id: str,
        parent_conversation_id: str,
        parent_agent_id: str,
        shared_context: str,
        checkpointer: Any,
        timeout_seconds: float,
        event_config: RunnableConfig | None = None,
    ) -> SubagentResult:
        started_at = perf_counter()
        task_id = task.task_id or task.agent_id
        conversation_id = self.build_child_thread_id(parent_conversation_id, task)
        await _emit_custom_event(
            "subagent.task.started",
            {
                "task_id": task_id,
                "agent_id": task.agent_id,
                "conversation_id": conversation_id,
                "parent_conversation_id": parent_conversation_id,
                "parent_agent_id": parent_agent_id,
            },
            config=event_config,
        )
        meta = self._registry.get(task.agent_id)
        if meta is None:
            duration_ms = int((perf_counter() - started_at) * 1000)
            await _emit_custom_event(
                "subagent.task.failed",
                {
                    "task_id": task_id,
                    "agent_id": task.agent_id,
                    "conversation_id": conversation_id,
                    "parent_conversation_id": parent_conversation_id,
                    "error": f"Agent '{task.agent_id}' not found",
                    "duration_ms": duration_ms,
                },
                config=event_config,
            )
            return SubagentResult(
                task_id=task_id,
                agent_id=task.agent_id,
                conversation_id=conversation_id,
                status="error",
                output="",
                step_count=0,
                mode="unknown",
                error=f"Agent '{task.agent_id}' not found",
                duration_ms=duration_ms,
                metadata=dict(task.metadata),
            )

        user_input = self._compose_input(shared_context, task.shared_context, task.user_input)
        initial_state = make_initial_state(
            messages=[HumanMessage(content=user_input)],
            conversation_id=conversation_id,
            tenant_id=tenant_id,
        )
        initial_state["metadata"] = {
            "parent_conversation_id": parent_conversation_id,
            "parent_agent_id": parent_agent_id,
            "task_id": task_id,
            **task.metadata,
        }
        set_current_conversation_id(conversation_id)
        set_current_thread_id(conversation_id)
        from core.agent_engine.orchestrator_factory import build_orchestrator

        agent, mode = build_orchestrator(
            meta=meta,
            tenant_id=tenant_id,
            user_input=user_input,
            state=initial_state,
        )
        config = {"configurable": {"thread_id": conversation_id, "checkpointer": checkpointer}}

        try:
            result = await asyncio.wait_for(
                agent.ainvoke(initial_state, config=config),
                timeout=max(timeout_seconds, 0.1),
            )
        except asyncio.TimeoutError:
            duration_ms = int((perf_counter() - started_at) * 1000)
            logger.warning(
                "subagent_timeout",
                agent_id=task.agent_id,
                conversation_id=conversation_id,
                parent_conversation_id=parent_conversation_id,
                duration_ms=duration_ms,
            )
            await _emit_custom_event(
                "subagent.task.timeout",
                {
                    "task_id": task_id,
                    "agent_id": task.agent_id,
                    "conversation_id": conversation_id,
                    "parent_conversation_id": parent_conversation_id,
                    "duration_ms": duration_ms,
                },
                config=event_config,
            )
            return SubagentResult(
                task_id=task_id,
                agent_id=task.agent_id,
                conversation_id=conversation_id,
                status="error",
                output="",
                step_count=0,
                mode=mode,
                error="subagent execution timed out",
                duration_ms=duration_ms,
                metadata=dict(task.metadata),
            )
        except Exception as exc:
            duration_ms = int((perf_counter() - started_at) * 1000)
            logger.error(
                "subagent_failed",
                agent_id=task.agent_id,
                conversation_id=conversation_id,
                parent_conversation_id=parent_conversation_id,
                error=str(exc),
                duration_ms=duration_ms,
            )
            await _emit_custom_event(
                "subagent.task.failed",
                {
                    "task_id": task_id,
                    "agent_id": task.agent_id,
                    "conversation_id": conversation_id,
                    "parent_conversation_id": parent_conversation_id,
                    "error": str(exc),
                    "duration_ms": duration_ms,
                },
                config=event_config,
            )
            return SubagentResult(
                task_id=task_id,
                agent_id=task.agent_id,
                conversation_id=conversation_id,
                status="error",
                output="",
                step_count=0,
                mode=mode,
                error=str(exc),
                duration_ms=duration_ms,
                metadata=dict(task.metadata),
            )

        last_message = result["messages"][-1]
        duration_ms = int((perf_counter() - started_at) * 1000)
        logger.info(
            "subagent_task_completed",
            agent_id=task.agent_id,
            conversation_id=conversation_id,
            parent_conversation_id=parent_conversation_id,
            step_count=int(result.get("step_count", 0)),
            duration_ms=duration_ms,
            mode=mode,
        )
        await _emit_custom_event(
            "subagent.task.completed",
            {
                "task_id": task_id,
                "agent_id": task.agent_id,
                "conversation_id": conversation_id,
                "parent_conversation_id": parent_conversation_id,
                "duration_ms": duration_ms,
                "mode": mode,
                "step_count": int(result.get("step_count", 0)),
            },
            config=event_config,
        )
        return SubagentResult(
            task_id=task_id,
            agent_id=task.agent_id,
            conversation_id=conversation_id,
            status="success",
            output=str(last_message.content),
            step_count=int(result.get("step_count", 0)),
            mode=mode,
            duration_ms=duration_ms,
            metadata=dict(task.metadata),
        )

    def _compose_input(self, parent_context: str, task_context: str, user_input: str) -> str:
        parts: list[str] = []
        if parent_context.strip():
            parts.append(f"父任务上下文：\n{parent_context.strip()}")
        if task_context.strip():
            parts.append(f"子任务补充上下文：\n{task_context.strip()}")
        parts.append(f"子任务请求：\n{user_input.strip()}")
        return "\n\n".join(parts)


def _default_shared_context(state: Mapping[str, Any]) -> str:
    parts = [str(state.get("memory_context", "")).strip(), str(state.get("rag_context", "")).strip()]
    return "\n\n".join(part for part in parts if part)


async def _emit_custom_event(
    name: str,
    data: Mapping[str, Any],
    *,
    config: RunnableConfig | None = None,
) -> None:
    try:
        await adispatch_custom_event(name, dict(data), config=config)
    except Exception:
        # Swallow all dispatch errors (RuntimeError when no handler is registered,
        # serialization failures, etc.) to avoid breaking the calling chain.
        logger.debug("custom_event_dispatch_failed", event_name=name)
        return


def make_subagent_executor_node(
    build_tasks: SubagentTaskBuilder,
    *,
    result_key: str = "subagent_results",
    shared_context_builder: SharedContextBuilder | None = None,
    gateway: SubagentGateway | None = None,
    max_concurrency: int | None = None,
    timeout_seconds: float | None = None,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    runtime_gateway = gateway or subagent_gateway

    async def node(state: Mapping[str, Any], config: RunnableConfig | None = None) -> dict[str, Any]:
        maybe_tasks = build_tasks(state)
        resolved_tasks = await maybe_tasks if inspect.isawaitable(maybe_tasks) else maybe_tasks
        tasks = list(resolved_tasks)
        if not tasks:
            return {result_key: []}
        shared_context = (
            shared_context_builder(state)
            if shared_context_builder is not None
            else _default_shared_context(state)
        )
        results = await runtime_gateway.run_batch(
            tasks,
            tenant_id=str(state.get("tenant_id", "unknown")),
            parent_conversation_id=str(state.get("conversation_id", "")),
            parent_agent_id=str((state.get("metadata") or {}).get("agent_id", "")),
            shared_context=shared_context,
            max_concurrency=max_concurrency,
            timeout_seconds=timeout_seconds,
            event_config=config,
        )
        return {result_key: [result.as_dict() for result in results]}

    return node


subagent_gateway = SubagentGateway()
