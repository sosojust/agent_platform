# core/tool_service/function/__init__.py
"""
Function Adapter - 直接调用 Python 函数

最简单的工具类型，直接调用 Python 函数。
"""
from .adapter import FunctionAdapter
from .validator import FunctionValidator

__all__ = [
    "FunctionAdapter",
    "FunctionValidator",
]
