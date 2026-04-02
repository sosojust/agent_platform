"""公共格式化 Skills"""
from typing import Any
from core.tool_service.skills.base import skill
import re


@skill(name="format_phone_number")
async def format_phone_number(args: dict[str, Any]) -> dict[str, Any]:
    """
    格式化电话号码为标准格式。
    
    支持中国大陆手机号和固话。
    
    Args:
        args: {"phone": "13812345678"}
    
    Returns:
        {"formatted": "138-1234-5678", "valid": true}
    """
    phone = str(args.get("phone", "")).strip()
    # 移除所有非数字字符
    digits = re.sub(r'\D', '', phone)
    
    # 手机号格式化
    if len(digits) == 11 and digits.startswith(('13', '14', '15', '16', '17', '18', '19')):
        formatted = f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
        return {"formatted": formatted, "valid": True, "type": "mobile"}
    
    # 固话格式化（带区号）
    if len(digits) >= 10:
        if len(digits) == 10:  # 3位区号 + 7位号码
            formatted = f"{digits[:3]}-{digits[3:]}"
        else:  # 4位区号 + 7/8位号码
            formatted = f"{digits[:4]}-{digits[4:]}"
        return {"formatted": formatted, "valid": True, "type": "landline"}
    
    return {"formatted": phone, "valid": False, "error": "无效的电话号码"}


@skill(name="format_currency")
async def format_currency(args: dict[str, Any]) -> dict[str, Any]:
    """
    格式化货币金额。
    
    Args:
        args: {"amount": 1234.56, "currency": "CNY"}
    
    Returns:
        {"formatted": "¥1,234.56", "amount": 1234.56}
    """
    amount = float(args.get("amount", 0))
    currency = str(args.get("currency", "CNY")).upper()
    
    # 货币符号映射
    symbols = {
        "CNY": "¥",
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "JPY": "¥",
    }
    
    symbol = symbols.get(currency, currency)
    
    # 格式化金额（千分位）
    formatted_amount = f"{amount:,.2f}"
    
    return {
        "formatted": f"{symbol}{formatted_amount}",
        "amount": amount,
        "currency": currency
    }


@skill(name="format_id_card")
async def format_id_card(args: dict[str, Any]) -> dict[str, Any]:
    """
    格式化身份证号（脱敏）。
    
    Args:
        args: {"id_card": "110101199001011234"}
    
    Returns:
        {"formatted": "110101********1234", "valid": true}
    """
    id_card = str(args.get("id_card", "")).strip()
    
    # 验证长度
    if len(id_card) not in (15, 18):
        return {"formatted": id_card, "valid": False, "error": "身份证号长度不正确"}
    
    # 脱敏：保留前6位和后4位
    if len(id_card) == 18:
        formatted = f"{id_card[:6]}********{id_card[-4:]}"
    else:
        formatted = f"{id_card[:6]}*****{id_card[-4:]}"
    
    return {"formatted": formatted, "valid": True}
