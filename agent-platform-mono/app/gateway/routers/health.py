from app.gateway.lifespan import readiness
from app.gateway.readiness import make_health_router

router = make_health_router("agent-platform", readiness)
