from __future__ import annotations
from typing import Any, List, Dict, Tuple
import json
import math
import re

from core.memory_rag.embedding.service import embedding_service
from core.ai_core.llm.client import llm_client


class ToolCandidate:
    def __init__(self, name: str, description: str, keywords: List[str], tool: Any):
        self.name = name
        self.description = description
        self.keywords = keywords or []
        self.tool = tool


def _tokenize(text: str) -> List[str]:
    s = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fa5]+", " ", str(text)).lower()
    return [t for t in s.split() if t]


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _keyword_scores(input_text: str, candidates: List[ToolCandidate]) -> Dict[str, float]:
    toks = set(_tokenize(input_text))
    scores: Dict[str, float] = {}
    for c in candidates:
        ks = set(_tokenize(" ".join(c.keywords)))
        inter = len(toks & ks)
        scores[c.name] = float(inter)
    return scores


def _vector_scores(input_text: str, candidates: List[ToolCandidate]) -> Dict[str, float]:
    texts = [input_text] + [c.description or c.name for c in candidates]
    vecs = embedding_service.embed(texts)
    q = vecs[0]
    scores: Dict[str, float] = {}
    for i, c in enumerate(candidates, start=1):
        scores[c.name] = _cosine(q, vecs[i])
    return scores


async def _llm_select(input_text: str, candidates: List[ToolCandidate], top_k: int) -> List[str]:
    items = [{"name": c.name, "desc": c.description, "keywords": c.keywords} for c in candidates]
    sys = "你是工具选择器。根据输入选择最相关的工具名称列表，返回严格的 JSON 数组，例如：[\"tool_a\",\"tool_b\"]。最多选择 {} 个。".format(top_k)
    content = "输入: {}\n候选工具: {}\n请只返回 JSON 数组。".format(input_text, json.dumps(items, ensure_ascii=False))
    llm = llm_client.get_chat([], task_type="complex")
    messages = [{"role": "system", "content": sys}, {"role": "user", "content": content}]
    resp = await llm.ainvoke(messages)
    try:
        data = json.loads(str(resp.content))
        if isinstance(data, list):
            names = [str(x) for x in data][:top_k]
            return names
    except Exception:
        pass
    return []


def _take_top(scores: Dict[str, float], top_k: int) -> List[str]:
    return [n for n, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]]


async def select_tools(input_text: str, tenant_id: str, candidates: List[ToolCandidate], strategy: str = "hybrid", top_k: int = 3) -> List[Any]:
    strategy = str(strategy or "hybrid").lower()
    if strategy == "keyword":
        ks = _keyword_scores(input_text, candidates)
        names = _take_top(ks, top_k)
        return [c.tool for c in candidates if c.name in names]
    if strategy == "vector":
        vs = _vector_scores(input_text, candidates)
        names = _take_top(vs, top_k)
        return [c.tool for c in candidates if c.name in names]
    if strategy == "llm":
        names = await _llm_select(input_text, candidates, top_k)
        allow = {c.name for c in candidates}
        names = [n for n in names if n in allow]
        return [c.tool for c in candidates if c.name in names]
    ks = _keyword_scores(input_text, candidates)
    vs = _vector_scores(input_text, candidates)
    all_names = set(_take_top(ks, top_k * 2) + _take_top(vs, top_k * 2))
    prelim = [c for c in candidates if c.name in all_names]
    if prelim:
        names = await _llm_select(input_text, prelim, top_k)
        allow = {c.name for c in prelim}
        names = [n for n in names if n in allow]
        if names:
            return [c.tool for c in prelim if c.name in names]
    scores = {n: 0.5 * ks.get(n, 0.0) + 0.5 * vs.get(n, 0.0) for n in {**ks, **vs}}
    names = _take_top(scores, top_k)
    return [c.tool for c in candidates if c.name in names]
