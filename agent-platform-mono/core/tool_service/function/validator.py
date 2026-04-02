# core/tool_service/function/validator.py
"""
Function 工具验证器

继承 BaseValidator，只需实现特定验证逻辑。
"""
from ..base.validator import BaseValidator
from ..types import FunctionToolMetadata


class FunctionValidator(BaseValidator):
    """
    Function 工具验证器。
    
    继承 BaseValidator，只需实现特定验证逻辑。
    """
    
    async def _validate_specific(self, metadata: FunctionToolMetadata) -> list[str]:
        """Function 特定验证"""
        errors = []
        
        # 类型检查
        if not isinstance(metadata, FunctionToolMetadata):
            errors.append(f"Function 工具必须使用 FunctionToolMetadata，当前类型: {type(metadata).__name__}")
            return errors  # 类型错误，后续检查无意义
        
        # 检查 function_ref
        if not metadata.function_ref:
            errors.append("Function 工具必须配置 function_ref")
        elif not callable(metadata.function_ref):
            errors.append("function_ref 必须是可调用对象")
        
        return errors
