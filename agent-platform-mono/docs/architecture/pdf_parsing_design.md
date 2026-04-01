# PDF 解析架构设计

## 概述

PDF 解析能力在 Agent Platform 中有两种使用场景，本文档说明架构设计和实现方式。

---

## 两种使用场景

### 场景 A：IngestGateway 写入时的 PDF 解析

**调用方**: `core/memory_rag/ingest/gateway.py`  
**目的**: 把 PDF 内容切块后向量化存储  
**特点**:

- 纯数据处理管道
- 无网络调用
- 无鉴权需求
- 无租户上下文
- 确定性的文本转换操作

**调用路径**:

```
IngestGateway
  ↓
core/memory_rag/ingest/pdf_parser.py
  ↓
shared/libs/pdf/parser.py (直接调用)
```

---

### 场景 B：doc_agent 处理 PDF 时的解析

**调用方**: 业务 Agent（如 doc_agent）  
**目的**: 提取摘要、回答问题、结构化抽取等  
**特点**:

- Agent 工具链的一个环节
- 需要租户隔离
- 需要鉴权
- 需要可观测性（Tracing）
- 代表用户执行的动作

**调用路径**:

```
doc_agent
  ↓
tool_gateway.invoke("skill:parse_pdf")
  ↓
domain_agents/doc/tools/doc_tools.py (@skill 装饰器)
  ↓
shared/libs/pdf/parser.py (内部调用)
```

---

## 核心判断

**场景 A 是基础设施调用**：

- 和调用 `hashlib.md5()` 没有本质区别
- 是内部实现细节
- 不需要鉴权、不需要可观测性、不需要租户隔离
- 调用者是平台自身

**场景 B 是业务工具调用**：

- 是 Agent 代表用户执行的动作
- 需要鉴权、需要记录谁在什么时间解析了什么文件
- 需要租户隔离

**两个场景共享的是解析能力本身（算法），但不共享调用方式。**

---

## 架构设计

### 目录结构

```
shared/libs/pdf/
├── __init__.py
└── parser.py          # 纯粹的 PDF 解析能力
                       # 输入：bytes，输出：str 或 list[PageText]
                       # 依赖：pymupdf / pdfplumber 等解析库
                       # 不依赖：tool_service / memory_rag / 任何业务层

core/memory_rag/ingest/
└── pdf_parser.py      # 直接 import shared/libs/pdf/parser.py
                       # 薄封装，处理 ingest 场景的特殊需求（如按页分块）

domain_agents/doc/tools/
└── doc_tools.py       # @skill 注册 parse_pdf 工具
                       # 内部调用 shared/libs/pdf/parser.py
                       # 通过 tool_gateway 对外暴露
                       # 有租户上下文、有可观测性
```

---

## 实现说明

### shared/libs/pdf/parser.py（核心能力）

```python
"""
PDF 解析基础能力
纯工具函数库，无任何框架依赖
"""

from dataclasses import dataclass


@dataclass
class PageText:
    """单页文本"""
    page_num: int
    text: str
    metadata: dict


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    提取 PDF 全文
    
    注意：当前为占位实现，实际项目中应使用：
    - pymupdf (fitz)
    - pdfplumber
    - pypdf2
    等库实现真实解析
    """
    return "[PDF_CONTENT_PLACEHOLDER] PDF parsing not implemented yet"


def extract_pages_from_pdf(pdf_bytes: bytes) -> list[PageText]:
    """
    按页提取 PDF 文本
    
    注意：当前为占位实现
    """
    return [
        PageText(
            page_num=1,
            text="[PDF_PAGE_PLACEHOLDER] PDF parsing not implemented yet",
            metadata={"total_pages": 1}
        )
    ]
```

---

### core/memory_rag/ingest/pdf_parser.py（场景 A 封装）

