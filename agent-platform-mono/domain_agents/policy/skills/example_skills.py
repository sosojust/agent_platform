"""保单域 Skill 示例"""
from typing import Any
from core.tool_service.skills.base import skill


@skill(name="format_policy_id")
async def format_policy_id(args: dict[str, Any]) -> dict[str, Any]:
    """
    格式化保单号：去除空格、转大写。
    
    Args:
        args: {"policy_id": "p2024001"}
    
    Returns:
        {"normalized": "P2024001"}
    """
    pid = str(args.get("policy_id", "")).strip().upper()
    return {"normalized": pid}


@skill(name="validate_policy_status")
async def validate_policy_status(args: dict[str, Any]) -> dict[str, Any]:
    """
    验证保单状态是否有效。
    
    Args:
        args: {"status": "ACTIVE"}
    
    Returns:
        {"valid": true, "status": "ACTIVE"}
    """
    status = str(args.get("status", "")).upper()
    valid_statuses = {"ACTIVE", "EXPIRED", "CANCELLED", "PENDING"}
    
    return {
        "valid": status in valid_statuses,
        "status": status,
        "valid_statuses": list(valid_statuses)
    }
