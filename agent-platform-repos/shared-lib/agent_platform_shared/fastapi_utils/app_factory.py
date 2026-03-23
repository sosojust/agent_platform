"""
FastAPI 应用工厂。

create_app() 统一创建 FastAPI 实例，自动完成：
  - 挂载 TenantContextMiddleware
  - 注册统一异常处理器
  - 挂载 /health 和 /ready 路由
  - 配置 CORS（可选）

各服务 main.py 只需调用 create_app() 并挂载自己的业务路由：

    from agent_platform_shared.fastapi_utils import create_app, ReadinessRegistry

    readiness = ReadinessRegistry()

    @asynccontextmanager
    async def lifespan(app):
        # 业务初始化...
        readiness.mark_ready("models")
        yield
        # 资源释放...

    app = create_app(
        title="AI Core Service",
        version="0.1.0",
        service_name="ai-core-service",
        readiness_registry=readiness,
        lifespan=lifespan,
    )

    # 只挂业务路由，健康检查路由已自动挂好
    app.include_router(llm_router)
    app.include_router(prompt_router)
"""
from contextlib import asynccontextmanager
from typing import Callable, AsyncIterator, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_platform_shared.fastapi_utils.health import ReadinessRegistry, make_health_router
from agent_platform_shared.fastapi_utils.error_handlers import register_error_handlers
from agent_platform_shared.middleware.tenant import TenantContextMiddleware


def create_app(
    title: str,
    service_name: str,
    version: str = "0.1.0",
    readiness_registry: Optional[ReadinessRegistry] = None,
    lifespan: Optional[Callable] = None,
    enable_cors: bool = False,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """
    创建标准化 FastAPI 应用。

    title:              API 文档标题
    service_name:       服务名，出现在健康检查响应中（建议和 K8s Deployment name 一致）
    version:            服务版本
    readiness_registry: ReadinessRegistry 实例，None 时创建一个空的（永远 ready）
    lifespan:           AsyncContextManager，各服务的启动/关闭逻辑
    enable_cors:        是否开启 CORS（开发环境可开，生产由 Gateway 处理）
    cors_origins:       允许的 CORS origin 列表
    """
    if readiness_registry is None:
        readiness_registry = ReadinessRegistry()

    # 包装 lifespan，确保日志记录
    from agent_platform_shared.logging.logger import get_logger
    logger = get_logger(service_name)

    if lifespan is not None:
        original_lifespan = lifespan

        @asynccontextmanager
        async def wrapped_lifespan(app: FastAPI) -> AsyncIterator[None]:
            logger.info(f"{service_name}_starting", version=version)
            async with original_lifespan(app) if hasattr(original_lifespan, '__aenter__') \
                    else _call_lifespan(original_lifespan, app):
                yield
            logger.info(f"{service_name}_stopped")

        effective_lifespan = wrapped_lifespan
    else:
        @asynccontextmanager
        async def effective_lifespan(app: FastAPI) -> AsyncIterator[None]:
            logger.info(f"{service_name}_starting", version=version)
            yield
            logger.info(f"{service_name}_stopped")

    app = FastAPI(
        title=title,
        version=version,
        lifespan=effective_lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # 1. 中间件（顺序重要：先注册的后执行）
    app.add_middleware(TenantContextMiddleware)

    if enable_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins or ["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # 2. 统一异常处理
    register_error_handlers(app)

    # 3. 健康检查路由（所有服务统一）
    app.include_router(make_health_router(service_name, readiness_registry))

    return app


@asynccontextmanager
async def _call_lifespan(
    lifespan_fn: Callable, app: FastAPI
) -> AsyncIterator[None]:
    """兼容普通 asynccontextmanager 函数形式的 lifespan。"""
    async with lifespan_fn(app):
        yield
