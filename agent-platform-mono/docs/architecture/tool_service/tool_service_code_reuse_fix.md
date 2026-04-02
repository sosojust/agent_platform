# Tool Service 代码复用问题修复

> 版本：v6.2  
> 日期：2026-04-02  
> 类型：代码质量优化

## 一、问题背景

### 1.1 发现的问题

**重复实现**：
- `InternalHTTPClient.call()` 和 `InternalMCPAdapter.invoke_tool()` 存在几乎相同的 HTTP 调用代码
- 包括 headers 透传逻辑、HTTP 方法判断、错误处理等

**违背原则**：
- 违背 DRY 原则（Don't Repeat Yourself）
- 违背文档自己强调的代码复用原则
- 增加维护成本

### 1.2 原有实现

**InternalHTTPClient（已有）**：
```python
class InternalHTTPClient:
    async def call(self, endpoint, method, data, context):
        url = f"{self.base_url}{endpoint}"
        
        # 透传上下文信息
        headers = {
            "X-Tenant-ID": context.tenant_id,
            "X-User-ID": context.user_id or "",
            ...
        }
        
        if method == "GET":
            response = await self._client.get(url, params=data, headers=headers)
        elif method == "POST":
            response = await self._client.post(url, json=data, headers=headers)
        ...
```

**InternalMCPAdapter（重复实现）**：
```python
class InternalMCPAdapter:
    async def invoke_tool(self, metadata, arguments, context):
        # 重复实现相同的逻辑
        url = f"{self.base_url}{endpoint}"
        
        # 重复的 headers 透传逻辑
        headers = {
            "X-Tenant-ID": context.tenant_id,
            "X-User-ID": context.user_id or "",
            ...
        }
        
        # 重复的 HTTP 方法判断
        if method == "GET":
            response = await self._client.get(url, params=arguments, headers=headers)
        elif method == "POST":
            response = await self._client.post(url, json=arguments, headers=headers)
        ...
```

**问题**：
1. 代码重复（约 30 行）
2. 维护成本高（修改一处要改两处）
3. 容易出现不一致（一处修改了，另一处忘记修改）

---

## 二、修复方案

### 2.1 委托模式

**核心思想**：InternalMCPAdapter 委托给 InternalHTTPClient，而不是重复实现。

**修复后的实现**：

```python
class InternalMCPAdapter(ToolAdapter):
    def __init__(self, domain: str, service_name: str, base_url: str):
        self.domain = domain
        self.service_name = service_name
        self.client = InternalHTTPClient(base_url)  # 使用 InternalHTTPClient
        self._tools = {}
    
    async def invoke_tool(self, metadata, arguments, context):
        """调用内部服务的工具（委托给 InternalHTTPClient）"""
        tool_info = self._tools[metadata.name]
        
        try:
            # 委托给 InternalHTTPClient（避免重复实现）
            return await self.client.call(
                endpoint=tool_info["endpoint"],
                method=tool_info["method"],
                data=arguments,
                context=context,
            )
        
        except httpx.HTTPStatusError as e:
            logger.error(
                "internal_mcp_invoke_failed",
                tool_name=metadata.name,
                service=self.service_name,
                status_code=e.response.status_code,
                error=str(e),
            )
            raise
        except Exception as e:
            logger.error(
                "internal_mcp_error",
                tool_name=metadata.name,
                service=self.service_name,
                error=str(e),
            )
            raise
    
    async def close(self):
        """关闭客户端"""
        await self.client.close()
```

### 2.2 职责划分

```
┌─────────────────────────────────────────┐
│      InternalMCPAdapter                 │
│  职责：                                 │
│  - MCP 协议封装                         │
│  - 工具注册和管理                       │
│  - 工具元数据管理                       │
│  - 错误日志记录                         │
└────────────────┬────────────────────────┘
                 │ 委托
                 ↓
┌─────────────────────────────────────────┐
│      InternalHTTPClient                 │
│  职责：                                 │
│  - HTTP 调用逻辑                        │
│  - 上下文透传                           │
│  - HTTP 方法处理                        │
│  - 连接管理                             │
└─────────────────────────────────────────┘
```

---

## 三、对比分析

### 3.1 代码行数对比

| 实现方式 | InternalMCPAdapter | InternalHTTPClient | 总行数 |
|---------|-------------------|-------------------|--------|
| **重复实现（v6.1）** | 120 行 | 50 行 | 170 行 |
| **委托实现（v6.2）** | 90 行 | 50 行 | 140 行 |
| **减少** | -30 行 | 0 行 | -30 行 |

### 3.2 维护成本对比

| 场景 | 重复实现 | 委托实现 |
|------|---------|---------|
| **新增 HTTP 方法** | 修改 2 处 | 修改 1 处 |
| **修改 headers** | 修改 2 处 | 修改 1 处 |
| **修改超时配置** | 修改 2 处 | 修改 1 处 |
| **修改错误处理** | 修改 2 处 | 修改 1 处 |

### 3.3 代码质量对比

