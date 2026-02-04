"""
API Routes package.
"""

from api.routes.analyze import router as analyze_router
from api.routes.history import router as history_router
from api.routes.auth import router as auth_router

__all__ = ["analyze_router", "history_router", "auth_router"]