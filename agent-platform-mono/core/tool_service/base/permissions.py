# core/tool_service/base/permissions.py
"""
权限检查器基类

提供通用权限检查逻辑：
- 本地白名单检查
- 远程用户中心检查（带缓存和降级）
- 多种策略支持

生产优化：
- 默认策略为 LOCAL_ONLY（性能优先）
- 远程检查失败时降级到本地规则（可用性优先）
- 权限结果缓存（减少远程调用）
"""
import time
from typing import Dict, Tuple
from shared.logging.logger import get_logger
from ..types import ToolMetadata, ToolContext, PermissionStrategy

logger = get_logger(__name__)


class BasePermissionChecker:
    """
    权限检查器基类。
    
    提供通用权限检查逻辑：
    - 本地白名单检查
    - 远程用户中心检查（带缓存和降级）
    - 多种策略支持
    
    生产优化：
    - 默认策略为 LOCAL_ONLY（性能优先）
    - 远程检查失败时降级到本地规则（可用性优先）
    - 权限结果缓存（减少远程调用）
    """
    
    def __init__(
        self,
        user_center_client=None,
        cache_ttl: int = 300,  # 缓存 5 分钟
        enable_fallback: bool = True,  # 启用降级
    ):
        self.user_center_client = user_center_client
        self.cache_ttl = cache_ttl
        self.enable_fallback = enable_fallback
        self._cache: Dict[str, Tuple[bool, str, float]] = {}  # {cache_key: (result, msg, timestamp)}
    
    async def check_permission(
        self,
        metadata: ToolMetadata,
        context: ToolContext,
    ) -> Tuple[bool, str]:
        """
        检查权限。
        
        根据 metadata.permission_strategy 选择策略：
        - LOCAL_ONLY: 仅本地白名单（默认，性能最优）
        - REMOTE_ONLY: 仅用户中心（敏感工具）
        - LOCAL_AND_REMOTE: 双重检查（最严格）
        - LOCAL_OR_REMOTE: 任一通过（最宽松）
        
        生产优化：
        - 远程检查失败时，如果启用降级，会 fallback 到本地规则
        - 远程检查结果会缓存，减少 HTTP 调用
        """
        strategy = metadata.permission_strategy
        
        if strategy == PermissionStrategy.LOCAL_ONLY:
            return await self._check_local(metadata, context)
        
        elif strategy == PermissionStrategy.REMOTE_ONLY:
            return await self._check_remote_with_fallback(metadata, context)
        
        elif strategy == PermissionStrategy.LOCAL_AND_REMOTE:
            # 先本地检查（快速失败）
            local_ok, local_msg = await self._check_local(metadata, context)
            if not local_ok:
                return False, local_msg
            # 再远程检查（带降级）
            return await self._check_remote_with_fallback(metadata, context)
        
        elif strategy == PermissionStrategy.LOCAL_OR_REMOTE:
            # 先本地检查（快速通过）
            local_ok, _ = await self._check_local(metadata, context)
            if local_ok:
                return True, "本地权限通过"
            # 本地不通过，尝试远程（带降级）
            return await self._check_remote_with_fallback(metadata, context)
        
        return False, "未知的权限策略"
    
    async def _check_local(
        self,
        metadata: ToolMetadata,
        context: ToolContext,
    ) -> Tuple[bool, str]:
        """本地白名单检查（通用逻辑）"""
        # 如果没有配置任何白名单，默认允许
        has_restrictions = (
            metadata.allowed_tenants or
            metadata.allowed_channels or
            metadata.allowed_users or
            metadata.allowed_tenant_types
        )
        
        if not has_restrictions:
            return True, "本地无限制，默认允许"
        
        # 检查 tenant_id
        if metadata.allowed_tenants:
            if context.tenant_id not in metadata.allowed_tenants:
                return False, f"租户 {context.tenant_id} 无权限"
        
        # 检查 channel_id
        if metadata.allowed_channels:
            if context.channel_id not in metadata.allowed_channels:
                return False, f"渠道 {context.channel_id} 无权限"
        
        # 检查 user_id
        if metadata.allowed_users:
            if context.user_id not in metadata.allowed_users:
                return False, f"用户 {context.user_id} 无权限"
        
        # 检查 tenant_type
        if metadata.allowed_tenant_types:
            if context.tenant_type not in metadata.allowed_tenant_types:
                return False, f"租户类型 {context.tenant_type} 无权限"
        
        return True, "本地权限检查通过"
    
    async def _check_remote_with_fallback(
        self,
        metadata: ToolMetadata,
        context: ToolContext,
    ) -> Tuple[bool, str]:
        """
        远程用户中心检查（带缓存和降级）。
        
        优化策略：
        1. 先查缓存
        2. 缓存未命中，调用远程
        3. 远程失败，降级到本地规则（如果启用）
        """
        # 1. 检查缓存
        cache_key = self._get_cache_key(metadata.name, context)
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        # 2. 调用远程
        remote_ok, remote_msg = await self._check_remote(metadata, context)
        
        # 3. 缓存结果（只缓存成功的结果）
        if remote_ok:
            self._put_to_cache(cache_key, (remote_ok, remote_msg))
        
        # 4. 如果远程失败且启用降级，fallback 到本地规则
        if not remote_ok and self.enable_fallback:
            logger.warning(
                "remote_check_failed_fallback_to_local",
                tool_name=metadata.name,
                tenant_id=context.tenant_id,
                remote_msg=remote_msg,
            )
            
            local_ok, local_msg = await self._check_local(metadata, context)
            if local_ok:
                return True, f"远程检查失败，降级到本地规则通过: {local_msg}"
            else:
                return False, f"远程检查失败且本地规则也不通过: {remote_msg}"
        
        return remote_ok, remote_msg
    
    async def _check_remote(
        self,
        metadata: ToolMetadata,
        context: ToolContext,
    ) -> Tuple[bool, str]:
        """远程用户中心检查（原始逻辑）"""
        if not self.user_center_client:
            logger.warning("user_center_client_not_configured")
            return True, "用户中心未配置，跳过远程检查"
        
        try:
            has_permission = await self.user_center_client.check_tool_permission(
                tool_name=metadata.name,
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                channel_id=context.channel_id,
                tenant_type=context.tenant_type,
            )
            
            if has_permission:
                return True, "用户中心权限检查通过"
            else:
                return False, "用户中心权限检查失败"
        
        except Exception as e:
            logger.error(
                "user_center_check_exception",
                tool_name=metadata.name,
                tenant_id=context.tenant_id,
                error=str(e),
            )
            # 异常时返回失败，由 _check_remote_with_fallback 处理降级
            return False, f"用户中心检查异常: {str(e)}"
    
    def _get_cache_key(self, tool_name: str, context: ToolContext) -> str:
        """生成缓存 key"""
        return f"perm:{tool_name}:{context.tenant_id}:{context.user_id}:{context.channel_id}"
    
    def _get_from_cache(self, cache_key: str) -> Tuple[bool, str] | None:
        """从缓存获取"""
        if cache_key not in self._cache:
            return None
        
        result, msg, timestamp = self._cache[cache_key]
        
        # 检查是否过期
        if time.time() - timestamp > self.cache_ttl:
            del self._cache[cache_key]
            return None
        
        return (result, msg)
    
    def _put_to_cache(self, cache_key: str, value: Tuple[bool, str]):
        """放入缓存"""
        self._cache[cache_key] = (value[0], value[1], time.time())
    
    def clear_cache(self):
        """清空缓存（用于测试或手动刷新）"""
        self._cache.clear()
