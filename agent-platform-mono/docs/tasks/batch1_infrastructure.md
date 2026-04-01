# Batch 1 — 基础设施层开发任务

## 概述

基础设施层是整个架构的底座，包含上下文管理、国际化、数据分层、向量检索、Memory 等核心能力。本批次任务有严格的依赖顺序，必须按序完成。

---

## Task 1.1 — 上下文模型扩展

**优先级**: P0  
**预计工时**: 2 天  
**依赖**: 无  
**被依赖**: 1.7, 2.1, 3.2, 3.3  
**状态**: ✅ 已完成

### 目标

扩展 `shared/middleware/tenant.py`，新增 6 个上下文字段，支持 `Authorization: Bearer {token}` 标准格式。

### 实现清单

#### 1. `shared/middleware/tenant.py`

✅ 新增 ContextVar 字段：

```python
# 新增字段
current_user_id: ContextVar[str] = ContextVar("user_id", default="")
current_auth_token: ContextVar[str] = ContextVar("auth_token", default="")
current_channel_id: ContextVar[str] = ContextVar("channel_id", default="")
current_tenant_type: ContextVar[str] = ContextVar("tenant_type", default="")
current_locale: ContextVar[str] = ContextVar("locale", default="zh-CN")
current_timezone: ContextVar[str] = ContextVar("timezone", default="Asia/Shanghai")

# Authorization 解析逻辑
auth_header = request.headers.get("Authorization", "")
token = auth_header.removeprefix("Bearer ").strip()
current_auth_token.set(token)

# 每个字段提供 getter/setter
def get_current_user_id() -> str: ...
def set_current_user_id(value: str) -> None: ...
# ... 其他字段同理
```

✅ structlog contextvars 绑定：`user_id`, `channel_id`, `locale`

#### 2. `tool_service/client/gateway.py`

✅ 更新 `_headers()` 方法：

```python
def _headers(self) -> dict[str, str]:
    h = {}
    if tenant_id := get_current_tenant_id():
        h["X-Tenant-Id"] = tenant_id
    if user_id := get_current_user_id():
        h["X-User-Id"] = user_id
    if token := get_current_auth_token():
        h["Authorization"] = f"Bearer {token}"
    if channel_id := get_current_channel_id():
        h["X-Channel-Id"] = channel_id
    if tenant_type := get_current_tenant_type():
        h["X-Tenant-Type"] = tenant_type
    if timezone := get_current_timezone():
        h["X-Timezone"] = timezone
    h["Accept-Language"] = get_current_locale() or "zh-CN"
    return h
```

#### 3. `shared/models/schemas.py`

✅ `AgentRunRequest` 增加可选字段：

```python
@dataclass
class AgentRunRequest:
    # 已有字段...
    user_id: str = ""
    channel_id: str = ""
    locale: str = ""
    timezone: str = ""
```

### 验收标准

- [x] 所有新字段的注入、读取、缺失默认值单测
- [x] `Authorization: Bearer {token}` 解析单测（含格式错误容错）
- [x] `Authorization: invalid_format` 不抛异常，token 为空字符串
- [x] structlog 日志包含 `user_id`, `channel_id`, `locale`
- [x] `tool_service` 透传所有新字段的集成测试

### 测试结果

```
tests/shared/test_tenant_middleware.py::test_new_context_fields_injection PASSED
tests/shared/test_tenant_middleware.py::test_authorization_bearer_parsing PASSED
tests/shared/test_tenant_middleware.py::test_authorization_bearer_invalid_format PASSED
tests/shared/test_tenant_middleware.py::test_missing_headers_default_values PASSED
tests/shared/test_tenant_middleware.py::test_setter_functions PASSED
tests/shared/test_tenant_middleware.py::test_authorization_bearer_with_extra_spaces PASSED
tests/shared/test_tenant_middleware.py::test_all_fields_together PASSED

7 passed in 0.11s
```

---

## Task 1.2 — 国际化基础层（i18n）

**优先级**: P0  
**预计工时**: 3 天  
**依赖**: 无  
**被依赖**: 1.6, 1.7, 2.2, 3.1, 3.3

### 目标

