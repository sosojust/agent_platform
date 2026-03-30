from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.tool_service.registry import tool_gateway
from shared.config.settings import settings

router = APIRouter(tags=["tools"])


def _require_app_auth(headers: dict[str, str]) -> str:
    app_id = headers.get("X-App-Id", "")
    app_token = headers.get("X-App-Token", "")
    if not app_id or not app_token:
        raise HTTPException(status_code=401, detail="missing app auth headers")
    expected = settings.tool_auth_map.get(app_id)
    if not expected or expected != app_token:
        raise HTTPException(status_code=401, detail="invalid app auth")
    return app_id


class ToolInvokeRequest(BaseModel):
    tool: str = Field(...)
    arguments: dict[str, Any] = Field(default_factory=dict)


@router.get("/tools", summary="列出可用工具")
async def list_tools(request: Request) -> list[dict]:
    _require_app_auth(dict(request.headers))
    return tool_gateway.list_tools()


@router.post("/tools/invoke", summary="调用工具")
async def invoke_tool(req: ToolInvokeRequest, request: Request) -> dict:
    _require_app_auth(dict(request.headers))
    try:
        result = await tool_gateway.invoke(req.tool, req.arguments)
        if isinstance(result, dict):
            return result
        return {"result": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
