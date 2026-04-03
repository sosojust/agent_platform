# core/tool_service/router.py
"""
Tool Router - 工具路由器

提供多种工具匹配策略：
- keyword: 关键词匹配
- vector: 向量相似度匹配
- llm: LLM 推理匹配
- hybrid: 混合策略
"""
from typing import List, Dict, Any
from enum import Enum
from shared.logging.logger import get_logger

logger = get_logger(__name__)


class MatchStrategy(str, Enum):
    """匹配策略"""
    KEYWORD = "keyword"    # 关键词匹配
    VECTOR = "vector"      # 向量相似度
    LLM = "llm"            # LLM 推理
    HYBRID = "hybrid"      # 混合策略


class ToolRouter:
    """
    工具路由器。
    
    根据用户意图智能匹配最相关的工具。
    
    支持多种匹配策略：
    - keyword: 关键词匹配（快速）
    - vector: 向量相似度匹配（准确）
    - llm: LLM 推理匹配（智能）
    - hybrid: 混合策略（平衡）
    """
    
    def __init__(self, tool_gateway):
        """
        Args:
            tool_gateway: 工具网关
        """
        self.tool_gateway = tool_gateway
    
    async def match_tools(
        self,
        query: str,
        strategy: MatchStrategy = MatchStrategy.KEYWORD,
        top_k: int = 5,
        context: Any = None,
    ) -> List[Dict[str, Any]]:
        """
        根据查询匹配工具。
        
        Args:
            query: 用户查询
            strategy: 匹配策略
            top_k: 返回前 K 个工具
            context: 工具上下文（用于权限过滤）
        
        Returns:
            匹配的工具列表
        """
        # 获取所有可用工具
        all_tools = await self.tool_gateway.list_tools(context=context)
        
        if strategy == MatchStrategy.KEYWORD:
            return self._match_by_keyword(query, all_tools, top_k)
        elif strategy == MatchStrategy.VECTOR:
            return self._match_by_vector(query, all_tools, top_k)
        elif strategy == MatchStrategy.LLM:
            return self._match_by_llm(query, all_tools, top_k)
        elif strategy == MatchStrategy.HYBRID:
            return self._match_by_hybrid(query, all_tools, top_k)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")
    
    def _match_by_keyword(
        self,
        query: str,
        tools: List[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """关键词匹配（简单实现）"""
        query_lower = query.lower()
        
        # 计算匹配分数
        scored_tools = []
        for tool in tools:
            score = 0
            
            # 名称匹配
            if query_lower in tool["name"].lower():
                score += 10
            
            # 描述匹配
            if query_lower in tool["description"].lower():
                score += 5
            
            # 标签匹配
            for tag in tool.get("tags", []):
                if query_lower in tag.lower():
                    score += 3
            
            if score > 0:
                scored_tools.append((tool, score))
        
        # 排序并返回 top_k
        scored_tools.sort(key=lambda x: x[1], reverse=True)
        return [tool for tool, _ in scored_tools[:top_k]]
    
    def _match_by_vector(
        self,
        query: str,
        tools: List[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """向量相似度匹配（TODO: 实现）"""
        logger.warning("vector_matching_not_implemented")
        return self._match_by_keyword(query, tools, top_k)
    
    def _match_by_llm(
        self,
        query: str,
        tools: List[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """LLM 推理匹配（TODO: 实现）"""
        logger.warning("llm_matching_not_implemented")
        return self._match_by_keyword(query, tools, top_k)
    
    def _match_by_hybrid(
        self,
        query: str,
        tools: List[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """混合策略匹配（TODO: 实现）"""
        logger.warning("hybrid_matching_not_implemented")
        return self._match_by_keyword(query, tools, top_k)


def init_tool_router(tool_gateway) -> ToolRouter:
    """初始化工具路由器"""
    router = ToolRouter(tool_gateway)
    logger.info("tool_router_initialized")
    return router
