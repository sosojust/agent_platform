from __future__ import annotations
from typing import Any, Awaitable, Callable, TypeVar
from core.tool_service.registry import tool_gateway

F = TypeVar("F", bound=Callable[[dict[str, Any]], Any | Awaitable[Any]])


def skill(
    name: str | None = None,
    input_schema: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
) -> Callable[[F], F]:
    def decorator(func: F) -> F:
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
