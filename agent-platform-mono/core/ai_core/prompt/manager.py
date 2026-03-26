from __future__ import annotations
import os
from typing import Any, Dict
from pathlib import Path
from shared.config.settings import settings
from core.ai_core.prompt.provider import (
    PromptProvider,
    LangfusePromptProvider,
    LocalFilePromptProvider,
)


class PromptManager:
    def __init__(self):
        self._cache: Dict[str, str] = {}
        self._providers: list[PromptProvider] = [
            LangfusePromptProvider(),
            LocalFilePromptProvider(),
        ]

    def _render(self, tpl: str, variables: Dict[str, Any] | None) -> str:
        if not variables:
            return tpl
        return tpl.format(**variables)

    def get(self, name: str, variables: Dict[str, Any] | None = None, version: str | None = None) -> str:
        key = f"{name}:{version or 'latest'}"
        if key in self._cache:
            return self._render(self._cache[key], variables)
        content = None
        for p in self._providers:
            content = p.get(name, version)
            if content:
                break
        if content is None:
            raise FileNotFoundError(f"prompt not found: {name}")
        self._cache[key] = content
        return self._render(content, variables)


prompt_manager = PromptManager()
