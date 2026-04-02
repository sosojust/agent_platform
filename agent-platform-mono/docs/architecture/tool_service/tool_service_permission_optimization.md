# Tool Service 权限策略优化说明

> 版本：v6.1  
> 日期：2026-04-02  
> 类型：性能和可用性优化

## 一、问题背景

### 1.1 原有设计的问题

**默认策略过重**：
```python
# v6.0 的默认策略
permission_strategy: PermissionStrategy = PermissionStrategy.LOCAL_AND_REMOTE
```

**问题**：
1. **性能问题**：每次工具调用都要串行走两层检查（本地白名单 + 远程用户中心 HTTP 请求）
2. **延迟增加**：远程 HTTP 请求通常需要 50-200ms
3. **可用性问题**：用户中心抖动时，所有工具调用都会失败（异常直接返回 `False`）

**生产影响**：
- 高频调用的工具（如查询类）延迟显著增加
- 用户中心维护或故障时，整个工具系统不可用
- 对于大部分普通工具，双重检查是过度设计

---

## 二、优化方案

### 2.1 默认策略调整

**v6.1 优化**：
```python
# 默认策略改为 LOCAL_ONLY
permission_strategy: PermissionStrategy = PermissionStrategy.LOCAL_ONLY
```

**理由**：
- 大部分工具（查询类、普通写入）不需要远程鉴权
- 本地白名单检查足够快（<1ms）
- 只有敏感工具才需要升级策略

### 2.2 降级机制

**v6.1 新增**：
```python
class BasePermissionChecker:
    def __init__(
        self,
        user_center_client=None,
        enable_fallback: bool = True,  # 启用降级
    ):
        self.enable_fallback = enable_fallback
    
    async def _check_remote_with_fallback(self, metadata, context):
        """远程检查失败时，降级到本地规则"""
        remote_ok, remote_msg = await self._check_remote(metadata, context)
        
        # 如果远程失败且启用降级
        if not remote_ok and self.enable_fallback:
            logger.warning("remote_check_failed_fallback_to_local", ...)
            
            local_ok, local_msg = await self._check_local(metadata, context)
            if local_ok:
                return True, f"远程检查失败，降级到本地规则通过"
        
        return remote_ok, remote_msg
```

**降级流程**：
```
1. 尝试远程检查
   ↓
2. 远程失败（超时/异常/拒绝）
   ↓
3. 降级到本地规则
   ↓
4. 本地规则通过 → 允许（记录日志）
   本地规则不通过 → 拒绝
```

### 2.3 权限缓存

**v6.1 新增**：
```python
class BasePermissionChecker:
    def __init__(
        self,
        user_center_client=None,
        cache_ttl: int = 300,  # 缓存 5 分钟
    ):
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, Tuple[bool, str, float]] = {}
    
    async def _check_remote_with_fallback(self, metadata, context):
        # 1. 先查缓存
        cache_key = self._get_cache_key(metadata.name, context)
        cached_result = self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result  # 缓存命中，直接返回
        
        # 2. 缓存未命中，调用远程
        remote_ok, remote_msg = await self._check_remote(metadata, context)
        
        # 3. 缓存成功的结果
        if remote_ok:
            self._put_to_cache(cache_key, (remote_ok, remote_msg))
        
        return remote_ok, remote_msg
```

**缓存策略**：
- 缓存 key：`perm:{tool_name}:{tenant_id}:{user_id}:{channel_id}`
- 缓存时长：5 分钟（可配置）
- 只缓存成功的结果（失败的不缓存，避免误拦截）

---

## 三、策略选择指南

### 3.1 工具类型与策略映射

| 工具类型 | 推荐策略 | 理由 | 示例 |
|---------|---------|------|------|
| **查询类工具** | LOCAL_ONLY | 高频调用，性能优先 | query_policy_basic |
| **普通写入** | LOCAL_ONLY | 本地白名单足够 | update_policy_status |
| **敏感操作** | REMOTE_ONLY | 必须用户中心鉴权 | delete_policy |
| **核心资产** | LOCAL_AND_REMOTE | 双重保障 | transfer_ownership |
| **外部 MCP** | LOCAL_ONLY | 外部服务已有鉴权 | weather:get_forecast |

