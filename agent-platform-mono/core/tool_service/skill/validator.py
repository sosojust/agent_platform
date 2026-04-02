# core/tool_service/skill/validator.py
"""
Skill 验证器

继承 BaseValidator，只需实现特定验证逻辑。
"""
from ..base.validator import BaseValidator
from ..types import SkillToolMetadata


class SkillValidator(BaseValidator):
    """
    Skill 验证器。
    
    继承 BaseValidator，只需实现特定验证逻辑。
    """
    
    def __init__(self, tool_gateway):
        self.tool_gateway = tool_gateway
    
    async def _validate_specific(self, metadata: SkillToolMetadata) -> list[str]:
        """Skill 特定验证"""
        errors = []
        
        # 类型检查
        if not isinstance(metadata, SkillToolMetadata):
            errors.append(f"Skill 工具必须使用 SkillToolMetadata，当前类型: {type(metadata).__name__}")
            return errors  # 类型错误，后续检查无意义
        
        # 检查 prompt_template
        if not metadata.prompt_template:
            errors.append("Skill 必须定义 prompt_template")
        
        # 检查 available_tools
        if not metadata.available_tools:
            errors.append("Skill 必须指定 available_tools")
        else:
            # 验证工具是否存在
            all_tool_names = {t["name"] for t in self.tool_gateway.list_tools()}
            for tool_name in metadata.available_tools:
                if tool_name not in all_tool_names:
                    errors.append(f"Skill 引用的工具不存在: {tool_name}")
        
        # 检查 llm_config
        if not metadata.llm_config:
            errors.append("Skill 必须配置 llm_config")
        elif "model" not in metadata.llm_config:
            errors.append("Skill 的 llm_config 必须包含 model 字段")
        
        return errors
