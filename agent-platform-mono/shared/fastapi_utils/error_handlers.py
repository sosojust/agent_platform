"""统一异常处理，所有错误返回统一格式。"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from shared.logging.logger import get_logger

logger = get_logger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exc(request: Request, exc: HTTPException):
        logger.warning("http_exception", path=request.url.path,
                       status=exc.status_code, detail=exc.detail)
        return JSONResponse(status_code=exc.status_code, content={
            "code": _code(exc.status_code),
            "message": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
            "detail": exc.detail if not isinstance(exc.detail, str) else None,
        })

    @app.exception_handler(RequestValidationError)
    async def validation_exc(request: Request, exc: RequestValidationError):
        logger.warning("validation_error", path=request.url.path, errors=exc.errors())
        return JSONResponse(status_code=422, content={
            "code": "VALIDATION_ERROR",
            "message": "请求参数校验失败",
            "detail": exc.errors(),
        })

    @app.exception_handler(Exception)
    async def generic_exc(request: Request, exc: Exception):
        logger.error("unhandled_exception", path=request.url.path,
                     error=str(exc), exc_info=True)
        return JSONResponse(status_code=500, content={
            "code": "INTERNAL_ERROR",
            "message": "服务内部错误，请稍后重试",
            "detail": None,
        })


def _code(status: int) -> str:
    return {400: "BAD_REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN",
            404: "NOT_FOUND", 422: "VALIDATION_ERROR", 429: "RATE_LIMITED",
            500: "INTERNAL_ERROR", 503: "SERVICE_UNAVAILABLE"}.get(status, "UNKNOWN_ERROR")
