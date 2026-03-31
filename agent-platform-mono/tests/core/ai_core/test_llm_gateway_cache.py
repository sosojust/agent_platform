from core.ai_core.llm.client import LLMGateway, LLMResult
from shared.config.nacos import _apply_config
from shared.config.settings import settings


def test_build_metadata_strips_cache_flags() -> None:
    gateway = LLMGateway()
    out = gateway._build_metadata(
        {
            "cache": True,
            "caching": True,
            "cache_ttl": 10,
            "cache_key": "k",
            "cache_policy": "x",
            "no_cache": False,
            "disable_cache": False,
            "biz": "ok",
        },
        tenant_id="t1",
        conversation_id="c1",
        scene="policy_query",
        task_type="simple",
    )
    assert "cache" not in out
    assert "caching" not in out
    assert "cache_ttl" not in out
    assert "cache_key" not in out
    assert "cache_policy" not in out
    assert "no_cache" not in out
    assert "disable_cache" not in out
    assert out["biz"] == "ok"
    assert out["tenant_id"] == "t1"
    assert out["conversation_id"] == "c1"
    assert out["scene"] == "policy_query"
    assert out["task_type"] == "simple"


def test_cache_ttl_policy_priority() -> None:
    gateway = LLMGateway()
    old_enabled = settings.llm.cache_enabled
    old_default = settings.llm.cache_default_ttl_seconds
    old_scene = settings.llm.cache_scene_ttl
    old_task = settings.llm.cache_task_ttl
    try:
        settings.llm.cache_enabled = True
        settings.llm.cache_default_ttl_seconds = 11
        settings.llm.cache_scene_ttl = '{"policy_query": 120}'
        settings.llm.cache_task_ttl = '{"simple": 30}'
        assert gateway._cache_ttl_seconds("policy_query", "simple") == 120
        assert gateway._cache_ttl_seconds("unknown_scene", "simple") == 30
        assert gateway._cache_ttl_seconds("unknown_scene", "complex") == 11
        settings.llm.cache_enabled = False
        assert gateway._cache_ttl_seconds("policy_query", "simple") == 0
    finally:
        settings.llm.cache_enabled = old_enabled
        settings.llm.cache_default_ttl_seconds = old_default
        settings.llm.cache_scene_ttl = old_scene
        settings.llm.cache_task_ttl = old_task


def test_cache_set_get_roundtrip() -> None:
    gateway = LLMGateway()
    old_max = settings.llm.cache_max_entries
    try:
        settings.llm.cache_max_entries = 2
        result = LLMResult(
            text="ok",
            usage={"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            finish_reason="stop",
            model="openai/gpt-4o-mini",
            cached=False,
            tool_calls=[],
        )
        gateway._cache_set("k1", result, 60)
        cached = gateway._cache_get("k1")
        assert cached is not None
        assert cached.text == "ok"
        assert cached.cached is True
    finally:
        settings.llm.cache_max_entries = old_max


def test_nacos_apply_model_and_cache_config() -> None:
    old_medium = settings.llm.medium_model
    old_nano = settings.llm.nano_model
    old_local = settings.llm.local_model
    old_cache_enabled = settings.llm.cache_enabled
    old_cache_default = settings.llm.cache_default_ttl_seconds
    old_cache_scene = settings.llm.cache_scene_ttl
    old_cache_task = settings.llm.cache_task_ttl
    old_cache_max = settings.llm.cache_max_entries
    try:
        _apply_config(
            settings,
            {
                "llm_medium_model": "openai/gpt-4o-mini",
                "llm_nano_model": "openai/gpt-4.1-nano",
                "llm_local_model": "ollama/qwen2.5",
                "llm_cache_enabled": True,
                "llm_cache_default_ttl_seconds": 25,
                "llm_cache_scene_ttl": {"policy_query": 60},
                "llm_cache_task_ttl": {"simple": 15},
                "llm_cache_max_entries": 100,
            },
        )
        assert settings.llm.medium_model == "openai/gpt-4o-mini"
        assert settings.llm.nano_model == "openai/gpt-4.1-nano"
        assert settings.llm.local_model == "ollama/qwen2.5"
        assert settings.llm.cache_enabled is True
        assert settings.llm.cache_default_ttl_seconds == 25
        assert settings.llm.cache_scene_ttl == '{"policy_query": 60}'
        assert settings.llm.cache_task_ttl == '{"simple": 15}'
        assert settings.llm.cache_max_entries == 100
    finally:
        settings.llm.medium_model = old_medium
        settings.llm.nano_model = old_nano
        settings.llm.local_model = old_local
        settings.llm.cache_enabled = old_cache_enabled
        settings.llm.cache_default_ttl_seconds = old_cache_default
        settings.llm.cache_scene_ttl = old_cache_scene
        settings.llm.cache_task_ttl = old_cache_task
        settings.llm.cache_max_entries = old_cache_max