构建完整的 i18n 基础设施，支持 locale 标准化、fallback 链、文案翻译、时区转换。

### 实现清单

#### 1. 目录结构

```
shared/i18n/
├── __init__.py
├── locale.py          # locale 解析、标准化、fallback 链
├── translator.py      # 系统固定文案翻译
├── timezone.py        # 时区转换工具
└── locales/
    ├── zh-CN.json
    ├── en-US.json
    └── ja-JP.json
```

#### 2. `shared/i18n/locale.py`

```python
SUPPORTED_LOCALES = {"zh-CN", "en-US", "ja-JP"}
DEFAULT_LOCALE = "zh-CN"

FALLBACK_CHAIN: dict[str, list[str]] = {
    "zh-TW": ["zh-CN", "en-US"],
    "zh-HK": ["zh-CN", "en-US"],
    "ja-JP": ["ja-JP", "zh-CN", "en-US"],
    "en-GB": ["en-US"],
}

def normalize_locale(raw: str) -> str:
    """zh→zh-CN, en→en-US, 不识别→DEFAULT_LOCALE"""

def get_fallback_chain(locale: str) -> list[str]:
    """返回包含自身的完整 fallback 列表"""
```

#### 3. `shared/i18n/translator.py`

```python
def t(key: str, locale: str | None = None, **kwargs) -> str:
    """
    locale 不传则从 current_locale() 读取
    key 不存在时按 fallback 链降级，最终返回 key 本身
    支持变量插值：t("error.not_found", name="保单")
    """
```

#### 4. `shared/i18n/locales/zh-CN.json`

核心条目（至少包含）：

```json
{
  "error.budget_exceeded": "当前会话 Token 用量已超限",
  "error.provider_timeout": "模型响应超时，请稍后重试",
  "error.provider_rate_limited": "请求过于频繁，请稍后重试",
  "error.tool_not_found": "工具 {name} 不存在",
  "error.tool_execution_failed": "工具 {name} 执行失败：{reason}",
  "memory.related": "相关记忆",
  "memory.recent": "近期对话",
  "retrieval.platform": "平台知识",
  "retrieval.channel": "渠道信息",
  "retrieval.tenant": "企业知识库",
  "retrieval.user": "用户信息",
  "tool.context_header": "工具执行结果",
  "instruction.respond_in_locale": "请用 {language} 回答。"
}
```

`en-US.json` 和 `ja-JP.json` 提供对应翻译。

#### 5. `shared/i18n/timezone.py`

```python
def to_user_timezone(utc_ts: int, timezone: str) -> str:
    """UTC timestamp → 用户时区可读时间"""

def parse_user_time(time_str: str, timezone: str) -> int:
    """用户本地时间字符串 → UTC timestamp"""
```

### 验收标准

- [ ] `normalize_locale("zh")` → `"zh-CN"`
- [ ] `normalize_locale("unknown")` → `"zh-CN"`
- [ ] `get_fallback_chain("zh-TW")` → `["zh-TW", "zh-CN", "en-US"]`
- [ ] `t("error.tool_not_found", name="test")` 插值正确
- [ ] `t("non.exist.key")` 返回 `"non.exist.key"`
- [ ] `t("error.budget_exceeded", locale="en-US")` 返回英文
- [ ] 时区转换：UTC 1711929600 → `Asia/Shanghai` 正确显示

---

## Task 1.3 — 数据分层模型

**优先级**: P0  
**预计工时**: 待定  
**依赖**: 无  
**被依赖**: 1.4, 1.5, 1.6, 1.7  
**状态**: ⏸️ 已暂停（待架构讨论）

### 暂停原因

在实现过程中发现数据建模需要更深入的架构讨论：

1. **平台 vs 业务边界**：如何在平台层定义数据分层，同时不限制业务层的建模自由度
2. **向量库建模规范**：需要先梳理清楚整体的数据模型体系
3. **扩展性设计**：如何支持不同业务场景（保险、HR、客服等）的数据类型定义

### 待讨论的问题

1. **Scope 定义**：
   - Platform/Channel/Tenant/User 四层分类是否合理？
   - 是否需要更灵活的分层机制？

2. **数据类型管理**：
   - 平台层应该定义哪些约束？
   - 业务层如何自由扩展数据类型？
   - 如何避免类型冲突？

3. **Collection 命名**：
   - 命名规范是否足够灵活？
   - 如何支持动态创建的业务场景？

4. **元数据结构**：
   - ChunkMetadata 应该包含哪些字段？
   - 如何平衡通用性和业务特定需求？

### 后续计划

1. 梳理整体数据模型体系
2. 讨论向量库建模规范
3. 确定平台层和业务层的职责边界
4. 重新设计并实现 Task 1.3

### 对其他任务的影响

- Task 1.4（向量库适配层）：可以先实现基础的 CRUD 接口，暂不依赖具体的数据模型
- Task 1.5（IngestGateway）：暂缓，等待数据模型确定
- Task 1.6（检索层）：暂缓，等待数据模型确定
- Task 1.7（Memory 层）：暂缓，等待数据模型确定

---

## Task 1.4 — 向量库适配层重写

**优先级**: P0  
**预计工时**: 3 天  
**依赖**: 1.3  
**被依赖**: 1.4.5, 1.5, 1.6, 1.7

---

## Task 1.4.5 — shared/libs 基础工具库

**优先级**: P0  
**预计工时**: 1 天  
**依赖**: 无  
**被依赖**: 1.5

### 目标

建立 `shared/libs/` 目录，定义 PDF 解析等基础工具的接口和目录结构，不做实际实现。

### 实现清单

#### 1. 目录结构

```
shared/libs/
├── __init__.py
├── pdf/
│   ├── __init__.py
│   └── parser.py      # PDF 解析接口定义
├── excel/
│   ├── __init__.py
│   └── parser.py      # Excel 解析接口（预留）
└── ocr/
    ├── __init__.py
    └── engine.py      # OCR 接口（预留）
```

#### 2. `shared/libs/pdf/parser.py` 接口定义

```python
"""
PDF 解析基础能力
纯工具函数库，无任何框架依赖
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class PageText:
    """单页文本"""
    page_num: int
    text: str
    metadata: dict


class PDFParser(Protocol):
    """PDF 解析器接口"""
    
    def extract_text(self, pdf_bytes: bytes) -> str:
        """
        提取 PDF 全文
        
        Args:
            pdf_bytes: PDF 文件字节流
            
        Returns:
            提取的文本内容
            
        注意：本次不做实际实现，返回占位符
        """
        ...
    
    def extract_pages(self, pdf_bytes: bytes) -> list[PageText]:
        """
        按页提取 PDF 文本
        
        Args:
            pdf_bytes: PDF 文件字节流
            
        Returns:
            每页的文本内容列表
            
        注意：本次不做实际实现，返回占位符
        """
        ...


class SimplePDFParser:
    """
    简单 PDF 解析器实现（占位符）
    
    实际项目中应使用 pymupdf / pdfplumber 等库实现
    本次仅提供接口和结构，不做真实解析
    """
    
    def extract_text(self, pdf_bytes: bytes) -> str:
        """占位实现：返回提示信息"""
        return "[PDF_CONTENT_PLACEHOLDER] PDF parsing not implemented yet"
    
    def extract_pages(self, pdf_bytes: bytes) -> list[PageText]:
        """占位实现：返回单页占位符"""
        return [
            PageText(
                page_num=1,
                text="[PDF_PAGE_PLACEHOLDER] PDF parsing not implemented yet",
                metadata={"total_pages": 1}
            )
        ]


# 默认解析器实例
default_parser = SimplePDFParser()


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    便捷函数：提取 PDF 全文
    
    使用示例：
        from shared.libs.pdf.parser import extract_text_from_pdf
        text = extract_text_from_pdf(pdf_bytes)
    """
    return default_parser.extract_text(pdf_bytes)


def extract_pages_from_pdf(pdf_bytes: bytes) -> list[PageText]:
    """
    便捷函数：按页提取 PDF 文本
    
    使用示例：
        from shared.libs.pdf.parser import extract_pages_from_pdf
        pages = extract_pages_from_pdf(pdf_bytes)
    """
    return default_parser.extract_pages(pdf_bytes)
```