```python
"""
IngestGateway 的 PDF 解析封装
直接调用 shared.libs.pdf，处理 ingest 场景的特殊需求
"""

from shared.libs.pdf import extract_text_from_pdf as _extract_text
from shared.libs.pdf import extract_pages_from_pdf


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """提取 PDF 全文（用于 ingest）"""
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

---

### domain_agents/doc/tools/doc_tools.py（场景 B 封装）

```python
"""
doc_agent 的 PDF 解析工具
通过 @skill 注册到 tool_service，有鉴权和可观测性
"""

from core.tool_service.skills.base import skill
from shared.libs.pdf import extract_text_from_pdf
import base64


@skill(
    name="parse_pdf",
    description="解析 PDF 文件，提取文本内容",
    keywords=["PDF", "解析", "文档", "提取"],
    input_schema={
        "type": "object",
        "properties": {
            "pdf_bytes": {
                "type": "string",
                "description": "PDF 文件的 base64 编码"
            }
        },
        "required": ["pdf_bytes"]
    },
)
async def parse_pdf(args: dict) -> dict:
    """
    解析 PDF 工具
    
    场景：doc_agent 需要解析用户上传的 PDF
    实现：内部调用 shared.libs.pdf，外部通过 tool_service 暴露
    特点：有租户隔离、有鉴权、有可观测性
    """
    pdf_bytes = base64.b64decode(args["pdf_bytes"])
    
    # 直接调用 shared.libs 的解析能力
    text = extract_text_from_pdf(pdf_bytes)
    
    return {
        "text": text,
        "status": "success",
        "length": len(text),
    }
```

---

## 设计原则

### 1. 能力下沉，调用分层

- **核心能力**放在 `shared/libs/`，无框架依赖
- **场景封装**在各自的调用层（ingest / domain_agents）
- **不走 tool_service** 的场景直接 import
- **走 tool_service** 的场景通过 `@skill` 注册

### 2. 避免过度设计

- IngestGateway 作为平台内部组件，直接调用解析库
- 不走 tool_service，避免平台自己调用自己的 HTTP 接口
- 减少网络开销和鉴权开销

### 3. 共享复用

- 两个场景共享同一份解析实现
- 避免代码重复
- 便于后续升级解析库

### 4. 依赖隔离

- `shared/libs/` 不依赖任何业务层
- `shared/libs/` 不依赖任何框架（FastAPI / LangGraph / tool_service）
- 纯函数式，输入 → 输出，无副作用

---

## 后续扩展

### 其他文档解析能力

按照相同的模式扩展：

```
shared/libs/
├── pdf/          # PDF 解析
├── excel/        # Excel 解析
├── word/         # Word 解析
├── ocr/          # OCR 识别
└── image/        # 图片处理
```

### 真实实现替换

当前为占位实现，后续可选择以下库实现真实解析：

**PDF 解析**:
- pymupdf (fitz) - 推荐，速度快
- pdfplumber - 表格提取好
- pypdf2 - 轻量级

**Excel 解析**:
- openpyxl - xlsx 格式
- xlrd - xls 格式

**OCR 识别**:
- pytesseract - 基于 Tesseract
- paddleocr - 中文识别好

---

## 与 tool_service 的关系

| 维度 | shared/libs | tool_service |
| --- | --- | --- |
| 定位 | 纯工具能力 | 业务工具层 |
| 鉴权 | 无 | 有 |
| 租户隔离 | 无 | 有 |
| 可观测性 | 无 | 有（Tracing） |
| 调用方式 | 直接 import | tool_gateway.invoke() |
| 使用场景 | 平台内部调用 | Agent 代表用户调用 |

---

## 总结

- **PDF 解析核心能力**放在 `shared/libs/pdf/`
- **IngestGateway** 直接调用（内部调用，无需鉴权）
- **doc_agent** 通过 `@skill` 包装后调用（业务工具，需要鉴权）
- **两者共享**同一份解析实现，但调用路径不同
- **当前阶段**仅提供接口定义和占位实现，不做真实解析
- **后续扩展**可按相同模式添加 Excel / Word / OCR 等能力
