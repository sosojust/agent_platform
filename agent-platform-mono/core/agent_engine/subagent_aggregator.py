from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

SubagentAggregationStrategy: TypeAlias = Literal[
    "summary",
    "priority",
    "vote",
    "confidence_rank",
    "conflict_resolution",
]


@dataclass(slots=True)
class AggregatedSubagentResult:
    strategy: SubagentAggregationStrategy
    final_output: str
    success_count: int
    error_count: int
    partial_failure: bool
    conflict_detected: bool = False
    selected_agent_ids: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    failed_agents: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "final_output": self.final_output,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "partial_failure": self.partial_failure,
            "conflict_detected": self.conflict_detected,
            "selected_agent_ids": self.selected_agent_ids,
            "sources": self.sources,
            "failed_agents": self.failed_agents,
            "metadata": self.metadata,
        }


def aggregate_subagent_results(
    results: Sequence[Mapping[str, Any]],
    *,
    strategy: SubagentAggregationStrategy = "summary",
    preferred_agent_ids: Sequence[str] | None = None,
    min_confidence: float = 0.0,
    conflict_resolution_template: str = (
        "检测到子 Agent 结论存在冲突，已按置信度排序给出建议：\n{ranked_candidates}\n"
        "建议采用 {selected_agent_id} 的结果（confidence={selected_confidence:.2f}）"
    ),
) -> AggregatedSubagentResult:
    success_results = [result for result in results if str(result.get("status", "")) == "success"]
    error_results = [result for result in results if str(result.get("status", "")) != "success"]
    success_agents = [str(result.get("agent_id", "")) for result in success_results]
    failed_agents = [str(result.get("agent_id", "")) for result in error_results]

    if strategy == "priority":
        return _aggregate_priority(
            success_results,
            error_results,
            preferred_agent_ids=preferred_agent_ids or (),
        )
    if strategy == "vote":
        return _aggregate_vote(success_results, error_results)
    if strategy == "confidence_rank":
        return _aggregate_confidence_rank(
            success_results,
            error_results,
            min_confidence=min_confidence,
        )
    if strategy == "conflict_resolution":
        return _aggregate_conflict_resolution(
            success_results,
            error_results,
            min_confidence=min_confidence,
            conflict_resolution_template=conflict_resolution_template,
        )

    final_output = _build_summary_text(success_results, error_results)
    return AggregatedSubagentResult(
        strategy="summary",
        final_output=final_output,
        success_count=len(success_results),
        error_count=len(error_results),
        partial_failure=bool(success_results) and bool(error_results),
        conflict_detected=_has_conflict(success_results),
        selected_agent_ids=success_agents,
        sources=success_agents,
        failed_agents=failed_agents,
    )


def _aggregate_priority(
    success_results: Sequence[Mapping[str, Any]],
    error_results: Sequence[Mapping[str, Any]],
    *,
    preferred_agent_ids: Sequence[str],
) -> AggregatedSubagentResult:
    selected_result: Mapping[str, Any] | None = None
    if success_results:
        prioritized_ids = [str(agent_id) for agent_id in preferred_agent_ids]
        for preferred_agent_id in prioritized_ids:
            selected_result = next(
                (
                    result
                    for result in success_results
                    if str(result.get("agent_id", "")) == preferred_agent_id
                ),
                None,
            )
            if selected_result is not None:
                break
        if selected_result is None:
            selected_result = success_results[0]

    if selected_result is None:
        final_output = _build_summary_text(success_results, error_results)
        return AggregatedSubagentResult(
            strategy="priority",
            final_output=final_output,
            success_count=0,
            error_count=len(error_results),
            partial_failure=False,
            conflict_detected=False,
            failed_agents=[str(result.get("agent_id", "")) for result in error_results],
            metadata={"selected_by": "fallback_summary"},
        )

    selected_agent_id = str(selected_result.get("agent_id", ""))
    selected_output = str(selected_result.get("output", "")).strip()
    note = _build_failure_note(error_results)
    final_output = selected_output if not note else f"{selected_output}\n\n{note}"
    return AggregatedSubagentResult(
        strategy="priority",
        final_output=final_output,
        success_count=len(success_results),
        error_count=len(error_results),
        partial_failure=bool(error_results),
        conflict_detected=_has_conflict(success_results),
        selected_agent_ids=[selected_agent_id],
        sources=[str(result.get("agent_id", "")) for result in success_results],
        failed_agents=[str(result.get("agent_id", "")) for result in error_results],
        metadata={"selected_by": "preferred_order", "selected_agent_id": selected_agent_id},
    )


