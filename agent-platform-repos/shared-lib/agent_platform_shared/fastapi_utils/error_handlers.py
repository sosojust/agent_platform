"""
统一异常处理。
所有服务注册同一套 handler，错误响应格式一致，方便调用方解析。

标准错误响应格式：
  {
    "code": "INTERNAL_ERROR",
    "message": "具体描述",
    "detail": null  # 可选的额外信息
  }
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from agent_platform_shared.logging.logger import get_logger

logger = get_logger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    """注册所有统一异常处理器，在 create_app() 中调用。"""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        logger.warning(
            "http_exception",
            path=request.url.path,
            status_code=exc.status_code,
            detail=exc.detail,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": _status_to_code(exc.status_code),
                "message": str(exc.detail) if isinstance(exc.detail, str)
                           else exc.detail.get("message", str(exc.detail))
                           if isinstance(exc.detail, dict) else str(exc.detail),
                "detail": exc.detail if not isinstance(exc.detail, str) else None,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        logger.warning(
            "validation_error",
            path=request.url.path,
            errors=exc.errors(),
        )
        return JSONResponse(
            status_code=422,
            content={
                "code": "VALIDATION_ERROR",
                "message": "请求参数校验失败",
                "detail": exc.errors(),
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            error=str(exc),
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={
                "code": "INTERNAL_ERROR",
                "message": "服务内部错误，请稍后重试",
                "detail": None,
            },
        )


def _status_to_code(status_code: int) -> str:
    return {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        408: "TIMEOUT",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMITED",
        500: "INTERNAL_ERROR",
        502: "BAD_GATEWAY",
        503: "SERVICE_UNAVAILABLE",
    }.get(status_code, "UNKNOWN_ERROR")