#### 3. `shared/libs/pdf/__init__.py`

```python
"""PDF 解析工具"""

from .parser import (
    PDFParser,
    SimplePDFParser,
    PageText,
    extract_text_from_pdf,
    extract_pages_from_pdf,
)

__all__ = [
    "PDFParser",
    "SimplePDFParser",
    "PageText",
    "extract_text_from_pdf",
    "extract_pages_from_pdf",
]
```

#### 4. `shared/libs/__init__.py`

```python
"""
shared/libs - 基础工具库

存放与业务无关、与框架无关的纯工具能力：
- PDF 解析
- Excel 解析
- OCR 识别
- 文档格式转换
等

特点：
1. 无框架依赖（不依赖 FastAPI / LangGraph / tool_service）
2. 纯函数式（输入 → 输出，无副作用）
3. 可被任何层级直接 import
"""
```

#### 5. 使用场景说明文档

创建 `shared/libs/README.md`：

```markdown
# shared/libs - 基础工具库

## 设计原则

1. **纯工具函数**：无框架依赖，无副作用
2. **直接调用**：不经过网关，不需要鉴权
3. **共享复用**：可被任何层级 import

## 使用场景

### 场景 A：IngestGateway 写入时的 PDF 解析

```python
# core/memory_rag/ingest/gateway.py
from shared.libs.pdf import extract_text_from_pdf

class IngestGateway:
    async def ingest(self, req: IngestRequest) -> IngestResult:
        if isinstance(req.content, bytes):
            # 直接调用，无需经过 tool_service
            text = extract_text_from_pdf(req.content)
        else:
            text = req.content
        # ... 后续处理
```

### 场景 B：doc_agent 处理 PDF 时的解析

```python
# domain_agents/doc/tools/doc_tools.py
from shared.libs.pdf import extract_text_from_pdf
from core.tool_service.skills.base import skill

@skill(
    name="parse_pdf",
    description="解析 PDF 文件内容",
    keywords=["PDF", "解析", "文档"],
)
async def parse_pdf(args: dict) -> dict:
    pdf_bytes = args["pdf_bytes"]
    # 内部调用 shared.libs，外部通过 tool_service 暴露
    text = extract_text_from_pdf(pdf_bytes)
    return {"text": text, "status": "success"}
```

## 目录结构

```
shared/libs/
├── pdf/          # PDF 解析
├── excel/        # Excel 解析（预留）
└── ocr/          # OCR 识别（预留）
```

## 实现说明

**当前阶段**：仅提供接口定义和占位实现，不做真实解析。

**后续实现**：可选择以下库实现真实解析能力：
- PDF: pymupdf / pdfplumber / pypdf2
- Excel: openpyxl / xlrd
- OCR: pytesseract / paddleocr

## 与 tool_service 的关系

- `shared/libs`: 纯工具能力，无鉴权、无租户隔离
- `tool_service`: 业务工具层，有鉴权、有可观测性

domain_agents 通过 `@skill` 包装 `shared/libs` 能力，注册到 tool_service。
```

### 验收标准

- [ ] `shared/libs/` 目录结构创建完成
- [ ] `PDFParser` 接口定义清晰
- [ ] `SimplePDFParser` 占位实现可调用（返回占位符）
- [ ] `extract_text_from_pdf` 便捷函数可用
- [ ] `extract_pages_from_pdf` 便捷函数可用
- [ ] README.md 说明两种使用场景
- [ ] 单测：调用占位实现返回预期占位符
- [ ] 文档：说明后续如何替换为真实实现

---

## Task 1.5 — 写入层：IngestGateway

**优先级**: P0  
**预计工时**: 3 天  
**依赖**: 1.3, 1.4, 1.4.5  
**被依赖**: 1.7

### 目标

重写 `VectorAdapter` 抽象接口和 `QdrantAdapter` 实现，支持完整 Filter DSL、幂等建表、score_threshold 过滤。

### 实现清单

#### 1. `core/memory_rag/vector/adapter.py`

