# core/tool_service/base/adapter.py
"""
工具适配器基类

提供通用能力：
- 工具加载
- 工具验证
- 工具调用
- 生命周期管理

子类只需实现抽象方法即可。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List
from ..types import ToolMetadata, ToolContext


class ToolAdapter(ABC):
    """
    工具适配器基类。
    
    提供通用能力：
    - 工具加载
    - 工具验证
    - 工具调用
    - 生命周期管理
    
    子类只需实现抽象方法即可。
    """
    
    @abstractmethod
    async def load_tools(self) -> List[ToolMetadata]:
        """加载工具列表"""
        pass
    
    @abstractmethod
    async def validate_tool(self, metadata: ToolMetadata) -> tuple[bool, list[str]]:
        """验证工具"""
        pass
    
    @abstractmethod
    async def invoke_tool(
        self,
        metadata: ToolMetadata,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> Any:
        """调用工具"""
        pass
    
    @abstractmethod
    def get_adapter_type(self) -> str:
        """获取适配器类型"""
        pass
    
    # 通用方法（子类可以直接使用）
    async def health_check(self) -> bool:
        """健康检查（通用实现）"""
        try:
            tools = await self.load_tools()
            return len(tools) > 0  # 至少有一个工具
        except Exception:
            return False
    
    async def close(self):
        """关闭资源（子类可以覆盖）"""
        pass
