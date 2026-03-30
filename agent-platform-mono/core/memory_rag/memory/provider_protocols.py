from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass
class CompressionRequest:
    messages: list[Mapping[str, Any]]
    max_turns: int
    keep_recent: int = 6
    token_threshold: int = 0
    model_name: str = ""


@dataclass
class CompressionResult:
    messages: list[dict[str, Any]]
    applied: bool
    strategy: str
    metrics: dict[str, int] = field(default_factory=dict)


class MessageFilter(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def apply(self, messages: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
        raise NotImplementedError


class MessageCompressor(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def compress(self, request: CompressionRequest) -> CompressionResult:
        raise NotImplementedError


class TokenizerProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def count_text(self, text: str, model_name: str = "") -> int:
        raise NotImplementedError

    @abstractmethod
    def count_messages(self, messages: list[Mapping[str, Any]], model_name: str = "") -> int:
        raise NotImplementedError


class LongTermExtractor(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def extract(
        self,
        messages: list[Mapping[str, Any]],
        tenant_id: str,
        conversation_id: str,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError
