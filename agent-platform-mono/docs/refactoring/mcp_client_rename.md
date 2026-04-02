# MCP Client 重命名和改进

## 问题描述

`core/tool_service/mcp/` 目录下的客户端命名不够明确：

- `service_client.py` (MCPServiceProvider) - 实际是调用内部 MCP 服务
- `external_client.py` (ExternalMCPProvider) - 调用外部 MCP 服务器

问题：
1. `service_client` 这个名字不够明确，看不出是内部还是外部
2. 内部 MCP 客户端没有透传完整的上下文信息（只传了 tenant_id 和 trace_id）
3. 类名 `MCPServiceProvider` 和 `ExternalMCPProvider` 不对称

## 解决方案

### 重命名

1. **service_client.py → internal_client.py**
   - `MCPServiceProvider` → `InternalMCPClient`
   - 明确表示这是内部 MCP 服务客户端

2. **external_client.py 保持不变，但重命名类**
   - `ExternalMCPProvider` → `ExternalMCPClient`
   - 与 `InternalMCPClient` 对称

### 功能改进

**InternalMCPClient** 现在透传完整的上下文信息：
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
- `X-Source`: 来源标识（固定为 "agent"）

这与 `shared/internal_http/client.py` 保持一致。

## 修改内容

### 新增文件

1. **core/tool_service/mcp/internal_client.py**
   - `InternalMCPClient` 类
   - 完整的上下文透传
   - 详细的文档注释

### 修改文件

1. **core/tool_service/mcp/external_client.py**
   - 重命名类：`ExternalMCPProvider` → `ExternalMCPClient`
   - 添加文档注释
   - 改进代码格式

2. **core/tool_service/mcp/__init__.py**
   - 导出 `InternalMCPClient` 和 `ExternalMCPClient`
   - 添加 `__all__`

3. **app/gateway/lifespan.py**
   - 导入从 `MCPServiceProvider` 改为 `InternalMCPClient`
   - 导入从 `ExternalMCPProvider` 改为 `ExternalMCPClient`
   - 使用新的类名

### 删除文件

- `core/tool_service/mcp/service_client.py`

## 架构改进

### 命名对称性

**修改前**:
```python
MCPServiceProvider      # 内部服务
ExternalMCPProvider     # 外部服务
```

**修改后**:
```python
InternalMCPClient       # 内部服务
ExternalMCPClient       # 外部服务
```

### 上下文透传

**修改前** (InternalMCPClient 的前身):
```python
def _headers(self) -> Dict[str, str]:
    h: Dict[str, str] = {}
    tid = get_current_tenant_id()
    rid = get_current_trace_id()
    if tid:
        h["X-Tenant-Id"] = tid
    if rid:
        h["X-Trace-Id"] = rid
    return h
```

**修改后**:
```python
def _headers(self) -> Dict[str, str]:
    """构建请求头，透传所有上下文字段"""
    h: Dict[str, str] = {
        "X-Tenant-Id": get_current_tenant_id(),
        "X-Trace-Id": get_current_trace_id(),
        "X-Conversation-Id": get_current_conversation_id(),
        "X-Thread-Id": get_current_thread_id() or get_current_conversation_id(),
        "X-Source": "agent",
        "Content-Type": "application/json",
    }
    
    # ... 透传所有其他上下文字段
    return h
```

## 职责划分

### InternalMCPClient
- **用途**: 调用内部 MCP 服务（如 mcp-service）
- **认证**: 通过上下文透传（租户、用户等）
- **特点**: 
  - 自动注入所有上下文信息
  - 使用内部服务 URL（从配置读取）
  - 支持重试机制

### ExternalMCPClient
- **用途**: 调用外部第三方 MCP 服务器
- **认证**: 使用 Bearer Token
- **特点**:
  - 不透传内部上下文（安全考虑）
  - 需要显式指定 base_url
  - 支持重试机制

## 使用示例

### 注册内部 MCP 服务

```python
from core.tool_service.mcp.internal_client import InternalMCPClient

# 使用默认配置（从 settings.mcp_service_url 读取）
internal_client = InternalMCPClient()

# 或指定自定义 URL
internal_client = InternalMCPClient(base_url="http://custom-mcp:8004")

# 注册到工具网关
await tool_gateway.register_mcp_provider("mcp", internal_client)
```

### 注册外部 MCP 服务器

```python
from core.tool_service.mcp.external_client import ExternalMCPClient

# 使用 token 认证
external_client = ExternalMCPClient(
    base_url="https://external-mcp.example.com",
    token="your-api-token"
)

# 注册到工具网关
await tool_gateway.register_mcp_provider("ext1", external_client)
```

## 优势

1. **命名清晰**: `Internal` vs `External` 一目了然
2. **对称性**: 两个类名结构一致（`*MCPClient`）
3. **上下文完整**: 内部客户端透传所有必要的上下文信息
4. **安全性**: 外部客户端不泄露内部上下文
5. **一致性**: 与 `shared/internal_http/client.py` 的上下文透传保持一致
6. **可维护**: 清晰的职责划分和文档注释

## 未来扩展

如果需要支持更多类型的 MCP 客户端：

1. **混合模式客户端**: 既透传上下文又使用 token
   ```python
   class HybridMCPClient(InternalMCPClient):
       def __init__(self, base_url: str, token: str):
           super().__init__(base_url)
           self._token = token
       
       def _headers(self):
           h = super()._headers()
           h["Authorization"] = f"Bearer {self._token}"
           return h
   ```

2. **缓存客户端**: 添加工具列表缓存
3. **熔断客户端**: 添加熔断器模式
4. **监控客户端**: 添加调用指标收集
