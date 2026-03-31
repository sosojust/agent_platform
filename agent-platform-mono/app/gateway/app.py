from fastapi import FastAPI

from app.gateway.error_handlers import register_error_handlers
from app.gateway.lifespan import lifespan
from app.gateway.routers.agents import router as agents_router
from app.gateway.routers.health import router as health_router
from app.gateway.routers.observability import router as observability_router
from app.gateway.routers.tools import router as tools_router
from shared.logging.logger import configure_logging
from shared.middleware.tenant import TenantContextMiddleware

configure_logging()

app = FastAPI(
    title="Agent Platform",
    description="团险业务 Agent Platform",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(TenantContextMiddleware)
register_error_handlers(app)
app.include_router(health_router)
app.include_router(tools_router)
app.include_router(agents_router)
app.include_router(observability_router)
