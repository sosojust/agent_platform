from __future__ import annotations

import json
from collections import defaultdict, deque
from collections.abc import Mapping
from threading import Lock
from typing import Any, cast

from redis import Redis

try:
    from opentelemetry import metrics
except Exception:
    metrics = None  # type: ignore[assignment]

from shared.config.settings import settings


class MetricsGateway:
    def __init__(self) -> None:
        self._lock = Lock()
        self._recent_limit = max(
            1,
            int(
                settings.get(
                    "observability_subagent_recent_limit",
                    getattr(settings, "observability_subagent_recent_limit", 20),
                )
            ),
        )
        self._recent_batches: deque[dict[str, Any]] = deque(maxlen=self._recent_limit)
        self._recent_aggregations: deque[dict[str, Any]] = deque(maxlen=self._recent_limit)
        self._summary = {
            "batch_count": 0,
            "task_count": 0,
            "success_count": 0,
            "error_count": 0,
            "batch_duration_ms_total": 0,
            "aggregation_duration_ms_total": 0,
        }
        self._scoped_summary: dict[str, dict[str, int]] = defaultdict(
            lambda: {
                "batch_count": 0,
                "task_count": 0,
                "success_count": 0,
                "error_count": 0,
                "batch_duration_ms_total": 0,
                "aggregation_duration_ms_total": 0,
            }
        )
        self._backend = str(
            settings.get(
                "observability_subagent_backend",
                getattr(settings, "observability_subagent_backend", "memory"),
            )
        ).lower()
        self._redis_prefix = str(
            settings.get(
                "observability_subagent_redis_prefix",
                getattr(settings, "observability_subagent_redis_prefix", "agent_platform:subagent_metrics"),
            )
        )
        self._redis_ttl = int(getattr(settings.redis, "checkpoint_ttl", 86400))
        self._redis_client: Redis | None = None
        self._batch_counter = None
        self._task_counter = None
        self._batch_duration_histogram = None
        self._aggregation_duration_histogram = None
        if metrics is not None:
            meter = metrics.get_meter("agent_platform.subagents")
            self._batch_counter = meter.create_counter("subagent_batch_total")
            self._task_counter = meter.create_counter("subagent_task_total")
            self._batch_duration_histogram = meter.create_histogram("subagent_batch_duration_ms")
            self._aggregation_duration_histogram = meter.create_histogram(
                "subagent_aggregation_duration_ms"
            )

    def record_batch(self, payload: Mapping[str, Any]) -> None:
        normalized = _normalize_payload(payload)
        task_count = int(payload.get("task_count", 0))
        success_count = int(payload.get("success_count", 0))
        error_count = int(payload.get("error_count", 0))
        batch_duration_ms = int(payload.get("batch_duration_ms", 0))
        with self._lock:
            self._summary["batch_count"] += 1
            self._summary["task_count"] += task_count
            self._summary["success_count"] += success_count
            self._summary["error_count"] += error_count
            self._summary["batch_duration_ms_total"] += batch_duration_ms
            self._recent_batches.appendleft(dict(normalized))
            for scope_key in _scope_keys(normalized):
                scoped = self._scoped_summary[scope_key]
                scoped["batch_count"] += 1
                scoped["task_count"] += task_count
                scoped["success_count"] += success_count
                scoped["error_count"] += error_count
                scoped["batch_duration_ms_total"] += batch_duration_ms
        attributes = _attributes(normalized)
        if self._batch_counter is not None:
            self._batch_counter.add(1, attributes=attributes)
        if self._task_counter is not None:
            self._task_counter.add(task_count, attributes=attributes)
        if self._batch_duration_histogram is not None:
            self._batch_duration_histogram.record(batch_duration_ms, attributes=attributes)
        self._record_batch_redis(normalized)

    def record_aggregation(self, payload: Mapping[str, Any]) -> None:
        normalized = _normalize_payload(payload)
        aggregation_duration_ms = int(payload.get("aggregation_duration_ms", 0))
        with self._lock:
            self._summary["aggregation_duration_ms_total"] += aggregation_duration_ms
            self._recent_aggregations.appendleft(dict(normalized))
            for scope_key in _scope_keys(normalized):
                scoped = self._scoped_summary[scope_key]
                scoped["aggregation_duration_ms_total"] += aggregation_duration_ms
        attributes = _attributes(normalized)
        if self._aggregation_duration_histogram is not None:
            self._aggregation_duration_histogram.record(aggregation_duration_ms, attributes=attributes)
        self._record_aggregation_redis(normalized)

    def snapshot(self, *, tenant_id: str = "", parent_agent_id: str = "") -> dict[str, Any]:
        if self._backend == "redis":
            redis_snapshot = self._snapshot_from_redis(tenant_id=tenant_id, parent_agent_id=parent_agent_id)
            if redis_snapshot is not None:
                return redis_snapshot
        with self._lock:
            scope = _scope_key(tenant_id=tenant_id, parent_agent_id=parent_agent_id)
            scoped = dict(
                self._scoped_summary.get(
                    scope,
                    {
                        "batch_count": 0,
                        "task_count": 0,
                        "success_count": 0,
                        "error_count": 0,
                        "batch_duration_ms_total": 0,
                        "aggregation_duration_ms_total": 0,
                    },
                )
            )
            if scope == "global":
                scoped = dict(self._summary)
            batch_count = int(scoped["batch_count"])
            recent_batches = _filter_recent(
                entries=list(self._recent_batches),
                tenant_id=tenant_id,
                parent_agent_id=parent_agent_id,
            )
            recent_aggregations = _filter_recent(
                entries=list(self._recent_aggregations),
                tenant_id=tenant_id,
                parent_agent_id=parent_agent_id,
            )
            aggregation_count = len(recent_aggregations)
            avg_batch_duration_ms = scoped["batch_duration_ms_total"] / batch_count if batch_count else 0.0
            avg_aggregation_duration_ms = (
                scoped["aggregation_duration_ms_total"] / aggregation_count if aggregation_count else 0.0
            )
            return {
                "summary": {
                    **dict(scoped),
                    "avg_batch_duration_ms": avg_batch_duration_ms,
                    "avg_aggregation_duration_ms": avg_aggregation_duration_ms,
                },
                "recent_batches": recent_batches,
                "recent_aggregations": recent_aggregations,
                "storage_backend": "memory",
            }

    def reset(self) -> None:
        with self._lock:
            self._recent_batches.clear()
            self._recent_aggregations.clear()
            self._scoped_summary.clear()
            for key in list(self._summary):
                self._summary[key] = 0
        self._reset_redis()

    def _redis(self) -> Redis | None:
        if self._backend != "redis":
            return None
        if self._redis_client is not None:
            return self._redis_client
        try:
            client = Redis.from_url(settings.redis.url, decode_responses=True)
            cast(Any, client).ping()
            self._redis_client = client
            return self._redis_client
        except Exception:
            self._redis_client = None
            return None

    def _record_batch_redis(self, payload: Mapping[str, Any]) -> None:
        client = self._redis()
        if client is None:
            return
        task_count = int(payload.get("task_count", 0))
        success_count = int(payload.get("success_count", 0))
        error_count = int(payload.get("error_count", 0))
        batch_duration_ms = int(payload.get("batch_duration_ms", 0))
        for scope in _scope_keys(payload):
            summary_key = f"{self._redis_prefix}:summary:{scope}"
            recent_key = f"{self._redis_prefix}:recent_batches:{scope}"
            entry = json.dumps(dict(payload), ensure_ascii=False)
            try:
                pipeline = cast(Any, client).pipeline(transaction=False)
                pipeline.hincrby(summary_key, "batch_count", 1)
                pipeline.hincrby(summary_key, "task_count", task_count)
                pipeline.hincrby(summary_key, "success_count", success_count)
                pipeline.hincrby(summary_key, "error_count", error_count)
                pipeline.hincrby(summary_key, "batch_duration_ms_total", batch_duration_ms)
                pipeline.lpush(recent_key, entry)
                pipeline.ltrim(recent_key, 0, self._recent_limit - 1)
                pipeline.expire(summary_key, self._redis_ttl)
                pipeline.expire(recent_key, self._redis_ttl)
                pipeline.execute()
            except Exception:
                self._redis_client = None
                return

    def _record_aggregation_redis(self, payload: Mapping[str, Any]) -> None:
        client = self._redis()
        if client is None:
            return
        aggregation_duration_ms = int(payload.get("aggregation_duration_ms", 0))
        for scope in _scope_keys(payload):
            summary_key = f"{self._redis_prefix}:summary:{scope}"
            recent_key = f"{self._redis_prefix}:recent_aggregations:{scope}"
            entry = json.dumps(dict(payload), ensure_ascii=False)
            try:
                pipeline = cast(Any, client).pipeline(transaction=False)
                pipeline.hincrby(summary_key, "aggregation_duration_ms_total", aggregation_duration_ms)
                pipeline.lpush(recent_key, entry)
                pipeline.ltrim(recent_key, 0, self._recent_limit - 1)
                pipeline.expire(summary_key, self._redis_ttl)
                pipeline.expire(recent_key, self._redis_ttl)
                pipeline.execute()
            except Exception:
                self._redis_client = None
                return

    def _snapshot_from_redis(self, *, tenant_id: str, parent_agent_id: str) -> dict[str, Any] | None:
        client = self._redis()
        if client is None:
            return None
        scope = _scope_key(tenant_id=tenant_id, parent_agent_id=parent_agent_id)
        summary_key = f"{self._redis_prefix}:summary:{scope}"
        recent_batch_key = f"{self._redis_prefix}:recent_batches:{scope}"
        recent_aggregation_key = f"{self._redis_prefix}:recent_aggregations:{scope}"
        try:
            summary_raw = cast(dict[str, Any], cast(Any, client).hgetall(summary_key))
            if not summary_raw and scope != "global":
                return {
                    "summary": {
                        "batch_count": 0,
                        "task_count": 0,
                        "success_count": 0,
                        "error_count": 0,
                        "batch_duration_ms_total": 0,
                        "aggregation_duration_ms_total": 0,
                        "avg_batch_duration_ms": 0.0,
                        "avg_aggregation_duration_ms": 0.0,
                    },
                    "recent_batches": [],
                    "recent_aggregations": [],
                    "storage_backend": "redis",
                }
            summary: dict[str, Any] = {
                "batch_count": int(summary_raw.get("batch_count", 0)),
                "task_count": int(summary_raw.get("task_count", 0)),
                "success_count": int(summary_raw.get("success_count", 0)),
                "error_count": int(summary_raw.get("error_count", 0)),
                "batch_duration_ms_total": int(summary_raw.get("batch_duration_ms_total", 0)),
                "aggregation_duration_ms_total": int(summary_raw.get("aggregation_duration_ms_total", 0)),
            }
            recent_batches = [
                _safe_load_json(str(item))
                for item in cast(list[Any], cast(Any, client).lrange(recent_batch_key, 0, -1))
            ]
            recent_aggregations = [
                _safe_load_json(str(item))
                for item in cast(list[Any], cast(Any, client).lrange(recent_aggregation_key, 0, -1))
            ]
            batch_count = summary["batch_count"]
            aggregation_count = len(recent_aggregations)
            summary["avg_batch_duration_ms"] = (
                summary["batch_duration_ms_total"] / batch_count if batch_count else 0.0
            )
            summary["avg_aggregation_duration_ms"] = (
                summary["aggregation_duration_ms_total"] / aggregation_count if aggregation_count else 0.0
            )
            return {
                "summary": summary,
                "recent_batches": recent_batches,
                "recent_aggregations": recent_aggregations,
                "storage_backend": "redis",
            }
        except Exception:
            self._redis_client = None
            return None

    def _reset_redis(self) -> None:
        client = self._redis()
        if client is None:
            return
        try:
            cursor = 0
            pattern = f"{self._redis_prefix}:*"
            while True:
                cursor, keys = cast(tuple[int, list[str]], cast(Any, client).scan(cursor=cursor, match=pattern, count=200))
                if keys:
                    cast(Any, client).delete(*keys)
                if cursor == 0:
                    break
        except Exception:
            self._redis_client = None


