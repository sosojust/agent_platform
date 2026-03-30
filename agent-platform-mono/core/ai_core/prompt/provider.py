from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional
from pathlib import Path
from shared.config.settings import settings

try:
    from langfuse import Langfuse
except Exception:
    Langfuse = None  # type: ignore


class PromptProvider(ABC):
    @abstractmethod
    def get(self, name: str, version: str | None = None) -> Optional[str]:
        ...


class LangfusePromptProvider(PromptProvider):
    def __init__(self):
        self._lf = None
        if Langfuse and settings.observability.langfuse_host and settings.observability.langfuse_public_key and settings.observability.langfuse_secret_key:
            try:
                self._lf = Langfuse(
                    host=settings.observability.langfuse_host,
                    public_key=settings.observability.langfuse_public_key,
                    secret_key=settings.observability.langfuse_secret_key,
                )
            except Exception:
                self._lf = None

    def get(self, name: str, version: str | None = None) -> Optional[str]:
        if not self._lf:
            return None
        try:
            p = self._lf.get_prompt(name=name, version=version) if version else self._lf.get_prompt(name=name)
            if not p or not getattr(p, "prompt", None):
                return None
            return str(p.prompt)
        except Exception:
            return None


class LocalFilePromptProvider(PromptProvider):
    def _local_path(self, name: str) -> Path:
        base = Path(__file__).resolve().parents[3]
        if name.endswith("_system"):
            domain = name.split("_")[0]
            return base / "domain_agents" / domain / "prompts" / "system.txt"
        return base / "core" / "ai_core" / "prompt" / f"{name}.txt"

    def get(self, name: str, version: str | None = None) -> Optional[str]:
        path = self._local_path(name)
        if not path.exists():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return None
