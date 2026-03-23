"""
健康检查模块（单体版）。

liveness  GET /health  进程存活即 200
readiness GET /ready   所有模块就绪才 200

单体特点：一个进程包含所有模块，readiness 需要汇总：
  - 模型加载（bge-m3 + bge-reranker，需要 30~60s）
  - 基础设施连通（Redis + Milvus + Qdrant）
  - 外部依赖可达（LLM API + 内网 Gateway，可选）
  - 域注册完成（所有 Agent 已注册）
"""
from typing import Callable, Awaitable
from fastapi import APIRouter, HTTPException
from shared.logging.logger import get_logger

logger = get_logger(__name__)
CheckFn = Callable[[], Awaitable[bool]]


class ReadinessRegistry:
    def __init__(self) -> None:
        self._flags: dict[str, bool] = {}
        self._checks: dict[str, CheckFn] = {}

    def mark_ready(self, name: str) -> None:
        """一次性标记某项已就绪（适合：模型加载、域注册完成等）。"""
        self._flags[name] = True
        logger.info("ready_flag_set", name=name)

    def mark_not_ready(self, name: str) -> None:
        self._flags[name] = False
        logger.warning("ready_flag_cleared", name=name)

    def register_check(self, name: str, fn: CheckFn) -> None:
        """注册动态检查函数（适合：Redis ping、Milvus 连通等）。"""
        self._checks[name] = fn

    async def is_ready(self) -> tuple[bool, dict]:
        detail: dict = {}
        for name, flag in self._flags.items():
            detail[name] = "ok" if flag else "not_ready"
            if not flag:
                return False, detail
        for name, fn in self._checks.items():
            try:
                ok = await fn()
                detail[name] = "ok" if ok else "failed"
                if not ok:
                    return False, detail
            except Exception as e:
                detail[name] = f"error: {e}"
                return False, detail
        return True, detail


def make_health_router(
    service_name: str,
    registry: ReadinessRegistry,
) -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get("/health", summary="Liveness probe")
    async def liveness() -> dict:
        """进程存活即返回 200，K8s liveness probe 使用。"""
        return {"status": "ok", "service": service_name}

    @router.get("/ready", summary="Readiness probe")
    async def readiness() -> dict:
        """
        所有检查项通过才返回 200，K8s readiness probe 使用。
        单体服务包含模型加载，initialDelaySeconds 建议设 90s。
        """
        ok, detail = await registry.is_ready()
        if not ok:
            logger.warning("not_ready", detail=detail)
            raise HTTPException(
                status_code=503,
                detail={"status": "not_ready", "checks": detail},
            )
        return {"status": "ready", "service": service_name, "checks": detail}

    return router
