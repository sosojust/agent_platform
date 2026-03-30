# 架构约束（Architecture Constraints）

## 层级边界
- `apps/` 仅通过平台稳定接口使用能力：`agent_engine(factory/run/stream)`, `tool_service(list_tools/invoke)`, `ai_core(llm_client/prompt_manager/routing)`, `memory_rag(embedding_service/rag_pipeline)`
- 禁止在上层直接 import 第三方 SDK（OpenAI/Anthropic/Langfuse/Qdrant 等）；差异由各层适配器/管理器内部屏蔽
- 多租户隔离全链路透传：`tenant_id` 必须出现在 workflow 状态、工具调用、检索过滤与日志中

## 防腐层总则（ACL）
- 稳定接口与语义：对上暴露的接口签名与错误语义保持稳定；升级第三方 SDK 不改变上层使用方式
- 适配器隔离：第三方 SDK/后端差异仅在 Provider/Adapter 内部出现；上层只依赖统一抽象
- 可插拔与降级：主提供者不可用时自动切换备提供者或本地实现；流式出错可降级为非流式；Prompt 拉取失败使用本地兜底
- 配置治理：模型/路由/端点/鉴权/超时在 `shared/config/settings.py` 与 Nacos 管理；禁止硬编码
- 观测与就绪：关键链路统一打点；/ready 暴露分项检查（`prompts_ready`、`rag_ready`、`rerank_available`、`redis`、`qdrant` 等）

## ai_core 约束
- Prompt 管理：仅使用 `prompt_manager.get(name, variables, version)`；内部通过 `PromptProvider` 链（Langfuse→本地）实现
- LLM 客户端与路由：仅使用 `llm_client.get_chat(tools, task_type)` 与 `routing.select_model(task_type)`；禁止直接实例化 ChatOpenAI 等 SDK
- 安全与审计：Prompt 变量采用白名单；禁止在日志中输出密钥与敏感变量

## memory_rag 约束
- Embedding 一致性：查询与入库向量统一通过 `embedding_service` 生成（复用 ai_core Provider），确保同一向量空间
- RAG Pipeline：仅构造通用 Filter DSL 与检索参数；后端翻译在 VectorStore 适配器层执行
- VectorStore 适配器：实现 `create_collection/add_texts/upsert/search/delete/by_ids/list_collections`；强制注入 `tenant_id` 过滤；Metadata 字段白名单与类型校验
- Collection 命名：`{tenant_id}_{type}` 强制规范；示例阶段 Filter DSL 支持 `EQ/AND`，后续按业务扩展
- Rerank 降级：未加载模型时降级为顺序截取 `top_k`，并在 /ready 暴露 `rerank_available`

## tool_service 约束
- 统一入口：工具仅通过 `registry.list_tools()` 与 `registry.invoke()` 使用；禁止越过工具层直连外部 MCP 或业务网关
- 适配器治理：外部系统协议差异（认证/超时/错误码）封装在 MCP/网关适配器；统一错误归一化
- 应用级鉴权：`X-App-Id/X-App-Token` 必填，配额/限流以 App 维度治理

## agent_engine 约束
- 合同：apps 注册必须提供 `factory() -> Graph`，并注入 `checkpointer/thread_id`
- 基础工作流：优先复用 `base_agent` 与标准节点（记忆→RAG→推理→工具→记忆）
- 观测：日志统一使用 `shared/logging` 输出 JSON，绑定 `tenant_id/trace_id/conversation_id/thread_id`
- ToolRouter：工具选择策略实现于 `agent_engine` 层；apps 只提供候选集合与元数据（`name/description/keywords/tool`），最终工具列表在构建 Graph 前选择并注入

## 就绪与发布
- 冷启动预热：Embedding/Rerank 模型预热完成后设置 `models`；Prompts 与 RAG 分项检查通过后才对外 /ready=200
- 灰度与回滚：根据 /ready detail 与观测指标（降级次数/不可翻译比例/错误率）决策放量与回滚

## 质量门禁（建议）
- 测试：新增/变更需具备最小单元/集成/E2E 用例（PromptManager、VectorStoreAdapter、RagPipeline、基础编排）
- Lint 与类型：在提交前运行 `ruff check`、`mypy`；保持严格类型与规范
- 覆盖率：为关键链路设定最低覆盖率门槛（建议 ≥ 70%），在 CI 中校验
