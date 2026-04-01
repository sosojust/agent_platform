"""
Locale 解析、标准化、fallback 链
"""

SUPPORTED_LOCALES = {"zh-CN", "en-US", "ja-JP"}
DEFAULT_LOCALE = "zh-CN"

FALLBACK_CHAIN: dict[str, list[str]] = {
    "zh-TW": ["zh-CN", "en-US"],
    "zh-HK": ["zh-CN", "en-US"],
    "en-GB": ["en-US"],
}

LOCALE_LANGUAGE_NAME = {
    "zh-CN": "中文",
    "en-US": "English",
    "ja-JP": "日本語",
}


def normalize_locale(raw: str) -> str:
    """
    标准化 locale
    
    Examples:
        normalize_locale("zh") -> "zh-CN"
        normalize_locale("en") -> "en-US"
        normalize_locale("unknown") -> "zh-CN"
        normalize_locale("zh-CN") -> "zh-CN"
    """
    if not raw:
        return DEFAULT_LOCALE
    
    raw = raw.strip()
    
    # 已经是标准格式
    if raw in SUPPORTED_LOCALES:
        return raw
    
    # 简写映射
    simple_mapping = {
        "zh": "zh-CN",
        "en": "en-US",
        "ja": "ja-JP",
    }
    
    if raw in simple_mapping:
        return simple_mapping[raw]
    
    # 尝试从 fallback 链中查找
    if raw in FALLBACK_CHAIN:
        return FALLBACK_CHAIN[raw][0]
    
    # 不识别的返回默认值
    return DEFAULT_LOCALE


def get_fallback_chain(locale: str) -> list[str]:
    """
    返回包含自身的完整 fallback 列表
    
    Examples:
        get_fallback_chain("zh-TW") -> ["zh-TW", "zh-CN", "en-US"]
        get_fallback_chain("zh-CN") -> ["zh-CN"]
        get_fallback_chain("ja-JP") -> ["ja-JP", "zh-CN", "en-US"]
    """
    # 不标准化，保留原始 locale
    if not locale:
        locale = DEFAULT_LOCALE
    
    # 优先检查 fallback 链（即使是标准 locale 也可能有 fallback）
    if locale in FALLBACK_CHAIN:
        return [locale] + FALLBACK_CHAIN[locale]
    
    # 如果是标准 locale 但不在 fallback 链中，只返回自身
    if locale in SUPPORTED_LOCALES:
        return [locale]
    
    # 其他情况，尝试标准化后返回
    normalized = normalize_locale(locale)
    return [normalized]
