from types import SimpleNamespace
from typing import Any
import pytest

from core.ai_core.llm import client as llm_client_module
from core.ai_core.llm.client import LLMGateway, LLMResult
from shared.config.settings import settings


async def test_complete_uses_scene_model_and_tracks_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = LLMGateway()
    captured: list[dict[str, Any]] = []
    old_nano = settings.llm.nano_model
    try:
        settings.llm.nano_model = "openai/test-nano-model"

        async def _fake_acompletion(**kwargs: Any) -> Any:
            captured.append(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="ok", tool_calls=[]),
                        finish_reason="stop",
                    )
                ],
                usage={"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
                cache_hit=False,
            )

        monkeypatch.setattr(llm_client_module, "acompletion", _fake_acompletion)
        result = await gateway.complete(
            messages=[{"role": "user", "content": "hi"}],
            scene="policy_rag_rewrite",
            tenant_id="tenant-a",
            conversation_id="conv-a",
        )
        usage = await gateway.get_tenant_usage("tenant-a")
        assert result.text == "ok"
        assert result.model == "openai/test-nano-model"
        assert captured[0]["model"] == "openai/test-nano-model"
        assert usage.total_tokens == 5
        assert gateway._conversation_usage["conv-a"] == 5
    finally:
        settings.llm.nano_model = old_nano


async def test_stream_fallback_to_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = LLMGateway()

    async def _fail_acompletion(**kwargs: Any) -> Any:
        raise RuntimeError("stream failed")

    async def _fake_complete(
        messages: list[Any],
        task_type: str = "complex",
        scene: str | None = None,
        tools: list[Any] | None = None,
        tenant_id: str | None = None,
        conversation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LLMResult:
        return LLMResult(
            text="fallback-content",
            usage={"prompt_tokens": 0, "completion_tokens": 1, "total_tokens": 1},
            finish_reason="stop",
            model="openai/gpt-4o-mini",
            cached=False,
            tool_calls=[],
        )

    monkeypatch.setattr(llm_client_module, "acompletion", _fail_acompletion)
    monkeypatch.setattr(gateway, "complete", _fake_complete)
    chunks = [
        chunk
        async for chunk in gateway.stream(
            messages=[{"role": "user", "content": "test"}],
            tenant_id="tenant-b",
            conversation_id="conv-b",
        )
    ]
    assert chunks == ["fallback-content"]
