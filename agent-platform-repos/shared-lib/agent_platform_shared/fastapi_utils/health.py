"""
健康检查模块。

liveness  GET /health  进程存活即返回 200，K8s 用于判断是否重启 Pod
readiness GET /ready   所有检查项通过才返回 200，K8s 用于判断是否分流量

用法：
    from agent_platform_shared.fastapi_utils.health import ReadinessRegistry

    registry = ReadinessRegistry()

    # 注册检查项（在 lifespan 里调用）
    registry.mark_ready("models")          # 标记某项已就绪
    registry.register_check("redis", check_redis_fn)  # 注册动态检查函数

    # 在 create_app() 中传入 registry，自动挂载 /health 和 /ready 路由
"""
import time
from typing import Callable, Awaitable
from fastapi import APIRouter, HTTPException
from agent_platform_shared.logging.logger import get_logger

logger = get_logger(__name__)

CheckFn = Callable[[], Awaitable[bool]]


class ReadinessRegistry:
    """
    管理服务的 readiness 状态。
    支持两种方式：
      1. mark_ready(name)：一次性标记（适合模型加载、连接初始化等）
      2. register_check(name, fn)：动态检查函数（适合 Redis ping、DB 连通性等）
    """

    def __init__(self) -> None:
        self._ready_flags: dict[str, bool] = {}
        self._check_fns: dict[str, CheckFn] = {}
        self._start_time = time.time()

    def mark_ready(self, name: str) -> None:
        """标记某个初始化项已完成。"""
        self._ready_flags[name] = True
        logger.info("readiness_flag_set", name=name)

    def mark_not_ready(self, name: str) -> None:
        """标记某个项不可用（如依赖服务故障时降级）。"""
        self._ready_flags[name] = False
        logger.warning("readiness_flag_cleared", name=name)

    def register_check(self, name: str, fn: CheckFn) -> None:
        """注册一个异步检查函数，/ready 时动态调用。"""
        self._check_fns[name] = fn

    async def is_ready(self) -> tuple[bool, dict]:
        """
        综合判断服务是否就绪。
        返回 (is_ready, detail_dict)。
        """
        detail: dict = {}

        # 检查静态标志
        for name, flag in self._ready_flags.items():
            detail[name] = "ok" if flag else "not_ready"
            if not flag:
                return False, detail

        # 执行动态检查函数
        for name, fn in self._check_fns.items():
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
    readiness_registry: ReadinessRegistry,
) -> APIRouter:
    """
    创建包含 /health 和 /ready 的 APIRouter。
    在 create_app() 中自动挂载，各服务无需手写。
    """
    router = APIRouter(tags=["health"])

    @router.get("/health", summary="Liveness probe")
    async def liveness() -> dict:
        """
        K8s liveness probe。
        进程能响应即返回 200，不做任何依赖检查。
        返回 503 时 K8s 会重启 Pod。
        """
        return {
            "status": "ok",
            "service": service_name,
        }

    @router.get("/ready", summary="Readiness probe")
    async def readiness() -> dict:
        """
        K8s readiness probe。
        所有检查项通过才返回 200。
        返回 503 时 K8s 停止给此 Pod 分流量（不重启）。
        """
        ok, detail = await readiness_registry.is_ready()
        if not ok:
            logger.warning("readiness_check_failed", detail=detail)
            raise HTTPException(
                status_code=503,
                detail={"status": "not_ready", "checks": detail},
            )
        return {
            "status": "ready",
            "service": service_name,
            "checks": detail,
        }

    return router