```python
class VectorAdapter(ABC):
    @abstractmethod
    def ensure_collection(self, name: str, dim: int) -> None:
        """幂等建表，已存在则跳过"""

    @abstractmethod
    def upsert(self, collection: str, records: list[dict]) -> None:
        """批量写入/更新"""

    @abstractmethod
    def search(
        self,
        collection: str,
        query_vector: list[float],
        top_k: int,
        filter_expr: dict | None = None,
        score_threshold: float = 0.0,
    ) -> list[dict]:
        """向量检索，支持过滤和分数阈值"""

    @abstractmethod
    def delete_by_filter(self, collection: str, filter_expr: dict) -> int:
        """按条件删除，返回删除数量"""

    @abstractmethod
    def list_collections(self) -> list[str]:
        """列出所有 collection"""
```

#### 2. `core/memory_rag/vector/qdrant_adapter.py`

Filter DSL 支持：

```python
# filter_expr 示例
{
    "AND": [
        {"EQ": {"field": "scope", "value": "tenant"}},
        {"IN": {"field": "data_type", "values": ["tenant_knowledge", "tenant_business"]}},
        {"RANGE": {"field": "importance", "gte": 0.5}},
        {"TIME_RANGE": {"field": "created_at", "gte": 1711929600, "lte": 1714521600}}
    ]
}
```

翻译为 Qdrant 原生 Filter。

`ensure_collection` 实现：

```python
def ensure_collection(self, name: str, dim: int) -> None:
    if self.client.collection_exists(name):
        return
    self.client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )
```

### 验收标准

- [ ] Filter DSL 所有操作（AND/OR/EQ/IN/RANGE/TIME_RANGE）单测
- [ ] `ensure_collection` 重复调用不报错
- [ ] `search` 的 `score_threshold=0.7` 正确过滤低分结果
- [ ] `delete_by_filter` 返回正确删除数量
- [ ] 不存在的 collection 调用 `search` 抛出明确异常

---

## Task 1.5 — 写入层：IngestGateway

**优先级**: P0  
**预计工时**: 3 天  
**依赖**: 1.3, 1.4  
**被依赖**: 1.7

### 目标

构建统一的数据写入网关，支持文本分块、PDF 解析、幂等更新、scope 校验。

### 实现清单

#### 1. 目录结构

```
core/memory_rag/ingest/
├── __init__.py
├── gateway.py       # IngestGateway 主入口
├── chunker.py       # 文本分块
└── pdf_parser.py    # PDF 文本提取
```

#### 2. `core/memory_rag/ingest/chunker.py`

```python
class ChunkStrategy(StrEnum):
    SENTENCE = "sentence"
    PARAGRAPH = "paragraph"
    SLIDING_WINDOW = "sliding_window"

@dataclass
class Chunk:
    text: str
    index: int

def chunk_text(text: str, strategy: ChunkStrategy, **kwargs) -> list[Chunk]:
    """
    SENTENCE: 按句号、问号、感叹号分割
    PARAGRAPH: 按双换行分割
    SLIDING_WINDOW: 固定长度滑动窗口，kwargs 需要 window_size, overlap
    """
```

#### 3. `core/memory_rag/ingest/pdf_parser.py`

```python
"""
IngestGateway 的 PDF 解析封装
直接调用 shared.libs.pdf，处理 ingest 场景的特殊需求
"""

from shared.libs.pdf import extract_text_from_pdf as _extract_text
from shared.libs.pdf import extract_pages_from_pdf, PageText


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    提取 PDF 全文（用于 ingest）
    直接调用 shared.libs.pdf.parser
    """
    return _extract_text(pdf_bytes)


def extract_text_by_pages(pdf_bytes: bytes, max_pages: int = 100) -> list[str]:
    """
    按页提取 PDF 文本（用于分块写入）
    
    Args:
        pdf_bytes: PDF 文件字节流
        max_pages: 最大处理页数（防止超大文件）
        
    Returns:
        每页的文本列表
    """
    pages = extract_pages_from_pdf(pdf_bytes)
    return [page.text for page in pages[:max_pages]]
```

#### 4. `core/memory_rag/ingest/gateway.py`

