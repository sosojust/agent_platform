from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Tuple


class LLMProvider(ABC):
    @abstractmethod
    async def complete(
        self,
        messages: List[Dict[str, Any]] | str,
        **kwargs: Any,
    ) -> Tuple[str, Dict[str, int]]:
        ...

    @abstractmethod
    async def stream(
        self,
        messages: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        ...
