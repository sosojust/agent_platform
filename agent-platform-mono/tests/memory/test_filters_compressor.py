from core.memory_rag.memory.compressor import (
    CharacterTokenizerProvider,
    ShortTermWindowCompressor,
    SimpleSummaryCompressor,
    build_compressor,
    build_tokenizer,
)
from core.memory_rag.memory.provider_protocols import CompressionRequest
from core.memory_rag.memory.filters import DuplicateRecentFilter, NoiseFilter, normalize_content


def test_normalize_content() -> None:
    assert normalize_content("  查询   保单   状态 ") == "查询 保单 状态"


def test_noise_filter() -> None:
    f = NoiseFilter()
    assert f.is_noise("好的")
    assert not f.is_noise("请帮我查询保单状态")


def test_duplicate_recent_filter() -> None:
    f = DuplicateRecentFilter(window_size=6)
    recent = [
        {"role": "user", "content": "我要查询保单"},
        {"role": "assistant", "content": "请提供保单号"},
    ]
    assert f.is_duplicate("user", "我要查询保单", recent)
    assert not f.is_duplicate("user", "我要查询理赔", recent)


def test_short_term_window_compressor() -> None:
    compressor = ShortTermWindowCompressor()
    assert compressor.trim_start(current_length=25, max_turns=20) == 5
    assert compressor.trim_start(current_length=10, max_turns=20) == 0


async def test_simple_summary_compressor() -> None:
    compressor = SimpleSummaryCompressor()
    request = CompressionRequest(
        messages=[
            {"role": "user", "content": "我是王五"},
            {"role": "assistant", "content": "好的"},
            {"role": "user", "content": "我想咨询理赔进度"},
            {"role": "assistant", "content": "请提供理赔单号"},
        ],
        max_turns=2,
        keep_recent=2,
    )
    result = await compressor.compress(request)
    assert result.applied is True
    assert result.strategy == "simple_summary"
    assert result.messages[0]["role"] == "system"
    assert "历史摘要" in str(result.messages[0]["content"])
    assert len(result.messages) == 3


def test_build_compressor_and_tokenizer_defaults() -> None:
    compressor = build_compressor("window")
    assert compressor.name == "window"
    tokenizer = build_tokenizer("char")
    assert isinstance(tokenizer, CharacterTokenizerProvider)
    assert tokenizer.count_messages([{"role": "user", "content": "abc"}]) >= 3
