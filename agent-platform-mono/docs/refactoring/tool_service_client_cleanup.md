# Tool Service Client 层重构

## 问题描述

`core/tool_service/client` 这一层的职责定位不清晰：

- 原本设计为"进行内部 API 直接调用"
- 但在当前架构下，所有工具调用应该统一通过 MCP 进行
- `domain_agents` 中的 MCP 工具直接使用 `internal_gateway` 调用后端服务，绕过了 MCP 架构
- 这导致了架构不一致：有些调用走 MCP，有些直接调用 HTTP API

## 架构问题

### 修改前的调用链

```
domain_agents MCP tools → tool_service/client/gateway (internal_gateway) → 后端服务
```

问题：
1. MCP 工具内部直接调用 HTTP API，没有通过 MCP 协议
2. `tool_service/client` 层职责不清，既不是 MCP 层，也不是通用 HTTP 客户端
3. 未来如果需要直接调用内部系统 API，应该单独拉一层出来

### 修改后的架构

```
domain_agents MCP tools → shared/internal_http/client (get_internal_api_client) → 后端服务
```

改进：
1. 删除了 `tool_service/client` 层
2. 创建了 `shared/internal_http/client` 作为内部服务 HTTP 客户端
3. MCP 工具内部使用专用的内部 HTTP 客户端调用后端服务
4. 职责更清晰：`shared/internal_http` 是基础设施层，专门用于调用内部服务

## 修改内容

### 新增文件

1. **shared/internal_http/client.py**
   - `InternalAPIClient`: 内部服务 API 客户端类
   - `get_internal_api_client()`: 获取客户端单例
   - `build_context_headers()`: 构建上下文请求头
   - 功能：
     - 自动注入租户、追踪、会话等上下文信息
     - 支持重试机制（3 次，指数退避）
     - 统一的日志记录
     - 连接池管理

2. **shared/internal_http/__init__.py**
   - 导出内部 HTTP 客户端相关接口

### 删除文件

- `core/tool_service/client/gateway.py`
- `core/tool_service/client/__init__.py`
- `core/tool_service/client/` 目录

### 修改文件

1. **domain_agents/policy/tools/policy_tools.py**
   - 从 `from core.tool_service.client.gateway import internal_gateway`
   - 改为 `from shared.internal_http.client import get_internal_api_client`
   - 调用从 `internal_gateway.get()` 改为 `get_internal_api_client().get()`

2. **domain_agents/claim/tools/claim_tools.py**
   - 同上

3. **domain_agents/customer/tools/customer_tools.py**
   - 同上

4. **app/gateway/lifespan.py**
   - 导入从 `from core.tool_service.client.gateway import internal_gateway`
   - 改为 `from shared.internal_http.client import get_internal_api_client`
   - 关闭调用从 `await internal_gateway.close()`
   - 改为 `await get_internal_api_client().close()`

5. **tests/apps/test_policy.py**
   - Mock 从 `patch("domain_agents.policy.tools.policy_tools.internal_gateway.get")`
   - 改为 `patch("domain_agents.policy.tools.policy_tools.get_internal_api_client")`
   - 需要 mock 返回值的 `.get` 方法

6. **tests/apps/test_claim.py**
   - 同上

## 架构改进

### 职责分层

1. **shared/internal_http** - 基础设施层
   - 提供内部服务 HTTP 客户端能力
   - 处理上下文传递、重试、日志等横切关注点
   - 专门用于调用内部微服务 API

2. **domain_agents** - 业务层
   - 实现具体的业务工具（MCP 工具）
   - 使用 `shared/internal_http` 调用后端服务
   - 专注于业务逻辑，不关心 HTTP 细节

3. **tool_service** - 工具服务层
   - 管理工具注册、路由、MCP 协议
   - 不再包含 HTTP 客户端实现

### 上下文传递

`InternalAPIClient` 自动传递以下上下文信息：
- `X-Tenant-Id`: 租户 ID
- `X-Trace-Id`: 追踪 ID
- `X-Conversation-Id`: 会话 ID
- `X-Thread-Id`: 线程 ID
- `X-User-Token`: 用户令牌
- `X-User-Id`: 用户 ID
- `Authorization`: 认证令牌
- `X-Channel-Id`: 渠道 ID
- `X-Tenant-Type`: 租户类型
- `X-Timezone`: 时区
- `Accept-Language`: 语言偏好

## 未来扩展

如果未来需要：

1. **直接调用内部系统 API**（非 MCP）
   - 继续使用 `shared/internal_http/client`
   - 或者创建特定的客户端类继承 `InternalAPIClient`

2. **添加更多 HTTP 客户端功能**
   - 在 `shared/internal_http/client.py` 中扩展
   - 如：缓存、熔断、限流等

3. **支持不同的后端服务**
   - 创建多个 `InternalAPIClient` 实例，指定不同的 `base_url`
   - 或者创建特定服务的客户端类

4. **调用外部第三方 API**
   - 创建新的 `shared/external_http` 模块
   - 与内部服务调用分离，使用不同的配置和策略

## 测试影响

测试需要更新 mock 方式：

### 修改前
```python
with patch("domain_agents.policy.tools.policy_tools.internal_gateway.get",
           new=AsyncMock(return_value=mock_data)):
    result = await query_policy_basic("P2024001")
```

### 修改后
```python
with patch("domain_agents.policy.tools.policy_tools.get_internal_api_client") as mock_client:
    mock_client.return_value.get = AsyncMock(return_value=mock_data)
    result = await query_policy_basic("P2024001")
```

## 优势

1. **职责清晰**：内部 HTTP 客户端在 `shared/internal_http` 层，作为基础设施
2. **命名明确**：`internal_http` 清楚表明是用于内部服务调用
3. **可复用**：任何需要调用内部服务的模块都可以使用
4. **易测试**：单例模式便于 mock
5. **易维护**：HTTP 相关逻辑集中在一处
6. **符合架构**：基础设施层 → 业务层的清晰分层
7. **易扩展**：未来可以添加 `external_http` 用于外部 API 调用
