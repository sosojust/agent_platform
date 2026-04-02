# core/tool_service/skill/__init__.py
"""
Skill Adapter - 执行 LLM 驱动的 Skill

Skill = Prompt Template + Available Tools + LLM Execution
"""
from .adapter import SkillAdapter, SkillDefinition
from .validator import SkillValidator
from .executor import SkillExecutor

__all__ = [
    "SkillAdapter",
    "SkillDefinition",
    "SkillValidator",
    "SkillExecutor",
]