```python
@dataclass
class IngestRequest:
    content: str | bytes
    data_type: DataType
    channel_id: str = ""
    tenant_id: str = ""
    user_id: str = ""
    source_id: str = ""
    source_name: str = ""
    language: str = "zh-CN"
    tags: list[str] = field(default_factory=list)
    expires_at: int = 0
    importance: float = 1.0
    chunk_strategy: ChunkStrategy = ChunkStrategy.PARAGRAPH

@dataclass
class IngestResult:
    source_id: str
    chunks_written: int
    chunks_skipped: int

class IngestGateway:
    async def ingest(self, req: IngestRequest) -> IngestResult:
        """
        1. 校验 scope 字段完整性（根据 data_type 判断需要哪些 scope 字段）
        2. 如果 content 是 bytes，尝试 PDF 解析
        3. 文本分块
        4. 生成 source_id（不传则用 content hash）
        5. 删除旧版本（同 source_id）
        6. 批量写入向量库
        """

    async def delete(self, data_type: DataType, source_id: str, **scope_kwargs) -> int:
        """按 source_id 删除"""
```

### 验收标准

- [ ] 三种分块策略单测
- [ ] PDF 解析单测（调用 shared.libs 占位实现）
- [ ] 同 `source_id` 二次写入，旧数据被删除
- [ ] `data_type=USER_MEMORY` 但 `user_id` 为空，抛出校验异常
- [ ] `language` 字段正确写入 metadata
- [ ] `importance` 字段正确写入
- [ ] PDF 按页分块功能测试（使用占位数据）

---

## Task 1.6 — 检索层：LayeredRetrievalGateway

**优先级**: P0  
**预计工时**: 4 天  
**依赖**: 1.2, 1.3, 1.4  
**被依赖**: 1.7, 3.3

### 目标

构建四层检索网关，支持 recall + rerank + budget 分配 + cache + query rewrite。

### 实现清单

#### 1. 目录结构

```
core/memory_rag/retrieval/
├── __init__.py
├── gateway.py       # LayeredRetrievalGateway 主入口
├── reranker.py      # RerankerGateway（批量评分）
└── rewriter.py      # QueryRewriter（走 PromptGateway）
```

#### 2. `core/memory_rag/retrieval/gateway.py`

```python
@dataclass
class ScopedRetrievalConfig:
    enabled: bool = True
    data_types: list[DataType] = field(default_factory=list)
    top_k_recall: int = 10
    top_k_rerank: int = 3
    score_threshold: float = 0.0
    rerank: bool = True
    rewrite: bool = False
    use_cache: bool = False
    cache_ttl: int = 0

@dataclass
class RetrievalPlan:
    platform: ScopedRetrievalConfig
    channel: ScopedRetrievalConfig
    tenant: ScopedRetrievalConfig
    user: ScopedRetrievalConfig
    budget_weights: dict[str, float] = field(default_factory=lambda: {
        "platform": 0.10, "channel": 0.20, "tenant": 0.35, "user": 0.25
    })
    max_total_tokens: int = 2000

@dataclass
class RetrievedChunk:
    text: str
    score: float
    scope: str
    data_type: str
    source_name: str
    tags: list[str]

@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]
    tokens_used: int

    def as_context_string(self, locale: str = "zh-CN") -> str:
        """
        按层分段，标签文案通过 i18n.t() 国际化
        【平台知识】
        ...
        【企业知识库】
        ...
        """

class LayeredRetrievalGateway:
    async def retrieve(
        self,
        query: str,
        user_id: str,
        tenant_id: str,
        channel_id: str,
        plan: RetrievalPlan,
    ) -> RetrievalResult:
        """
        1. 四层并发检索
        2. 各层内部：recall → importance 加权 → rerank
        3. budget 分配截取
        4. 组装输出
        """
```

#### 3. `core/memory_rag/retrieval/reranker.py`

```python
class RerankerGateway:
    async def rerank(
        self,
        query: str,
        docs: list[str],
        top_k: int,
    ) -> list[tuple[str, float]]:
        """批量调用 compute_score([(query, doc) for doc in docs])"""
```

#### 4. `core/memory_rag/retrieval/rewriter.py`

