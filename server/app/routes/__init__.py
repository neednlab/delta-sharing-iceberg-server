from app.routes.shares import router as shares_router
from app.routes.metadata import router as metadata_router
from app.routes.version import router as version_router
from app.routes.query import router as query_router
from app.routes.health import router as health_router

__all__ = [
    "shares_router",
    "metadata_router",
    "version_router",
    "query_router",
    "health_router",
]
