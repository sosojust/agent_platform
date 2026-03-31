# ai_core 层能力设计说明

定位：AI 能力层（与业务无关）。聚焦“如何稳定、高性价比地调用 LLM”，以及 Prompt 的可观测、可治理。对上游 apps 提供统一的推理与 Prompt 获取接口。

## 设计目标
- 稳定：请求超时、重试、熔断、代理切换、降级策略齐备。
- 成本：按业务场景与能力等级路由不同模型，兼顾时延与费用；支持本地模型。
- 治理：Prompt 版本化、变更可追溯、线上兜底策略明确。

## 能力总览
- 统一 LLM 客户端（complete/stream）
- Prompt 管理（Langfuse 拉取/本地兜底、变量渲染、缓存）
- 双层模型路由（业务语义路由 + LiteLLM 高可用路由）
- 观测与降级（日志、埋点、开关、fallback）

### 防腐层（ACL）
- 统一接口：
  - `PromptProvider.get(name, version?) -> str|None`
- 适配器：
  - `LangfusePromptProvider`、`LocalFilePromptProvider`
- 网关：
  - `PromptGateway` 组合多个 Provider，按顺序尝试，成功即返回并缓存
  - 上游仅使用 `prompt_gateway.get(name, variables, version)`

### 层级防腐总则
- 上层使用边界：apps/workflows 仅调用 `llm_gateway`、`prompt_gateway`、`routing` 暴露的稳定接口，不直接操作第三方 SDK。
- 下层依赖隔离：所有第三方 SDK（OpenAI/Anthropic/Langfuse 等）只出现在 Provider/Manager 内部；禁止在上层直接 import。
- 签名与语义稳定：接口不随 SDK 升级改变；错误码、用量（tokens）与超时统一归一化。
- 可插拔与降级：主提供者不可用时切换备提供者或本地实现；stream 异常可降级为非流式；Prompt 拉取失败使用本地兜底。
- 配置治理：模型、路由、鉴权与超时在 `settings.*` 中集中管理；支持 Nacos 动态下发与灰度。
- 观测与就绪：关键路径统一打点；/ready 暴露 prompts_ready 与 LLM 相关健康项，便于发布与回滚决策。
## 模块与提供方式

### 1) LLM 客户端
- 位置：`core/ai_core/llm/client.py`
- 能力：
  - 统一封装 LiteLLM 的 complete/stream/tool calling 能力，屏蔽下层 SDK 差异
  - 支持 OpenAI/Anthropic/本地模型（settings.llm 配置）
  - 内建：超时、重试（幂等请求）、错误码归一化、fallback
  - 统一费控与用量采集：tenant 级查询对外、conversation 级保护对内
  - 统一缓存策略：由 task_type/scene 决策，不对上游暴露 cache 开关
- 提供方式：
  - 在 workflow 中通过 `llm_gateway.get_chat(tools, task_type|scene)` 获取推理实例
  - 在需要强约束调用时直接使用 `complete/stream`

#### LiteLLM 封装边界（必须遵守）
- 对上游暴露：
  - `complete(messages, task_type, tenant_id, conversation_id, metadata)`
  - `stream(messages, task_type, tenant_id, conversation_id, metadata)`
  - `get_tenant_usage(tenant_id)`、`reset_tenant_budget(tenant_id)`（管理接口）
- 对上游不暴露：
  - LiteLLM Router 负载均衡算法、并发参数、HTTP 重试细节
  - 具体模型标识符与 fallback 链细节
  - 缓存启停布尔参数（由 ai_core 内部策略决定）
- 约束：
  - `tenant_id`、`conversation_id` 使用显式参数透传，禁止依赖隐式全局上下文
  - apps/workflows 不直接调用 ChatOpenAI/ChatAnthropic 等第三方 SDK

#### 防腐层（ACL）设计（LLM 提供者适配）
- 稳定接口：
  - `class ILLMProvider`（示意）
    - `complete(messages, **kwargs) -> (text: str, usage: dict)`
    - `stream(messages, **kwargs) -> AsyncIterator[str]`
  - 由 `llm/client.py` 统一选择并调用，不暴露下层 SDK 差异
- 适配器实现：
  - `OpenAIProvider(ILLMProvider)`、`AnthropicProvider(ILLMProvider)`、`LocalProvider(ILLMProvider)`
  - 统一错误与用量字段规范（error_code、finish_reason、tokens）
- 行为规范：
  - 幂等重试仅针对 `complete`，`stream` 发生错误时降级为 `complete` 或提前结束
  - 统一消息格式：`{"role": "system|user|assistant", "content": "..."}`
  - 统一上下文透传：`tenant_id/conversation_id/thread_id/trace_id`
  - 统一超时与代理设置，禁止在应用层直接操作 SDK 配置