def _aggregate_vote(
    success_results: Sequence[Mapping[str, Any]],
    error_results: Sequence[Mapping[str, Any]],
) -> AggregatedSubagentResult:
    if not success_results:
        return AggregatedSubagentResult(
            strategy="vote",
            final_output=_build_summary_text(success_results, error_results),
            success_count=0,
            error_count=len(error_results),
            partial_failure=False,
            failed_agents=[str(result.get("agent_id", "")) for result in error_results],
            metadata={"vote_winner_count": 0, "vote_total": 0},
        )

    groups: dict[str, list[Mapping[str, Any]]] = {}
    for result in success_results:
        output = str(result.get("output", "")).strip()
        groups.setdefault(output, []).append(result)

    ranked_groups = sorted(
        groups.items(),
        key=lambda item: (
            len(item[1]),
            sum(_extract_confidence(result) for result in item[1]),
        ),
        reverse=True,
    )
    winning_output, winning_results = ranked_groups[0]
    winning_agent_ids = [str(result.get("agent_id", "")) for result in winning_results]
    tie_count = sum(1 for _, group in ranked_groups if len(group) == len(winning_results))
    note = _build_failure_note(error_results)
    final_output = winning_output if not note else f"{winning_output}\n\n{note}"
    return AggregatedSubagentResult(
        strategy="vote",
        final_output=final_output,
        success_count=len(success_results),
        error_count=len(error_results),
        partial_failure=bool(error_results),
        conflict_detected=len(groups) > 1,
        selected_agent_ids=winning_agent_ids,
        sources=[str(result.get("agent_id", "")) for result in success_results],
        failed_agents=[str(result.get("agent_id", "")) for result in error_results],
        metadata={
            "vote_winner_count": len(winning_results),
            "vote_total": len(success_results),
            "tie_detected": tie_count > 1,
        },
    )


def _aggregate_confidence_rank(
    success_results: Sequence[Mapping[str, Any]],
    error_results: Sequence[Mapping[str, Any]],
    *,
    min_confidence: float,
) -> AggregatedSubagentResult:
    selected_result = _select_highest_confidence(success_results)
    if selected_result is None:
        return AggregatedSubagentResult(
            strategy="confidence_rank",
            final_output=_build_summary_text(success_results, error_results),
            success_count=0,
            error_count=len(error_results),
            partial_failure=False,
            failed_agents=[str(result.get("agent_id", "")) for result in error_results],
            metadata={"selected_confidence": 0.0},
        )

    selected_agent_id = str(selected_result.get("agent_id", ""))
    selected_confidence = _extract_confidence(selected_result)
    if selected_confidence < float(min_confidence):
        summary = _build_summary_text(success_results, error_results)
        return AggregatedSubagentResult(
            strategy="confidence_rank",
            final_output=summary,
            success_count=len(success_results),
            error_count=len(error_results),
            partial_failure=bool(error_results),
            conflict_detected=_has_conflict(success_results),
            selected_agent_ids=[],
            sources=[str(result.get("agent_id", "")) for result in success_results],
            failed_agents=[str(result.get("agent_id", "")) for result in error_results],
            metadata={"selected_confidence": selected_confidence, "below_threshold": True},
        )
    final_output = str(selected_result.get("output", "")).strip()
    note = _build_failure_note(error_results)
    if note:
        final_output = f"{final_output}\n\n{note}"
    return AggregatedSubagentResult(
        strategy="confidence_rank",
        final_output=final_output,
        success_count=len(success_results),
        error_count=len(error_results),
        partial_failure=bool(error_results),
        conflict_detected=_has_conflict(success_results),
        selected_agent_ids=[selected_agent_id],
        sources=[str(result.get("agent_id", "")) for result in success_results],
        failed_agents=[str(result.get("agent_id", "")) for result in error_results],
        metadata={"selected_confidence": selected_confidence, "selected_agent_id": selected_agent_id},
    )


