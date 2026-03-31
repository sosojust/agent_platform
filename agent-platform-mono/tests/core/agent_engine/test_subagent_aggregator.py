from core.agent_engine.subagent_aggregator import aggregate_subagent_results


def test_aggregate_subagent_results_summary_tracks_success_and_failure() -> None:
    aggregated = aggregate_subagent_results(
        [
            {"agent_id": "policy-assistant", "status": "success", "output": "保单状态正常"},
            {"agent_id": "claim-assistant", "status": "success", "output": "理赔处理中"},
            {"agent_id": "customer-assistant", "status": "error", "error": "timeout"},
        ]
    )

    assert aggregated.strategy == "summary"
    assert aggregated.success_count == 2
    assert aggregated.error_count == 1
    assert aggregated.partial_failure is True
    assert aggregated.selected_agent_ids == ["policy-assistant", "claim-assistant"]
    assert aggregated.failed_agents == ["customer-assistant"]
    assert "policy-assistant: 保单状态正常" in aggregated.final_output
    assert "失败子 Agent: customer-assistant（timeout）" in aggregated.final_output


def test_aggregate_subagent_results_priority_prefers_configured_agent() -> None:
    aggregated = aggregate_subagent_results(
        [
            {"agent_id": "policy-assistant", "status": "success", "output": "保单状态正常"},
            {"agent_id": "claim-assistant", "status": "success", "output": "理赔处理中"},
            {"agent_id": "customer-assistant", "status": "error", "error": "unavailable"},
        ],
        strategy="priority",
        preferred_agent_ids=["claim-assistant", "policy-assistant"],
    )

    assert aggregated.strategy == "priority"
    assert aggregated.selected_agent_ids == ["claim-assistant"]
    assert aggregated.metadata["selected_agent_id"] == "claim-assistant"
    assert aggregated.final_output.startswith("理赔处理中")
    assert "失败子 Agent: customer-assistant（unavailable）" in aggregated.final_output


def test_aggregate_subagent_results_vote_selects_majority_output() -> None:
    aggregated = aggregate_subagent_results(
        [
            {"agent_id": "policy-assistant", "status": "success", "output": "建议通过"},
            {"agent_id": "claim-assistant", "status": "success", "output": "建议通过"},
            {"agent_id": "risk-assistant", "status": "success", "output": "建议拒绝"},
        ],
        strategy="vote",
    )

    assert aggregated.strategy == "vote"
    assert aggregated.final_output == "建议通过"
    assert aggregated.selected_agent_ids == ["policy-assistant", "claim-assistant"]
    assert aggregated.conflict_detected is True
    assert aggregated.metadata["vote_winner_count"] == 2


def test_aggregate_subagent_results_confidence_rank_uses_highest_confidence() -> None:
    aggregated = aggregate_subagent_results(
        [
            {
                "agent_id": "policy-assistant",
                "status": "success",
                "output": "保单信息可信",
                "metadata": {"confidence": 0.61},
            },
            {
                "agent_id": "claim-assistant",
                "status": "success",
                "output": "理赔结论更可信",
                "metadata": {"confidence": 0.93},
            },
        ],
        strategy="confidence_rank",
    )

    assert aggregated.strategy == "confidence_rank"
    assert aggregated.selected_agent_ids == ["claim-assistant"]
    assert aggregated.metadata["selected_confidence"] == 0.93
    assert aggregated.final_output == "理赔结论更可信"


def test_aggregate_subagent_results_conflict_resolution_emits_resolution_text() -> None:
    aggregated = aggregate_subagent_results(
        [
            {
                "agent_id": "policy-assistant",
                "status": "success",
                "output": "建议通过",
                "metadata": {"confidence": 0.72},
            },
            {
                "agent_id": "claim-assistant",
                "status": "success",
                "output": "建议拒绝",
                "metadata": {"confidence": 0.88},
            },
        ],
        strategy="conflict_resolution",
    )

    assert aggregated.strategy == "conflict_resolution"
    assert aggregated.conflict_detected is True
    assert aggregated.selected_agent_ids == ["claim-assistant"]
    assert "检测到子 Agent 结论存在冲突" in aggregated.final_output
    assert "建议采用 claim-assistant 的结果" in aggregated.final_output


def test_aggregate_subagent_results_confidence_rank_respects_threshold() -> None:
    aggregated = aggregate_subagent_results(
        [
            {
                "agent_id": "policy-assistant",
                "status": "success",
                "output": "建议通过",
                "metadata": {"confidence": 0.41},
            },
            {
                "agent_id": "claim-assistant",
                "status": "success",
                "output": "建议拒绝",
                "metadata": {"confidence": 0.48},
            },
        ],
        strategy="confidence_rank",
        min_confidence=0.8,
    )

    assert aggregated.strategy == "confidence_rank"
    assert aggregated.selected_agent_ids == []
    assert aggregated.metadata["below_threshold"] is True


def test_aggregate_subagent_results_conflict_resolution_uses_custom_template() -> None:
    aggregated = aggregate_subagent_results(
        [
            {
                "agent_id": "policy-assistant",
                "status": "success",
                "output": "建议通过",
                "metadata": {"confidence": 0.72},
            },
            {
                "agent_id": "claim-assistant",
                "status": "success",
                "output": "建议拒绝",
                "metadata": {"confidence": 0.88},
            },
        ],
        strategy="conflict_resolution",
        conflict_resolution_template="候选如下：\n{ranked_candidates}\n最终选择 {selected_agent_id}",
    )

    assert aggregated.final_output.startswith("候选如下：")
    assert "最终选择 claim-assistant" in aggregated.final_output
