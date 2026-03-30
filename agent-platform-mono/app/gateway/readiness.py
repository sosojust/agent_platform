from typing import Awaitable, Callable

from fastapi import APIRouter, HTTPException

from shared.logging.logger import get_logger

logger = get_logger(__name__)
CheckFn = Callable[[], Awaitable[bool]]


class ReadinessRegistry:
    def __init__(self) -> None:
        self._flags: dict[str, bool] = {}
        self._checks: dict[str, CheckFn] = {}

    def mark_ready(self, name: str) -> None:
        self._flags[name] = True
        logger.info("ready_flag_set", name=name)

    def mark_not_ready(self, name: str) -> None:
        self._flags[name] = False
        logger.warning("ready_flag_cleared", name=name)

    def register_check(self, name: str, fn: CheckFn) -> None:
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


def make_health_router(service_name: str, registry: ReadinessRegistry) -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get("/health", summary="Liveness probe")
    async def liveness() -> dict:
        return {"status": "ok", "service": service_name}

    @router.get("/ready", summary="Readiness probe")
    async def readiness() -> dict:
        ok, detail = await registry.is_ready()
        if not ok:
            logger.warning("not_ready", detail=detail)
            raise HTTPException(
                status_code=503,
                detail={"status": "not_ready", "checks": detail},
            )
        return {"status": "ready", "service": service_name, "checks": detail}

    return router
