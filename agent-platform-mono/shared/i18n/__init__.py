"""
shared/i18n - 国际化基础层

存放与国际化相关的核心能力：
- locale 解析、标准化、fallback 链
- 系统固定文案翻译
- 时区转换工具
"""

from .locale import (
    SUPPORTED_LOCALES,
    DEFAULT_LOCALE,
    FALLBACK_CHAIN,
    LOCALE_LANGUAGE_NAME,
    normalize_locale,
    get_fallback_chain,
)
from .translator import t
from .timezone import to_user_timezone, parse_user_time

__all__ = [
    "SUPPORTED_LOCALES",
    "DEFAULT_LOCALE",
    "FALLBACK_CHAIN",
    "LOCALE_LANGUAGE_NAME",
    "normalize_locale",
    "get_fallback_chain",
    "t",
    "to_user_timezone",
    "parse_user_time",
]