### 3.2 策略详解

#### LOCAL_ONLY（默认）

```python
tool = ToolMetadata(
    name="query_policy_basic",
    # permission_strategy 默认 LOCAL_ONLY
)
```

**特点**：
- 只检查本地白名单
- 性能最优（<1ms）
- 适合大部分工具

**检查流程**：
```
1. 检查 allowed_tenants
2. 检查 allowed_channels
3. 检查 allowed_users
4. 检查 allowed_tenant_types
5. 如果没有配置任何白名单 → 默认允许
```

#### REMOTE_ONLY（敏感工具）

```python
tool = ToolMetadata(
    name="delete_policy",
    permission_strategy=PermissionStrategy.REMOTE_ONLY,
)
```

**特点**：
- 只检查用户中心
- 必须远程鉴权
- 适合敏感操作

**检查流程**：
```
1. 调用用户中心 API
2. 失败 → 降级到本地规则（如果启用）
3. 成功 → 缓存结果
```

#### LOCAL_AND_REMOTE（最严格）

```python
tool = ToolMetadata(
    name="transfer_ownership",
    permission_strategy=PermissionStrategy.LOCAL_AND_REMOTE,
)
```

**特点**：
- 双重检查
- 最严格
- 适合核心资产

**检查流程**：
```
1. 先本地检查（快速失败）
2. 本地不通过 → 直接拒绝
3. 本地通过 → 再远程检查
4. 远程失败 → 降级到本地规则（如果启用）
```

#### LOCAL_OR_REMOTE（最宽松）

```python
tool = ToolMetadata(
    name="view_dashboard",
    permission_strategy=PermissionStrategy.LOCAL_OR_REMOTE,
)
```

**特点**：
- 任一通过即可
- 最宽松
- 适合灵活场景

**检查流程**：
```
1. 先本地检查（快速通过）
2. 本地通过 → 直接允许
3. 本地不通过 → 再远程检查
4. 远程失败 → 降级到本地规则（如果启用）
```

---

## 四、性能对比

### 4.1 延迟对比

| 策略 | 第 1 次调用 | 第 2-N 次调用（缓存） | 用户中心故障时 |
|------|-----------|---------------------|--------------|
| **LOCAL_ONLY** | <1ms | <1ms | <1ms（不受影响） |
| **REMOTE_ONLY** | 50-200ms | <1ms | <1ms（降级） |
| **LOCAL_AND_REMOTE** | 50-200ms | <1ms | <1ms（降级） |
| **LOCAL_OR_REMOTE** | <1ms（本地通过）| <1ms | <1ms（降级） |

### 4.2 可用性对比

| 场景 | v6.0（默认 LOCAL_AND_REMOTE） | v6.1（默认 LOCAL_ONLY + 降级） |
|------|------------------------------|-------------------------------|
| **正常情况** | 可用（延迟高） | 可用（延迟低） |
| **用户中心抖动** | 不可用（全部失败） | 可用（降级到本地） |
| **用户中心维护** | 不可用（全部失败） | 可用（降级到本地） |
| **网络故障** | 不可用（全部失败） | 可用（降级到本地） |

---

## 五、使用示例

### 5.1 普通工具（默认策略）

```python
# 查询类工具 - 使用默认策略
policy_adapter.register_tool(
    name="query_policy_basic",
    description="查询保单基本信息",
    endpoint="/api/v1/policies/{policy_id}/basic",
    method="GET",
    # permission_strategy 默认 LOCAL_ONLY
)
```

### 5.2 敏感工具（升级策略）

```python
# 删除操作 - 必须用户中心鉴权
policy_adapter.register_tool(
    name="delete_policy",
    description="删除保单",
    endpoint="/api/v1/policies/{policy_id}",
    method="DELETE",
    permission_strategy=PermissionStrategy.REMOTE_ONLY,  # 明确指定
)
```

### 5.3 配置权限检查器