```python
class QueryRewriter:
    async def rewrite(self, query: str, locale: str = "zh-CN") -> str:
        """
        通过 prompt_gateway.get("query_rewriter_sys", locale=locale) 获取 prompt
        调用 LLM 改写查询
        """
```

### 验收标准

- [ ] 四层检索隔离测试（mock 向量库）
- [ ] `budget_weights` 正确分配 token 预算
- [ ] reranker 批量调用测试
- [ ] `as_context_string(locale="en-US")` 标签为英文
- [ ] cache 命中测试（platform 层开启 cache）
- [ ] query rewrite 集成测试

---

## Task 1.7 — Memory 层重写

**优先级**: P0  
**预计工时**: 4 天  
**依赖**: 1.1, 1.2, 1.4, 1.5, 1.6  
**被依赖**: 3.3

### 目标

重写 Memory 层，支持短期 Redis + 长期向量库、noise 过滤、dedup、consolidate、profile/preference 管理。

### 实现清单

#### 1. `core/memory_rag/memory/config.py`

```python
@dataclass
class MemoryConfig:
    max_turns: int = 20
    dedup_window: int = 6
    noise_texts: set[str] = field(default_factory=lambda: {
        "嗯", "哦", "好的", "收到", "了解", "谢谢", "好的谢谢", "ok", "OK", "好", "是的", "对"
    })
    long_term_enabled: bool = True
    consolidate_every: int = 20
    max_long_term_tokens: int = 800
    compression_strategy: str = "window"
```

#### 2. `core/memory_rag/memory/gateway.py`

```python
class MemoryGateway:
    async def append(
        self, *, conversation_id, tenant_id, user_id,
        role, content, config: MemoryConfig
    ) -> None:
        """
        1. noise 过滤
        2. dedup（与最近 dedup_window 条对比）
        3. 写入 Redis stm:{tenant_id}:{user_id}:{conversation_id}
        4. 检查是否触发 consolidate
        """

    async def get_short_term(
        self, *, conversation_id, tenant_id, user_id,
        config: MemoryConfig
    ) -> list[dict]:
        """读取短期记忆，最多 max_turns 条"""

    async def build_context(
        self, *, query, conversation_id, user_id,
        tenant_id, channel_id, locale,
        config: MemoryConfig, retrieval_plan: RetrievalPlan
    ) -> str:
        """
        并发执行：
        1. 短期记忆读取
        2. 长期 User 层检索（USER_MEMORY）
        输出格式：
        【相关记忆】
        ...长期检索结果...
        
        【近期对话】
        user: ...
        assistant: ...
        """

    async def update_profile(
        self, *, tenant_id, user_id, content, source_id
    ) -> None:
        """写入 USER_PROFILE 类型数据"""

    async def update_preference(
        self, *, tenant_id, user_id, content, source_id
    ) -> None:
        """写入 USER_PREFERENCE 类型数据"""

    async def _consolidate(
        self, *, conversation_id, tenant_id, user_id
    ) -> None:
        """
        1. 读取短期记忆
        2. LLM 压缩摘要
        3. 写入长期向量库（USER_MEMORY）
        4. 清理 Redis 旧数据
        """
```

### 验收标准

- [ ] noise 过滤单测（"嗯" 被过滤）
- [ ] dedup 单测（连续重复内容被跳过）
- [ ] consolidate 触发测试（第 20 条触发）
- [ ] `build_context` 并发执行测试
- [ ] `locale="en-US"` 时标签为英文
- [ ] profile/preference 写入测试

---

## 架构防腐门禁

每个 Task 完成时检查：

- [ ] `core/` 和 `shared/` 不反向依赖 `domain_agents/`
- [ ] `shared/` 不依赖 `core/`
- [ ] 向量库具体实现只在 `vector/qdrant_adapter.py`
- [ ] 不在上层 import `qdrant_client`

---

## Batch 1 完成标志

- [ ] 所有 Task 验收标准通过
- [ ] 集成测试：完整流程（写入 → 检索 → Memory 构建）
- [ ] 性能测试：四层检索 P95 < 500ms
- [ ] 文档：API 文档和使用示例