| 指标 | 重复实现 | 委托实现 |
|------|---------|---------|
| **DRY 原则** | ❌ 违背 | ✅ 遵守 |
| **单一职责** | ❌ 职责混乱 | ✅ 职责清晰 |
| **可维护性** | ❌ 低 | ✅ 高 |
| **可测试性** | ❌ 需要测试 2 处 | ✅ 只需测试 1 处 |
| **一致性** | ❌ 容易不一致 | ✅ 保证一致 |

---

## 四、设计原则

### 4.1 DRY 原则（Don't Repeat Yourself）

**定义**：
> 每一个知识点在系统中都应该有一个单一的、明确的、权威的表示。

**应用**：
- HTTP 调用逻辑只在 `InternalHTTPClient` 中实现一次
- `InternalMCPAdapter` 通过委托复用这个逻辑

### 4.2 单一职责原则（Single Responsibility Principle）

**InternalHTTPClient 的职责**：
- 封装 HTTP 调用
- 透传上下文
- 处理 HTTP 方法

**InternalMCPAdapter 的职责**：
- MCP 协议封装
- 工具注册和管理
- 错误日志记录

### 4.3 委托优于继承

**为什么用委托而不是继承？**

❌ **继承方式**：
```python
class InternalMCPAdapter(InternalHTTPClient):
    # 问题：
    # 1. 继承了不需要的方法
    # 2. 耦合度高
    # 3. 违背 Liskov 替换原则
    pass
```

✅ **委托方式**：
```python
class InternalMCPAdapter:
    def __init__(self, ...):
        self.client = InternalHTTPClient(...)  # 组合
    
    async def invoke_tool(self, ...):
        return await self.client.call(...)  # 委托
```

**委托的优势**：
- 松耦合
- 灵活性高
- 易于测试（可以 mock client）
- 符合"组合优于继承"原则

---

## 五、使用示例

### 5.1 注册和使用

```python
# 创建 InternalMCPAdapter
policy_adapter = InternalMCPAdapter(
    domain="policy",
    service_name="policy-service",
    base_url="http://policy-service",
)

# 注册工具
policy_adapter.register_tool(
    name="query_policy_basic",
    description="查询保单基本信息",
    endpoint="/api/v1/policies/{policy_id}/basic",
    method="GET",
)

# 调用工具（内部委托给 InternalHTTPClient）
result = await policy_adapter.invoke_tool(
    metadata=metadata,
    arguments={"policy_id": "P2024001"},
    context=context,
)
```

### 5.2 测试

```python
# 测试 InternalHTTPClient（单独测试）
async def test_internal_http_client():
    client = InternalHTTPClient("http://test-service")
    
    result = await client.call(
        endpoint="/api/test",
        method="POST",
        data={"key": "value"},
        context=context,
    )
    
    assert result == expected_result

# 测试 InternalMCPAdapter（可以 mock client）
async def test_internal_mcp_adapter():
    adapter = InternalMCPAdapter("policy", "policy-service", "http://test")
    
    # Mock InternalHTTPClient
    adapter.client = Mock()
    adapter.client.call = AsyncMock(return_value={"result": "ok"})
    
    result = await adapter.invoke_tool(metadata, arguments, context)
    
    # 验证委托调用
    adapter.client.call.assert_called_once_with(
        endpoint="/api/test",
        method="POST",
        data=arguments,
        context=context,
    )
```

---

## 六、迁移指南

### 6.1 代码无需修改

**好消息**：对外接口完全不变，业务代码无需修改。

```python
# 业务代码（v6.1 和 v6.2 完全一样）
policy_adapter = InternalMCPAdapter(
    domain="policy",
    service_name="policy-service",
    base_url="http://policy-service",
)

policy_adapter.register_tool(...)

result = await policy_adapter.invoke_tool(...)
```

### 6.2 内部实现变化

| 组件 | v6.1 | v6.2 |
|------|------|------|
| **InternalMCPAdapter.__init__** | `self._client = httpx.AsyncClient()` | `self.client = InternalHTTPClient()` |
| **InternalMCPAdapter.invoke_tool** | 直接调用 `self._client.get/post/...` | 委托给 `self.client.call()` |
| **InternalMCPAdapter.close** | `await self._client.aclose()` | `await self.client.close()` |

---

## 七、总结

### 7.1 核心改进

1. **消除代码重复**：减少 30 行重复代码
2. **提升可维护性**：修改一处即可
3. **强化职责分离**：Adapter 负责协议，Client 负责 HTTP
4. **遵守设计原则**：DRY、单一职责、委托优于继承

### 7.2 设计原则总结

```
代码复用的三个层次：
1. 继承（Base 类提供通用能力）
2. 组合（Adapter 使用 Client）
3. 委托（Adapter 委托给 Client）

本次修复体现了第 2 和第 3 层次。
```

### 7.3 最佳实践

1. ✅ 发现重复代码时，立即重构
2. ✅ 优先使用委托而非继承
3. ✅ 保持单一职责
4. ✅ 编写单元测试验证重构
5. ✅ 保持对外接口不变

---

**文档维护者**：Agent Platform Team  
**最后更新**：2026-04-02  
**版本**：v6.2
