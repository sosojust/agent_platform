from __future__ import annotations

from typing import Any, Mapping

from core.ai_core.llm.client import llm_gateway
from core.memory_rag.memory.provider_protocols import (
    CompressionRequest,
    CompressionResult,
    MessageCompressor,
    TokenizerProvider,
)
from core.memory_rag.memory.filters import normalize_content


class CharacterTokenizerProvider(TokenizerProvider):
    @property
    def name(self) -> str:
        return "char"

    def count_text(self, text: str, model_name: str = "") -> int:
        return len(str(text))

    def count_messages(self, messages: list[Mapping[str, Any]], model_name: str = "") -> int:
        total = 0
        for message in messages:
            total += self.count_text(str(message.get("content", "")), model_name=model_name)
            total += 4
        return total + 2


class TiktokenTokenizerProvider(TokenizerProvider):
    @property
    def name(self) -> str:
        return "tiktoken"

    def count_text(self, text: str, model_name: str = "") -> int:
        encoding = self._encoding(model_name=model_name)
        return len(encoding.encode(str(text)))

    def count_messages(self, messages: list[Mapping[str, Any]], model_name: str = "") -> int:
        total = 0
        for message in messages:
            total += self.count_text(str(message.get("content", "")), model_name=model_name)
            total += 4
        return total + 2

    def _encoding(self, model_name: str) -> Any:
        import tiktoken

        model = str(model_name or "gpt-4o-mini")
        try:
            return tiktoken.encoding_for_model(model)
        except Exception:
            return tiktoken.get_encoding("cl100k_base")


class ShortTermWindowCompressor(MessageCompressor):
    @property
    def name(self) -> str:
        return "window"

    def trim_start(self, current_length: int, max_turns: int) -> int:
        return max(0, int(current_length) - max(0, int(max_turns)))

    def compress_messages(self, messages: list[Mapping[str, Any]], max_turns: int) -> list[dict[str, Any]]:
        limit = max(0, int(max_turns))
        if limit == 0:
            return []
        return [dict(item) for item in messages[-limit:]]

    async def compress(self, request: CompressionRequest) -> CompressionResult:
        out = self.compress_messages(request.messages, request.max_turns)
        return CompressionResult(
            messages=out,
            applied=len(out) < len(request.messages),
            strategy=self.name,
            metrics={"before_count": len(request.messages), "after_count": len(out)},
        )


class SimpleSummaryCompressor(MessageCompressor):
    @property
    def name(self) -> str:
        return "simple_summary"

    async def compress(self, request: CompressionRequest) -> CompressionResult:
        max_turns = max(0, int(request.max_turns))
        if len(request.messages) <= max_turns:
            out = [dict(item) for item in request.messages]
            return CompressionResult(
                messages=out,
                applied=False,
                strategy=self.name,
                metrics={"before_count": len(out), "after_count": len(out)},
            )
        keep_recent = max(1, int(request.keep_recent))
        recent = [dict(item) for item in request.messages[-keep_recent:]]
        old = request.messages[: max(0, len(request.messages) - keep_recent)]
        parts: list[str] = []
        for message in old:
            role = str(message.get("role", ""))
            content = normalize_content(str(message.get("content", "")))
            if not content:
                continue
            parts.append(f"{role}: {content}")
        summary_text = "；".join(parts[:12])
        summary = {"role": "system", "content": f"[历史摘要]{summary_text}" if summary_text else "[历史摘要]"}
        out = [summary] + recent
        return CompressionResult(
            messages=out,
            applied=True,
            strategy=self.name,
            metrics={"before_count": len(request.messages), "after_count": len(out)},
        )


class LLMSummaryCompressor(MessageCompressor):
    def __init__(self, task_type: str = "simple") -> None:
        self._task_type = str(task_type)
        self._fallback = SimpleSummaryCompressor()

    @property
    def name(self) -> str:
        return "llm_summary"

    async def compress(self, request: CompressionRequest) -> CompressionResult:
        max_turns = max(0, int(request.max_turns))
        if len(request.messages) <= max_turns:
            out = [dict(item) for item in request.messages]
            return CompressionResult(
                messages=out,
                applied=False,
                strategy=self.name,
                metrics={"before_count": len(out), "after_count": len(out)},
            )
        keep_recent = max(1, int(request.keep_recent))
        old = request.messages[: max(0, len(request.messages) - keep_recent)]
        recent = [dict(item) for item in request.messages[-keep_recent:]]
        text = self._as_transcript(old)
        try:
            llm = llm_gateway.get_chat([], task_type=self._task_type)
            resp = await llm.ainvoke(
                [
                    {
                        "role": "system",
                        "content": "请将对话历史压缩为简洁中文摘要，保留事实、偏好、约束、待办，不要输出无关说明。",
                    },
                    {"role": "user", "content": text},
                ]
            )
            summary_text = normalize_content(str(getattr(resp, "content", "")))
            if not summary_text:
                return await self._fallback.compress(request)
            out = [{"role": "system", "content": f"[历史摘要]{summary_text}"}] + recent
            return CompressionResult(
                messages=out,
                applied=True,
                strategy=self.name,
                metrics={"before_count": len(request.messages), "after_count": len(out)},
            )
        except Exception:
            return await self._fallback.compress(request)

    def _as_transcript(self, messages: list[Mapping[str, Any]]) -> str:
        lines: list[str] = []
        for message in messages:
            role = str(message.get("role", ""))
            content = normalize_content(str(message.get("content", "")))
            if not content:
                continue
            lines.append(f"{role}: {content}")
        return "\n".join(lines)


TOKENIZER_REGISTRY: dict[str, type[TokenizerProvider]] = {
    "char": CharacterTokenizerProvider,
    "tiktoken": TiktokenTokenizerProvider,
}

COMPRESSOR_REGISTRY: dict[str, type[MessageCompressor]] = {
    "window": ShortTermWindowCompressor,
    "simple_summary": SimpleSummaryCompressor,
    "llm_summary": LLMSummaryCompressor,
}


def build_tokenizer(provider_name: str) -> TokenizerProvider:
    name = str(provider_name or "char")
    cls = TOKENIZER_REGISTRY.get(name) or CharacterTokenizerProvider
    if cls is TiktokenTokenizerProvider:
        try:
            return cls()
        except Exception:
            return CharacterTokenizerProvider()
    return cls()


def build_compressor(strategy_name: str) -> MessageCompressor:
    raw = str(strategy_name or "window")
    name, _, arg = raw.partition(":")
    cls = COMPRESSOR_REGISTRY.get(name) or ShortTermWindowCompressor
    if cls is LLMSummaryCompressor:
        task_type = str(arg or "simple")
        return LLMSummaryCompressor(task_type=task_type)
    return cls()
