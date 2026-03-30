from __future__ import annotations

from typing import Any, Iterable, Mapping

from core.memory_rag.memory.provider_protocols import MessageFilter


DEFAULT_NOISE_TEXTS = {
    "嗯",
    "哦",
    "好的",
    "收到",
    "了解",
    "谢谢",
    "好的谢谢",
}


def normalize_content(content: str) -> str:
    return " ".join(content.strip().split())


class NoiseFilter(MessageFilter):
    def __init__(self, noise_texts: Iterable[str] = DEFAULT_NOISE_TEXTS, min_compact_len: int = 1) -> None:
        self._noise_texts = {str(item) for item in noise_texts}
        self._min_compact_len = int(min_compact_len)

    @property
    def name(self) -> str:
        return "noise_filter"

    def is_noise(self, content: str) -> bool:
        compact = content.replace(" ", "")
        if len(compact) <= self._min_compact_len:
            return True
        return compact in self._noise_texts

    def apply(self, messages: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for message in messages:
            role = str(message.get("role", ""))
            content = normalize_content(str(message.get("content", "")))
            if not content:
                continue
            if self.is_noise(content):
                continue
            out.append({"role": role, "content": content})
        return out


class DuplicateRecentFilter(MessageFilter):
    def __init__(self, window_size: int = 6) -> None:
        self._window_size = max(1, int(window_size))

    @property
    def name(self) -> str:
        return "duplicate_recent_filter"

    def is_duplicate(
        self,
        role: str,
        content: str,
        recent_messages: Iterable[Mapping[str, Any]],
    ) -> bool:
        items = list(recent_messages)[-self._window_size :]
        for msg in reversed(items):
            old_role = str(msg.get("role", ""))
            old_content = normalize_content(str(msg.get("content", "")))
            if old_role == role and old_content == content:
                return True
        return False

    def apply(self, messages: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for message in messages:
            role = str(message.get("role", ""))
            content = normalize_content(str(message.get("content", "")))
            if not content:
                continue
            if self.is_duplicate(role=role, content=content, recent_messages=out):
                continue
            out.append({"role": role, "content": content})
        return out


FILTER_REGISTRY: dict[str, type[MessageFilter]] = {
    "noise": NoiseFilter,
    "duplicate_recent": DuplicateRecentFilter,
}


def build_filters(strategy_names: list[str]) -> list[MessageFilter]:
    filters: list[MessageFilter] = []
    for name in strategy_names:
        cls = FILTER_REGISTRY.get(str(name))
        if cls is None:
            continue
        filters.append(cls())
    return filters
