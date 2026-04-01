"""
时区转换工具
"""
from datetime import datetime, timezone
import zoneinfo


def to_user_timezone(utc_ts: int, user_timezone: str) -> str:
    """
    UTC timestamp → 用户时区可读时间
    
    Args:
        utc_ts: UTC timestamp (秒)
        user_timezone: 用户时区，如 "Asia/Shanghai", "America/New_York"
    
    Returns:
        用户时区的可读时间字符串，如 "2024-01-01 12:00:00"
    
    Examples:
        to_user_timezone(1704067200, "Asia/Shanghai")
        -> "2024-01-01 08:00:00"
    """
    try:
        # 创建 UTC datetime
        utc_dt = datetime.fromtimestamp(utc_ts, tz=timezone.utc)
        
        # 转换到用户时区
        user_tz = zoneinfo.ZoneInfo(user_timezone)
        user_dt = utc_dt.astimezone(user_tz)
        
        # 格式化输出
        return user_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        # 时区无效或其他错误，返回 UTC 时间
        utc_dt = datetime.fromtimestamp(utc_ts, tz=timezone.utc)
        return utc_dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def parse_user_time(time_str: str, user_timezone: str) -> int:
    """
    用户本地时间字符串 → UTC timestamp
    
    Args:
        time_str: 用户本地时间字符串，如 "2024-01-01 12:00:00"
        user_timezone: 用户时区，如 "Asia/Shanghai"
    
    Returns:
        UTC timestamp (秒)
    
    Examples:
        parse_user_time("2024-01-01 12:00:00", "Asia/Shanghai")
        -> 1704081600
    """
    try:
        # 解析时间字符串
        user_dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        
        # 设置时区
        user_tz = zoneinfo.ZoneInfo(user_timezone)
        user_dt = user_dt.replace(tzinfo=user_tz)
        
        # 转换为 UTC timestamp
        return int(user_dt.timestamp())
    except Exception:
        # 解析失败，返回当前时间
        return int(datetime.now(tz=timezone.utc).timestamp())
