from __future__ import annotations
from shared.config.settings import settings


def select_model(task_type: str) -> tuple[str, str]:
    if task_type == "simple":
        m = settings.llm.default_model
    elif task_type == "local":
        m = settings.llm.default_model
    else:
        m = settings.llm.strong_model
    if "/" in m:
        provider, name = m.split("/", 1)
        return provider, name
    return "openai", m
