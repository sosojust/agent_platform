from __future__ import annotations
from typing import Any, Callable, Dict, Optional, Awaitable
from core.tool_service.registry import tool_gateway


def skill(
    name: Optional[str] = None,
    input_schema: Optional[Dict[str, Any]] = None,
    output_schema: Optional[Dict[str, Any]] = None,
):
    def decorator(func: Callable[[Dict[str, Any]], Any | Awaitable[Any]]):
        reg_name = name or func.__name__
        tool_gateway.register_skill(
            reg_name,
            func,
            input_schema=input_schema,
            output_schema=output_schema,
            provider="skill",
        )
        return func

    return decorator
