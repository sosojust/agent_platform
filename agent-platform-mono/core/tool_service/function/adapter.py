# core/tool_service/function/adapter.py
"""
Function 适配器

用于直接调用 Python 函数（最简单的工具类型）。
"""
from typing import Any, Dict, List, Callable
import inspect
import asyncio
from shared.logging.logger import get_logger
from ..base.adapter import ToolAdapter
from ..types import ToolMetadata, ToolContext, ToolType, AdapterType, FunctionToolMetadata

logger = get_logger(__name__)


class FunctionAdapter(ToolAdapter):
    """
    Function 适配器。
    
    用于直接调用 Python 函数（最简单的工具类型）。
    """
    
    def __init__(self, domain: str = "common"):
        self.domain = domain
        self._functions: Dict[str, Callable] = {}
        self._metadata_cache: Dict[str, ToolMetadata] = {}
    
    def register_function(
        self,
        func: Callable,
        name: str | None = None,
        description: str | None = None,
        category: str | None = None,
    ):
        """注册一个 Python 函数作为工具"""
        tool_name = name or func.__name__
        tool_desc = description or (func.__doc__ or "").strip()
        tool_category = category or self.domain
        
        self._functions[tool_name] = func
        
        # 生成元数据
        sig = inspect.signature(func)
        input_schema = self._generate_schema_from_signature(sig)
        
        metadata = FunctionToolMetadata(
            name=tool_name,
            description=tool_desc,
            type=ToolType.TOOL,
            category=tool_category,
            input_schema=input_schema,
            source_module=func.__module__,
            source_domain=self.domain,
            tags=["function", tool_category],
            # Function 特定字段
            function_ref=func,
        )
        
        self._metadata_cache[tool_name] = metadata
    
    async def load_tools(self) -> List[FunctionToolMetadata]:
        """加载所有已注册的函数工具"""
        return list(self._metadata_cache.values())
    
    def _generate_schema_from_signature(self, sig: inspect.Signature) -> dict:
        """从函数签名生成 JSON Schema"""
        properties = {}
        required = []
        
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "args", "kwargs"):
                continue
            
            param_type = "string"
            if param.annotation != inspect.Parameter.empty:
                if param.annotation == int:
                    param_type = "integer"
                elif param.annotation == float:
                    param_type = "number"
                elif param.annotation == bool:
                    param_type = "boolean"
                elif param.annotation == dict:
                    param_type = "object"
                elif param.annotation == list:
                    param_type = "array"
            
            properties[param_name] = {"type": param_type}
            
            if param.default == inspect.Parameter.empty:
                required.append(param_name)
        
        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }
    
    async def validate_tool(self, metadata: ToolMetadata) -> tuple[bool, list[str]]:
        """验证函数工具"""
        from .validator import FunctionValidator
        validator = FunctionValidator()
        return await validator.validate(metadata)
    
    async def invoke_tool(
        self,
        metadata: ToolMetadata,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> Any:
        """执行函数工具"""
        func = self._functions.get(metadata.name)
        if not func:
            raise ValueError(f"Function not found: {metadata.name}")
        
        # 调用函数
        result = func(**arguments)
        
        # 处理异步
        if asyncio.iscoroutine(result):
            result = await result
        
        return result
    
    def get_adapter_type(self) -> str:
        return AdapterType.FUNCTION.value
