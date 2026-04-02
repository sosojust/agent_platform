# core/tool_service/skill/adapter.py
"""
Skill 适配器

Skill 是基于 LLM 的复合能力：
- Prompt 模板：定义任务
- Available Tools：可调用的工具
- LLM Execution：由 LLM 推理和执行
"""
from typing import Any, Dict, List
from dataclasses import dataclass, field
from shared.logging.logger import get_logger
from ..base.adapter import ToolAdapter
from ..types import ToolMetadata, ToolContext, ToolType, AdapterType, SkillToolMetadata
from .executor import SkillExecutor

logger = get_logger(__name__)


@dataclass
class SkillDefinition:
    """
    Skill 定义。
    
    Skill = Prompt Template + Available Tools + LLM Execution
    """
    name: str
    description: str
    prompt_template: str              # Prompt 模板
    available_tools: List[str]        # 可用工具列表
    llm_config: dict = field(default_factory=lambda: {"model": "gpt-4", "temperature": 0.3})
    input_schema: dict = field(default_factory=dict)


class SkillAdapter(ToolAdapter):
    """
    Skill 适配器。
    
    Skill 是基于 LLM 的复合能力：
    - Prompt 模板：定义任务
    - Available Tools：可调用的工具
    - LLM Execution：由 LLM 推理和执行
    """
    
    def __init__(self, domain: str, tool_gateway):
        """
        Args:
            domain: 域名
            tool_gateway: 工具网关（用于获取可用工具）
        """
        self.domain = domain
        self.tool_gateway = tool_gateway
        self.executor = SkillExecutor(tool_gateway)
        self._skills: Dict[str, SkillDefinition] = {}
    
    def register_skill(self, skill_def: SkillDefinition):
        """注册一个 Skill"""
        self._skills[skill_def.name] = skill_def
        logger.info(
            "skill_registered",
            name=skill_def.name,
            domain=self.domain,
            tool_count=len(skill_def.available_tools),
        )
    
    async def load_tools(self) -> List[ToolMetadata]:
        """加载所有已注册的 Skill"""
        tools = []
        
        for name, skill_def in self._skills.items():
            metadata = SkillToolMetadata(
                name=name,
                description=skill_def.description,
                category=self.domain,
                input_schema=skill_def.input_schema,
                source_domain=self.domain,
                tags=["skill", "llm", self.domain],
                # Skill 特定字段
                prompt_template=skill_def.prompt_template,
                available_tools=skill_def.available_tools,
                llm_config=skill_def.llm_config,
            )
            tools.append(metadata)
        
        logger.info(
            "skill_tools_loaded",
            domain=self.domain,
            count=len(tools),
        )
        
        return tools
    
    async def validate_tool(self, metadata: ToolMetadata) -> tuple[bool, list[str]]:
        """验证 Skill（使用 SkillValidator）"""
        from .validator import SkillValidator
        validator = SkillValidator(self.tool_gateway)
        return await validator.validate(metadata)
    
    async def invoke_tool(
        self,
        metadata: ToolMetadata,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> Any:
        """执行 Skill（通过 SkillExecutor）"""
        skill_def = self._skills.get(metadata.name)
        if not skill_def:
            raise ValueError(f"Skill not found: {metadata.name}")
        
        return await self.executor.execute(skill_def, arguments, context)
    
    def get_adapter_type(self) -> str:
        return AdapterType.SKILL.value