def _safe_load_json(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    except Exception:
        return {}


def _normalize_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["tenant_id"] = str(payload.get("tenant_id", ""))
    normalized["parent_agent_id"] = str(payload.get("parent_agent_id", ""))
    normalized["strategy"] = str(payload.get("strategy", ""))
    return normalized


def _scope_key(*, tenant_id: str, parent_agent_id: str) -> str:
    if tenant_id and parent_agent_id:
        return f"tenant_agent:{tenant_id}:{parent_agent_id}"
    if tenant_id:
        return f"tenant:{tenant_id}"
    if parent_agent_id:
        return f"agent:{parent_agent_id}"
    return "global"


def _scope_keys(payload: Mapping[str, Any]) -> list[str]:
    tenant_id = str(payload.get("tenant_id", ""))
    parent_agent_id = str(payload.get("parent_agent_id", ""))
    scopes = ["global"]
    if tenant_id:
        scopes.append(_scope_key(tenant_id=tenant_id, parent_agent_id=""))
    if parent_agent_id:
        scopes.append(_scope_key(tenant_id="", parent_agent_id=parent_agent_id))
    if tenant_id and parent_agent_id:
        scopes.append(_scope_key(tenant_id=tenant_id, parent_agent_id=parent_agent_id))
    return scopes


def _filter_recent(
    *,
    entries: list[dict[str, Any]],
    tenant_id: str,
    parent_agent_id: str,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for entry in entries:
        if tenant_id and str(entry.get("tenant_id", "")) != tenant_id:
            continue
        if parent_agent_id and str(entry.get("parent_agent_id", "")) != parent_agent_id:
            continue
        filtered.append(entry)
    return filtered


def _attributes(payload: Mapping[str, Any]) -> dict[str, str]:
    return {
        "tenant_id": str(payload.get("tenant_id", "")),
        "parent_agent_id": str(payload.get("parent_agent_id", "")),
        "strategy": str(payload.get("strategy", "")),
    }


metrics_gateway = MetricsGateway()