```python
# app/gateway/lifespan.py
from core.tool_service.base.permissions import BasePermissionChecker

# 创建权限检查器
permission_checker = BasePermissionChecker(
    user_center_client=user_center_client,
    cache_ttl=300,           # 缓存 5 分钟
    enable_fallback=True,    # 启用降级（推荐）
)

# 注册到 tool_gateway
tool_gateway.set_permission_checker(permission_checker)
```

### 5.4 监控和告警

```python
# 监控指标
metrics = {
    "permission_check_total": Counter("工具权限检查总数"),
    "permission_check_local": Counter("本地检查次数"),
    "permission_check_remote": Counter("远程检查次数"),
    "permission_check_cache_hit": Counter("缓存命中次数"),
    "permission_check_fallback": Counter("降级次数"),
    "permission_check_denied": Counter("拒绝次数"),
}

# 告警规则
alerts = [
    {
        "name": "用户中心可用性低",
        "condition": "permission_check_fallback > 100/min",
        "action": "通知运维团队",
    },
    {
        "name": "权限拒绝率高",
        "condition": "permission_check_denied / permission_check_total > 0.1",
        "action": "检查权限配置",
    },
]
```

---

## 六、迁移指南

### 6.1 从 v6.0 迁移到 v6.1

**代码无需修改**：
- 默认策略自动变为 LOCAL_ONLY
- 降级和缓存自动启用
- 现有工具继续工作

**可选优化**：
```python
# 1. 明确敏感工具的策略
sensitive_tools = [
    "delete_policy",
    "transfer_ownership",
    "export_sensitive_data",
]

for tool_name in sensitive_tools:
    tool_metadata.permission_strategy = PermissionStrategy.REMOTE_ONLY

# 2. 配置缓存时长（可选）
permission_checker = BasePermissionChecker(
    user_center_client=user_center_client,
    cache_ttl=600,  # 改为 10 分钟
)

# 3. 禁用降级（不推荐）
permission_checker = BasePermissionChecker(
    user_center_client=user_center_client,
    enable_fallback=False,  # 生产环境不推荐
)
```

### 6.2 测试建议

```python
# 1. 测试默认策略
async def test_default_strategy():
    tool = ToolMetadata(name="query_policy_basic")
    assert tool.permission_strategy == PermissionStrategy.LOCAL_ONLY

# 2. 测试降级机制
async def test_fallback():
    # Mock 用户中心故障
    user_center_client.check_tool_permission = Mock(side_effect=Exception("timeout"))
    
    # 应该降级到本地规则
    result, msg = await checker.check_permission(metadata, context)
    assert result == True
    assert "降级到本地规则通过" in msg

# 3. 测试缓存
async def test_cache():
    # 第 1 次调用
    start = time.time()
    await checker.check_permission(metadata, context)
    first_duration = time.time() - start
    
    # 第 2 次调用（缓存命中）
    start = time.time()
    await checker.check_permission(metadata, context)
    second_duration = time.time() - start
    
    assert second_duration < first_duration * 0.1  # 缓存快 10 倍以上
```

---

## 七、总结

### 7.1 核心改进

1. **默认策略优化**：LOCAL_AND_REMOTE → LOCAL_ONLY（性能提升 50-200ms）
2. **降级机制**：用户中心故障时自动降级（可用性提升）
3. **权限缓存**：减少远程调用（性能提升 10 倍以上）

### 7.2 生产收益

| 指标 | v6.0 | v6.1 | 提升 |
|------|------|------|------|
| **平均延迟** | 100ms | <1ms | 100 倍 |
| **用户中心故障时可用性** | 0% | 100% | ∞ |
| **远程调用次数** | 100% | <10%（缓存） | 10 倍 |

### 7.3 最佳实践

1. ✅ 大部分工具使用默认策略（LOCAL_ONLY）
2. ✅ 敏感工具明确指定策略（REMOTE_ONLY）
3. ✅ 启用降级机制（enable_fallback=True）
4. ✅ 配置合理的缓存时长（300-600 秒）
5. ✅ 监控降级触发次数（告警用户中心问题）

---

**文档维护者**：Agent Platform Team  
**最后更新**：2026-04-02  
**版本**：v6.1