def _aggregate_conflict_resolution(
    success_results: Sequence[Mapping[str, Any]],
    error_results: Sequence[Mapping[str, Any]],
    *,
    min_confidence: float,
    conflict_resolution_template: str,
) -> AggregatedSubagentResult:
    if not success_results:
        return AggregatedSubagentResult(
            strategy="conflict_resolution",
            final_output=_build_summary_text(success_results, error_results),
            success_count=0,
            error_count=len(error_results),
            partial_failure=False,
            failed_agents=[str(result.get("agent_id", "")) for result in error_results],
        )

    if not _has_conflict(success_results):
        summary = _build_summary_text(success_results, error_results)
        return AggregatedSubagentResult(
            strategy="conflict_resolution",
            final_output=summary,
            success_count=len(success_results),
            error_count=len(error_results),
            partial_failure=bool(error_results),
            conflict_detected=False,
            selected_agent_ids=[str(result.get("agent_id", "")) for result in success_results],
            sources=[str(result.get("agent_id", "")) for result in success_results],
            failed_agents=[str(result.get("agent_id", "")) for result in error_results],
            metadata={"resolved_by": "no_conflict"},
        )

    selected_result = _select_highest_confidence(success_results) or success_results[0]
    selected_agent_id = str(selected_result.get("agent_id", ""))
    selected_confidence = _extract_confidence(selected_result)
    ranked_lines: list[str] = []
    for result in sorted(success_results, key=_extract_confidence, reverse=True):
        agent_id = str(result.get("agent_id", ""))
        output = str(result.get("output", "")).strip()
        confidence = _extract_confidence(result)
        ranked_lines.append(f"- {agent_id}（confidence={confidence:.2f}）: {output}")
    template = conflict_resolution_template or (
        "检测到子 Agent 结论存在冲突，已按置信度排序给出建议：\n{ranked_candidates}\n"
        "建议采用 {selected_agent_id} 的结果（confidence={selected_confidence:.2f}）"
    )
    resolution_text = template.format(
        ranked_candidates="\n".join(ranked_lines),
        selected_agent_id=selected_agent_id,
        selected_confidence=selected_confidence,
        min_confidence=min_confidence,
    )
    if selected_confidence < float(min_confidence):
        resolution_text = (
            f"{resolution_text}\n当前最高置信度 {selected_confidence:.2f} 低于阈值 {float(min_confidence):.2f}"
        )
    lines = [resolution_text]
    failure_note = _build_failure_note(error_results)
    if failure_note:
        lines.append(failure_note)
    return AggregatedSubagentResult(
        strategy="conflict_resolution",
        final_output="\n".join(lines),
        success_count=len(success_results),
        error_count=len(error_results),
        partial_failure=bool(error_results),
        conflict_detected=True,
        selected_agent_ids=[selected_agent_id],
        sources=[str(result.get("agent_id", "")) for result in success_results],
        failed_agents=[str(result.get("agent_id", "")) for result in error_results],
        metadata={
            "resolved_by": "highest_confidence",
            "selected_agent_id": selected_agent_id,
            "selected_confidence": selected_confidence,
        },
    )


def _build_summary_text(
    success_results: Sequence[Mapping[str, Any]],
    error_results: Sequence[Mapping[str, Any]],
) -> str:
    if not success_results and not error_results:
        return "没有可用的子 Agent 执行结果。"

    lines: list[str] = []
    for result in success_results:
        agent_id = str(result.get("agent_id", ""))
        output = str(result.get("output", "")).strip()
        lines.append(f"{agent_id}: {output}")

    failure_note = _build_failure_note(error_results)
    if failure_note:
        lines.append(failure_note)

    return "\n".join(line for line in lines if line)


def _extract_confidence(result: Mapping[str, Any]) -> float:
    raw = result.get("confidence", None)
    if raw is None:
        raw = (result.get("metadata") or {}).get("confidence", 0.0)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _select_highest_confidence(
    success_results: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    if not success_results:
        return None
    return max(success_results, key=_extract_confidence)


def _has_conflict(success_results: Sequence[Mapping[str, Any]]) -> bool:
    # NOTE: Conflict detection uses exact string deduplication after stripping whitespace.
    # Two outputs that are semantically equivalent but worded differently will be treated
    # as conflicting. This is an intentional approximation — semantic similarity comparison
    # (e.g. via embedding_gateway) is tracked as a future improvement (P2).
    normalized_outputs = {
        str(result.get("output", "")).strip()
        for result in success_results
        if str(result.get("output", "")).strip()
    }
    return len(normalized_outputs) > 1


def _build_failure_note(error_results: Sequence[Mapping[str, Any]]) -> str:
    if not error_results:
        return ""
    failed_items = [
        f"{result.get('agent_id', '')}（{str(result.get('error', 'unknown error')).strip() or 'unknown error'}）"
        for result in error_results
    ]
    return f"失败子 Agent: {'；'.join(failed_items)}"
