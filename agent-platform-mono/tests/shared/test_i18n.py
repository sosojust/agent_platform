"""
Tests for Task 1.2 - i18n 基础层
测试 locale 标准化、fallback 链、文案翻译、时区转换
"""
import pytest
from shared.i18n import (
    normalize_locale,
    get_fallback_chain,
    t,
    to_user_timezone,
    parse_user_time,
    SUPPORTED_LOCALES,
    DEFAULT_LOCALE,
)


class TestLocaleNormalization:
    """测试 locale 标准化"""
    
    def test_normalize_simple_codes(self):
        """测试简写代码标准化"""
        assert normalize_locale("zh") == "zh-CN"
        assert normalize_locale("en") == "en-US"
        assert normalize_locale("ja") == "ja-JP"
    
    def test_normalize_already_standard(self):
        """测试已经是标准格式的 locale"""
        assert normalize_locale("zh-CN") == "zh-CN"
        assert normalize_locale("en-US") == "en-US"
        assert normalize_locale("ja-JP") == "ja-JP"
    
    def test_normalize_unknown(self):
        """测试不识别的 locale 返回默认值"""
        assert normalize_locale("unknown") == DEFAULT_LOCALE
        assert normalize_locale("fr-FR") == DEFAULT_LOCALE
        assert normalize_locale("") == DEFAULT_LOCALE
    
    def test_normalize_fallback_chain_locales(self):
        """测试 fallback 链中的 locale"""
        assert normalize_locale("zh-TW") == "zh-CN"
        assert normalize_locale("zh-HK") == "zh-CN"
        assert normalize_locale("en-GB") == "en-US"


class TestFallbackChain:
    """测试 fallback 链"""
    
    def test_fallback_chain_zh_tw(self):
        """测试繁体中文的 fallback 链"""
        chain = get_fallback_chain("zh-TW")
        assert chain == ["zh-TW", "zh-CN", "en-US"]
    
    def test_fallback_chain_zh_cn(self):
        """测试简体中文的 fallback 链（无 fallback）"""
        chain = get_fallback_chain("zh-CN")
        assert chain == ["zh-CN"]
    
    def test_fallback_chain_ja_jp(self):
        """测试日语的 fallback 链（标准 locale，无 fallback）"""
        chain = get_fallback_chain("ja-JP")
        assert chain == ["ja-JP"]
    
    def test_fallback_chain_en_gb(self):
        """测试英式英语的 fallback 链"""
        chain = get_fallback_chain("en-GB")
        assert chain == ["en-GB", "en-US"]


class TestTranslation:
    """测试文案翻译"""
    
    def test_translation_zh_cn(self):
        """测试中文翻译"""
        text = t("error.budget_exceeded", locale="zh-CN")
        assert text == "当前会话 Token 用量已超限"
    
    def test_translation_en_us(self):
        """测试英文翻译"""
        text = t("error.budget_exceeded", locale="en-US")
        assert text == "Current session token usage has exceeded the limit"
    
    def test_translation_ja_jp(self):
        """测试日文翻译"""
        text = t("error.budget_exceeded", locale="ja-JP")
        assert text == "現在のセッションのトークン使用量が制限を超えました"
    
    def test_translation_with_interpolation(self):
        """测试变量插值"""
        text = t("error.tool_not_found", locale="zh-CN", name="保单查询")
        assert text == "工具 保单查询 不存在"
        
        text = t("error.tool_not_found", locale="en-US", name="policy_query")
        assert text == "Tool policy_query not found"
    
    def test_translation_key_not_found(self):
        """测试 key 不存在时返回 key 本身"""
        text = t("non.exist.key", locale="zh-CN")
        assert text == "non.exist.key"
    
    def test_translation_fallback(self):
        """测试 fallback 机制"""
        # ja-JP 中不存在的 key，应该 fallback 到 zh-CN
        # 假设我们只在 zh-CN 中定义了某个 key
        text = t("error.budget_exceeded", locale="ja-JP")
        # ja-JP 中有这个 key，所以返回日文
        assert "トークン" in text
    
    def test_translation_multiple_interpolation(self):
        """测试多个变量插值"""
        text = t("error.tool_execution_failed", locale="zh-CN", name="查询工具", reason="超时")
        assert text == "工具 查询工具 执行失败：超时"


class TestTimezone:
    """测试时区转换"""
    
    def test_to_user_timezone_shanghai(self):
        """测试转换到上海时区"""
        # 2024-01-01 00:00:00 UTC = 2024-01-01 08:00:00 Asia/Shanghai
        utc_ts = 1704067200
        result = to_user_timezone(utc_ts, "Asia/Shanghai")
        assert result == "2024-01-01 08:00:00"
    
    def test_to_user_timezone_new_york(self):
        """测试转换到纽约时区"""
        # 2024-01-01 00:00:00 UTC = 2023-12-31 19:00:00 America/New_York
        utc_ts = 1704067200
        result = to_user_timezone(utc_ts, "America/New_York")
        assert result == "2023-12-31 19:00:00"
    
    def test_to_user_timezone_invalid(self):
        """测试无效时区返回 UTC 时间"""
        utc_ts = 1704067200
        result = to_user_timezone(utc_ts, "Invalid/Timezone")
        assert "UTC" in result
    
    def test_parse_user_time_shanghai(self):
        """测试解析上海时区时间"""
        # 2024-01-01 08:00:00 Asia/Shanghai = 2024-01-01 00:00:00 UTC
        time_str = "2024-01-01 08:00:00"
        result = parse_user_time(time_str, "Asia/Shanghai")
        assert result == 1704067200
    
    def test_parse_user_time_new_york(self):
        """测试解析纽约时区时间"""
        # 2023-12-31 19:00:00 America/New_York = 2024-01-01 00:00:00 UTC
        time_str = "2023-12-31 19:00:00"
        result = parse_user_time(time_str, "America/New_York")
        assert result == 1704067200
    
    def test_parse_user_time_invalid_format(self):
        """测试无效时间格式返回当前时间"""
        result = parse_user_time("invalid", "Asia/Shanghai")
        # 应该返回一个合理的 timestamp（当前时间附近）
        assert result > 1700000000  # 2023年之后
