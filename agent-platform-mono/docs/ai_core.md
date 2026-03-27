# ai_core 层能力设计说明

定位：AI 能力层（与业务无关）。聚焦“如何稳定、高性价比地调用 LLM”，以及 Prompt 的可观测、可治理。对上游 apps 提供统一的推理与 Prompt 获取接口。

## 设计目标
- 稳定：请求超时、重试、熔断、代理切换、降级策略齐备。
- 成本：按 task_type 路由不同模型，兼顾时延与费用；支持本地模型。
- 治理：Prompt 版本化、变更可追溯、线上兜底策略明确。

## 能力总览
- 统一 LLM 客户端（complete/stream）
- Prompt 管理（Langfuse 拉取/本地兜底、变量渲染、缓存）
- 模型路由（simple/complex/local 等；可扩展）
- 观测与降级（日志、埋点、开关、fallback）

### 防腐层（ACL）
- 统一接口：
  - `PromptProvider.get(name, version?) -> str|None`
- 适配器：
  - `LangfusePromptProvider`、`LocalFilePromptProvider`
- 管理器：
  - `PromptManager` 组合多个 Provider，按顺序尝试，成功即返回并缓存
  - 上游仅使用 `prompt_manager.get(name, variables, version)`

### 层级防腐总则
- 上层使用边界：apps/workflows 仅调用 `llm_client`、`prompt_manager`、`routing` 暴露的稳定接口，不直接操作第三方 SDK。
- 下层依赖隔离：所有第三方 SDK（OpenAI/Anthropic/Langfuse 等）只出现在 Provider/Manager 内部；禁止在上层直接 import。
- 签名与语义稳定：接口不随 SDK 升级改变；错误码、用量（tokens）与超时统一归一化。
- 可插拔与降级：主提供者不可用时切换备提供者或本地实现；stream 异常可降级为非流式；Prompt 拉取失败使用本地兜底。
- 配置治理：模型、路由、鉴权与超时在 `settings.*` 中集中管理；支持 Nacos 动态下发与灰度。
- 观测与就绪：关键路径统一打点；/ready 暴露 prompts_ready 与 LLM 相关健康项，便于发布与回滚决策。
## 模块与提供方式

### 1) LLM 客户端
- 位置：`core/ai_core/llm/client.py`
- 能力：
  - 支持 OpenAI/Anthropic/本地模型（settings.llm 配置）
  - 内建：超时、重试（幂等请求）、错误码归一化
- 提供方式：
  - 在 workflow 中通过 `llm_client.get_chat(tools, task_type)` 获取绑定工具的推理实例

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
  - `select_model(task_type: str, options: dict) -> str`
  - 路由策略示例：
    - `simple` → 小模型（快速/低成本）
    - `complex` → 强模型（更高质量）
    - `local` → 本地模型（隐私/内网）
  - 可依据 budget、latency、敏感级别进一步细化
- 提供方式：
  - workflow 中按任务类型选路由，传入到 LLM 客户端

#### 防腐层要点
- 路由策略与模型标识与下层 SDK 解耦；内部维护“策略名 → 模型名/提供者”的映射
- 允许热更新路由配置（Nacos），不影响上游调用签名

## 配置与治理
- 配置入口：`shared/config/settings.py` 下的 `LLMSettings`
  - `LLM_DEFAULT_MODEL`, `LLM_STRONG_MODEL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `LOCAL_MODEL_BASE_URL`
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
  - ai_core 对上层仅暴露 `complete/stream` 与 `get_prompt/select_model` 四个稳定入口
  - 不随 SDK 升级改变签名与语义
- 对内防腐：
  - 第三方 SDK 全部隐藏在 Provider/Manager 内部；统一错误、用量与日志字段
  - 任何替换（新 SDK/新接口）只需更新适配器，不影响上游

## apps 使用边界
- apps/ 或 workflow 只描述“任务类型/约束/变量”
- ai_core 决定“执行何模型/如何渲染 Prompt/如何降级”

## 示例调用
```python
from core.ai_core.prompt.manager import prompt_manager
from core.ai_core.llm.client import llm_client

sys_prompt = prompt_manager.get("policy_agent_system", {"tenant_id": tenant_id})
messages = [{"role": "system", "content": sys_prompt},
            {"role": "user", "content": question}]
llm = llm_client.get_chat(tools=[], task_type="simple")
resp = await llm.ainvoke(messages)
text = resp.content
```
