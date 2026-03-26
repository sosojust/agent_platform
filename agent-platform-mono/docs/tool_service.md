# tool_service 层能力设计说明

定位：统一工具接入层。聚合本地 Skill 与 MCP（内部/外部），对上游暴露统一的工具清单与调用接口，提供应用级鉴权与可观测性。

## 设计目标
- 统一：无论工具来源（Skill/MCP），统一注册、统一调用。
- 安全：按调用方应用（App-Id）进行鉴权与配额治理。
- 可扩展：支持内部 mcp-service 与外部 MCP 提供者。

## 能力总览
- 工具注册表（Skill + MCP）
- Skill 装饰器（本地函数快速注册）
- MCP 客户端（内部/外部）
- HTTP API：/tools、/tools/invoke
- 应用级鉴权（X-App-Id/X-App-Token）

## 模块与提供方式

### 1) 工具注册表
- 位置：`core/tool_service/registry.py`
- 能力：
  - `register_skill(name, func, input_schema?, output_schema?)`
  - `register_mcp_client(provider, client)`（client 需实现 `list_tools` 与 `invoke`）
  - `list_tools() -> list[dict]`
  - `invoke(tool_name: str, arguments: dict) -> Any`
- 行为：
  - Skill 工具登记为 `skill:{name}`
  - MCP 工具登记为 `{provider}:{tool_name}`

### 2) Skill 装饰器
- 位置：`core/tool_service/skills/base.py`
- 能力：
  - `@skill(name?, input_schema?, output_schema?)`
  - 装饰函数自动注册到工具注册表
- 使用：
  - 推荐在 apps/*/tools 中定义领域工具时使用

### 3) MCP 客户端
- 位置：`core/tool_service/mcp/`
  - `service_client.py`：内部 mcp-service 客户端（/tools 与 /invoke）
  - `external_client.py`：通用外部 MCP 客户端
- 提供方式：
  - 在应用启动阶段注册：
    - 内部：`await registry.register_mcp_client("mcp", MCPServiceClient())`
    - 外部：遍历 `settings.external_mcp_endpoints` 注册 `ExternalMCPClient`

### 4) HTTP API
- 位置：`main.py`
- 路由：
  - `GET /tools` → 列出所有工具（Skill + MCP）
  - `POST /tools/invoke` → 调用工具（body: `{"tool": "...", "arguments": {...}}`）
- 鉴权：
  - 请求头 `X-App-Id`, `X-App-Token`，由 `settings.tool_auth_map` 进行校验
  - 统一按调用方应用鉴权，而非每 endpoint 独立鉴权

## 配置与治理
- 配置入口：`shared/config/settings.py`
  - `mcp_service_url`：内部 mcp-service 地址
  - `external_mcp_endpoints`：外部 MCP 列表
  - `external_mcp_token`：统一 token（如需）
  - `tool_auth_map`：应用级鉴权表（`{"app-ops":"s3cr3t", ...}`）
- 观测：
  - 工具清单与调用日志统一记录（含 tenant_id/trace_id/app_id）
  - 可扩展限流/配额（按 App-Id）

## 上下文四元透传（必备）
- 透传元素：
  - `tenant_id` → 请求头 `X-Tenant-Id`
  - `conversation_id` → 请求头 `X-Conversation-Id`
  - `thread_id` → 请求头 `X-Thread-Id`（默认为 `conversation_id`，可派生）
  - `trace_id` → 请求头 `X-Trace-Id`
- 工具层注入点：
  - `core/tool_service/client/gateway.py` 自动注入上述四元（来源于 contextvars）
  - 如果存在用户令牌（`X-User-Token`），也会一并转发到网关
- 日志绑定：
  - 中间件将四元绑定到日志上下文，便于全链路观测与审计

## 后续扩展（鉴权与用户令牌）
- 支持将 `X-User-Token` 纳入上下文，作为用户态鉴权凭据；
- 工具层默认透传该 Token 到网关，建议在业务系统侧验证；
- 可按 App-Id + 用户 Token 组合做更细粒度的权限和配额控制。

## 依赖防腐层（ACL）设计
- 稳定接口：
  - 注册表对外提供稳定的 `list_tools/invoke`，不暴露下游实现差异
  - MCP 客户端统一接口（示意）：`list_tools() -> list[dict]`、`invoke(tool_name, args) -> Any`
- 适配器：
  - 内部 mcp-service 适配器：HTTP schema 与调用约定封装在 `service_client.py`
  - 外部 MCP 适配器：`external_client.py` 负责外部协议差异（认证/超时/错误码）
  - 业务网关适配器：`client/gateway.py` 统一 header/重试/观测，屏蔽下游差异
- 规范化：
  - 输入/输出 schema 在工具注册阶段校验与归一化（字段类型、必填项）
  - 错误归一化：统一错误码与 message，确保上游只处理稳定错误语义
- 变更与替换：
  - 新的 MCP 提供者仅需实现同名接口并注册即可，不影响 apps
  - 下游网关协议变更只更新适配器，不影响工具调用层

## 层级防腐总则
- 上层使用边界：apps 与编排层仅通过 `registry.list_tools()` 与 `registry.invoke()` 使用工具能力；禁止直接调用外部 MCP 或业务网关。
- 下层依赖隔离：外部系统（mcp-service/外部 MCP/业务网关）的协议与认证差异全部封装在适配器内；上层不 import 下游 SDK。
- 签名与语义稳定：`list_tools/invoke` 的接口语义稳定；错误码与消息统一归一化，避免上层处理下游差异。
- 可插拔与降级：新增或替换 MCP 提供者只需注册适配器；调用失败可按策略重试或降级（返回一致的错误语义）。
- 配置治理：端点、鉴权、配额与限流在 `settings.*` 与 Nacos 统一配置与灰度；禁止在上层硬编码。
- 观测与就绪：工具调用统一埋点与日志穿透（tenant_id/trace_id/app_id）；必要时在 /ready 增加工具服务相关健康项以配合发布与回滚。
## apps 使用边界
- apps 可以：
  - 使用 `@skill` 暴露本地能力
  - 通过注册表间接调用 MCP 工具
- apps 不需要：
  - 关心工具来源与调用细节（重试、鉴权、路由由工具层处理）

## 示例
### 1) 注册本地 Skill
```python
from core.tool_service.skills.base import skill

@skill(name="format_policy_id")
async def format_policy_id(args: dict) -> dict:
    pid = str(args.get("policy_id", "")).strip().upper()
    return {"normalized": pid}
```

### 2) 调用 MCP 工具（透传）
```python
from core.tool_service import registry

res = await registry.invoke("mcp:query_policy_basic", {"policy_id": "P2024001"})
```

### 3) HTTP 调试
```bash
curl -H "X-App-Id: app-ops" -H "X-App-Token: s3cr3t" http://localhost:8000/tools
curl -X POST -H "Content-Type: application/json" \
     -H "X-App-Id: app-ops" -H "X-App-Token: s3cr3t" \
     -d '{"tool":"skill:format_policy_id","arguments":{"policy_id":" p2024001 "}}' \
     http://localhost:8000/tools/invoke
```