### 2) Prompt 管理
- 位置：`core/ai_core/prompt/manager.py`
- 能力：
  - `get(name: str, variables?: dict, version?: str) -> str`
  - 优先从 Langfuse 拉取指定版本；失败时使用本地 fallback
  - 变量渲染（Jinja2/简单模板器），支持默认变量（tenant_id 等）
  - 本地缓存（内存/可选持久）
- 提供方式：
  - 在构造 messages 前调用，返回最终可用的 prompt 文本

#### Langfuse Prompt 命名约定与清单
- 命名约定：
  - 业务 Agent 系统提示词：`{domain}_agent_system`（例如：`policy_agent_system`）
  - 平台通用能力提示词：`{module}_{action}_{role}`（例如：`tool_router_select_sys`、`tool_router_select_user`）
- 当前关键 Prompt Key（建议在 Langfuse 中同名维护）：
  - `policy_agent_system`
  - `claim_agent_system`
  - `customer_agent_system`
  - `tool_router_select_sys`
  - `tool_router_select_user`
- 回退约定：
  - Langfuse 中不存在或拉取失败时，按 `LocalFilePromptProvider` 规则回退到本地模板文件
  - `tool_router_select_sys` → `core/ai_core/prompt/tool_router_select_sys.txt`
  - `tool_router_select_user` → `core/ai_core/prompt/tool_router_select_user.txt`

#### 防腐层要点
- 与 Langfuse/第三方存储交互统一封装在 `prompt/manager.py`，上游仅依赖 `get_prompt(name, variables)`
- 失败与超时策略统一由管理器处理，避免上游直接感知第三方 API 差异

### 3) 模型路由
- 位置：`core/ai_core/routing/router.py`
- 能力：
  - 业务语义路由：`select_model(scene: str, force_local: bool=False) -> ModelSpec`
  - 路由维度：能力等级（nano/simple/medium/complex）+ 数据安全约束（sensitive）
  - 可按业务场景声明策略（policy_query、claim_reason、customer_faq、*_rag_rewrite）
- 提供方式：
  - workflow/apps 传 `scene`（业务语义），ai_core 输出统一 `model` 与 `task_type`

#### 双层 Router 职责边界
- ai_core `router.py`：
  - 负责“什么业务场景用什么模型名”
  - 只处理业务语义、能力等级、安全约束
- LiteLLM Router：
  - 负责“同一个模型名如何高可用调用”
  - 处理限流、负载均衡、重试、fallback、多 key 调度
- 串联关系：
  - `scene -> ai_core router.py -> model_name -> LiteLLM Router -> deployment`

#### 防腐层要点
- 路由策略与模型标识与下层 SDK 解耦；内部维护“策略名 → 模型名/提供者”的映射
- 允许热更新路由配置（Nacos），不影响上游调用签名

## 配置与治理
- 配置入口：`shared/config/settings.py` 下的 `LLMSettings`
  - `LLM_DEFAULT_MODEL`, `LLM_STRONG_MODEL`, `LLM_MEDIUM_MODEL`, `LLM_NANO_MODEL`, `LLM_LOCAL_MODEL`
  - `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `LOCAL_MODEL_BASE_URL`
- 观测：
  - 统一日志（structlog）：模型名、tokens、耗时、tenant_id/trace_id
  - 可选上报 Langfuse/OTel（settings.observability）
- 降级：
  - 主提供商不可用 → 切换备提供商/本地模型
  - streaming 出错 → 降级为非流式
  - Prompt 拉取失败 → 使用本地 fallback

### 就绪与来源可见性
- /ready 探针：
  - `prompts_ready`：模板可获取并渲染
  - `models`：Embedding/Rerank 模型预热完成
- 来源可见性：
  - `prompts_source_langfuse`：为 true 表示当前 Prompt 来源为 Langfuse；为 false 表示使用本地兜底

## 层级稳定与依赖防腐（总则）
- 对外稳定：
  - ai_core 对上层仅暴露 `complete/stream/get_chat` 与 `get_prompt/select_model` 稳定入口
  - 不随 SDK 升级改变签名与语义
- 对内防腐：
  - 第三方 SDK 全部隐藏在 Provider/Manager 内部；统一错误、用量与日志字段
  - 任何替换（新 SDK/新接口）只需更新适配器，不影响上游

## apps 使用边界
- apps/ 或 workflow 只描述“业务场景/约束/变量”
- ai_core 决定“执行何模型/如何渲染 Prompt/如何降级”

## 示例调用
```python
from core.ai_core.prompt.manager import prompt_gateway
from core.ai_core.llm.client import llm_gateway

sys_prompt = prompt_gateway.get("policy_agent_system", {"tenant_id": tenant_id})
messages = [{"role": "system", "content": sys_prompt},
            {"role": "user", "content": question}]
llm = llm_gateway.get_chat(tools=[], scene="policy_query")
resp = await llm.ainvoke(messages)
text = resp.content
```
