"""
系统固定文案翻译
"""
import json
from pathlib import Path
from typing import Any
from shared.middleware.tenant import get_current_locale
from .locale import get_fallback_chain

# 缓存加载的翻译文件
_translations_cache: dict[str, dict[str, str]] = {}


def _load_translations(locale: str) -> dict[str, str]:
    """加载指定 locale 的翻译文件"""
    if locale in _translations_cache:
        return _translations_cache[locale]
    
    locale_file = Path(__file__).parent / "locales" / f"{locale}.json"
    if not locale_file.exists():
        return {}
    
    with open(locale_file, "r", encoding="utf-8") as f:
        translations = json.load(f)
    
    _translations_cache[locale] = translations
    return translations


def t(key: str, locale: str | None = None, **kwargs: Any) -> str:
    """
    翻译系统固定文案
    
    Args:
        key: 翻译 key，如 "error.not_found"
        locale: 语言区域，不传则从 current_locale() 读取
        **kwargs: 变量插值参数
    
    Returns:
        翻译后的文本，如果 key 不存在则返回 key 本身
    
    Examples:
        t("error.tool_not_found", name="保单查询")
        -> "工具 保单查询 不存在"
        
        t("error.tool_not_found", locale="en-US", name="policy_query")
        -> "Tool policy_query not found"
    """
    # 获取 locale
    if locale is None:
        locale = get_current_locale()
    
    # 获取 fallback 链
    fallback_chain = get_fallback_chain(locale)
    
    # 按 fallback 链查找翻译
    for loc in fallback_chain:
        translations = _load_translations(loc)
        if key in translations:
            text = translations[key]
            # 变量插值
            if kwargs:
                try:
                    text = text.format(**kwargs)
                except (KeyError, ValueError):
                    pass  # 插值失败，返回原文本
            return text
    
    # 所有 fallback 都找不到，返回 key 本身
    return key
