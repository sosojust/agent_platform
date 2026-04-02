# core/tool_service/base/validator.py
"""
工具验证器基类

提供通用验证逻辑，子类只需实现特定验证。

验证流程：
1. 通用验证（基类实现）- 90% 的逻辑
2. 特定验证（子类实现）- 10% 的逻辑
"""
from typing import List, Tuple
from ..types import ToolMetadata


class BaseValidator:
    """
    工具验证器基类。
    
    提供通用验证逻辑，子类只需实现特定验证。
    
    验证流程：
    1. 通用验证（基类实现）- 90% 的逻辑
    2. 特定验证（子类实现）- 10% 的逻辑
    """
    
    async def validate(self, metadata: ToolMetadata) -> Tuple[bool, List[str]]:
        """
        完整验证流程。
        
        1. 通用验证（基类实现）
        2. 特定验证（子类实现）
        """
        errors = []
        
        # 1. 通用验证
        common_errors = self._validate_common(metadata)
        errors.extend(common_errors)
        
        # 2. 特定验证（子类实现）
        specific_errors = await self._validate_specific(metadata)
        errors.extend(specific_errors)
        
        return (len(errors) == 0, errors)
    
    def _validate_common(self, metadata: ToolMetadata) -> List[str]:
        """通用验证逻辑（所有工具都需要）"""
        errors = []
        
        if not metadata.name:
            errors.append("工具名称不能为空")
        
        if not metadata.description:
            errors.append("工具描述不能为空")
        
        if not metadata.input_schema:
            errors.append("工具必须定义 input_schema")
        
        # 验证 input_schema 格式
        if metadata.input_schema:
            if not isinstance(metadata.input_schema, dict):
                errors.append("input_schema 必须是字典")
            elif "type" not in metadata.input_schema:
                errors.append("input_schema 必须包含 type 字段")
        
        return errors
    
    async def _validate_specific(self, metadata: ToolMetadata) -> List[str]:
        """
        特定验证逻辑（子类覆盖）。
        
        子类只需实现这个方法，添加特定的验证逻辑。
        """
        return []
