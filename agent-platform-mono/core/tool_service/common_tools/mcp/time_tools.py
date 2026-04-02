"""公共时间处理 MCP 工具"""
from typing import Any
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from mcp.server.fastmcp import FastMCP
from shared.logging.logger import get_logger

logger = get_logger(__name__)
mcp = FastMCP("common-time")


@mcp.tool()
async def get_current_time(timezone: str = "Asia/Shanghai") -> dict[str, Any]:
    """
    获取指定时区的当前时间。
    
    Args:
        timezone: 时区名称，如 "Asia/Shanghai", "UTC", "America/New_York"
    
    Returns:
        {
            "time": "2024-01-01 12:00:00",
            "timezone": "Asia/Shanghai",
            "timestamp": 1704096000
        }
    """
    try:
        tz = ZoneInfo(timezone)
        now = datetime.now(tz)
        
        return {
            "time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "timezone": timezone,
            "timestamp": int(now.timestamp()),
            "iso": now.isoformat(),
        }
    except Exception as e:
        logger.error("get_current_time_failed", timezone=timezone, error=str(e))
        return {"error": f"获取时间失败: {str(e)}"}


@mcp.tool()
async def calculate_date_diff(start_date: str, end_date: str) -> dict[str, Any]:
    """
    计算两个日期之间的差值。
    
    Args:
        start_date: 开始日期，格式 "YYYY-MM-DD"
        end_date: 结束日期，格式 "YYYY-MM-DD"
    
    Returns:
        {
            "days": 10,
            "weeks": 1,
            "months": 0,
            "start": "2024-01-01",
            "end": "2024-01-11"
        }
    """
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        
        diff = end - start
        days = diff.days
        weeks = days // 7
        months = days // 30  # 近似值
        
        return {
            "days": days,
            "weeks": weeks,
            "months": months,
            "start": start_date,
            "end": end_date,
        }
    except Exception as e:
        logger.error("calculate_date_diff_failed", error=str(e))
        return {"error": f"日期计算失败: {str(e)}"}


@mcp.tool()
async def add_days_to_date(date: str, days: int) -> dict[str, Any]:
    """
    在指定日期上增加或减少天数。
    
    Args:
        date: 基准日期，格式 "YYYY-MM-DD"
        days: 要增加的天数（负数表示减少）
    
    Returns:
        {
            "original": "2024-01-01",
            "result": "2024-01-11",
            "days_added": 10
        }
    """
    try:
        base_date = datetime.strptime(date, "%Y-%m-%d")
        result_date = base_date + timedelta(days=days)
        
        return {
            "original": date,
            "result": result_date.strftime("%Y-%m-%d"),
            "days_added": days,
        }
    except Exception as e:
        logger.error("add_days_to_date_failed", error=str(e))
        return {"error": f"日期计算失败: {str(e)}"}


@mcp.tool()
async def is_business_day(date: str, country: str = "CN") -> dict[str, Any]:
    """
    判断指定日期是否为工作日。
    
    注意：此实现仅判断周末，不包含法定节假日。
    
    Args:
        date: 日期，格式 "YYYY-MM-DD"
        country: 国家代码，如 "CN", "US"
    
    Returns:
        {
            "date": "2024-01-01",
            "is_business_day": false,
            "weekday": "Monday",
            "note": "不包含法定节假日判断"
        }
    """
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        weekday = dt.weekday()  # 0=Monday, 6=Sunday
        
        # 简单判断：周一到周五为工作日
        is_business = weekday < 5
        
        weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        
        return {
            "date": date,
            "is_business_day": is_business,
            "weekday": weekday_names[weekday],
            "note": "不包含法定节假日判断",
        }
    except Exception as e:
        logger.error("is_business_day_failed", error=str(e))
        return {"error": f"判断失败: {str(e)}"}
