from __future__ import annotations
from typing import Any, List, Dict
from langchain_openai import ChatOpenAI
from core.ai_core.routing.router import select_model
from shared.config.settings import settings


class LLMClient:
    def get_chat(self, tools: List[Any], task_type: str = "complex") -> Any:
        provider, model_name = select_model(task_type)
        api_key = settings.llm.openai_api_key if provider == "openai" else ""
        llm = ChatOpenAI(model=model_name, api_key=api_key, streaming=True).bind_tools(tools)
        return llm


llm_client = LLMClient()
