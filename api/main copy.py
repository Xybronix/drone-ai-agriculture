"""
Drone AI Agriculture - Main API Entry Point
Cloud-based agricultural analysis API with AI-powered image classification.
"""
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Set

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from api.config import get_settings
from api.database import init_database, close_database
from api.routes import analyze_router, history_router, auth_router
from api.services.ai_service import get_ai_service
from api.models import HealthResponse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

settings = get_settings()

# Prometheus metrics
REQUEST_COUNT = Counter(
    'api_requests_total',
    'Total API requests',
    ['method', 'endpoint', 'status']
)
REQUEST_LATENCY = Histogram(
    'api_request_latency_seconds',
    'API request latency',
    ['method', 'endpoint']
)

# Track startup time for uptime calculation
startup_time = None

# WebSocket connection manager
class ConnectionManager:
    """Manage WebSocket connections for real-time updates."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.add(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.active_connections.discard(conn)

    async def send_personal(self, websocket: WebSocket, message: dict):
        """Send message to specific client."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Failed to send WebSocket message: {e}")


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    global startup_time

    # Startup
    logger.info("Starting Drone AI Agriculture API...")
    startup_time = time.time()

    # Initialize database
    await init_database()
    logger.info("Database initialized")

    # Load AI model
    ai_service = get_ai_service()
    if ai_service.model_loaded:
        logger.info(f"AI model loaded ({ai_service.model_type})")
    else:
        logger.warning("AI model not loaded - running in development mode")

    # Create upload directory
    os.makedirs(settings.local_storage_path, exist_ok=True)
    os.makedirs(os.path.join(settings.local_storage_path, "thumbnails"), exist_ok=True)

    logger.info(f"API ready on {settings.api_host}:{settings.api_port}")

    yield

    # Shutdown
    logger.info("Shutting down API...")
    await close_database()
    logger.info("Database connections closed")


# Create FastAPI application
app = FastAPI(
    title="Drone AI Agriculture API",
    description="""
    ## Agricultural Image Analysis API

    This API provides AI-powered analysis of agricultural images for:
    - **Plant Detection** - Detect presence of plants with high confidence
    - **Species Identification** - Identify plant species
    - **Growth Stage Evaluation** - Determine current growth stage
    - **Health Diagnosis** - Detect diseases, deficiencies, and stress
    - **Smart Recommendations** - Get actionable agricultural advice

    ### Features
    - RESTful API with OpenAPI documentation
    - WebSocket support for real-time streaming
    - JWT authentication
    - Multi-environment support (local, S3, MinIO)
    - Prometheus metrics for monitoring

    ### Authentication
    Most endpoints require authentication. Get a token from `/api/v1/auth/token`.
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request timing middleware
@app.middleware("http")
async def add_timing_middleware(request: Request, call_next):
    """Add request timing and metrics."""
    start_time = time.time()

    response = await call_next(request)

    # Calculate duration
    duration = time.time() - start_time

    # Record metrics
    endpoint = request.url.path
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=endpoint,
        status=response.status_code
    ).inc()
    REQUEST_LATENCY.labels(
        method=request.method,
        endpoint=endpoint
    ).observe(duration)

    # Add timing header
    response.headers["X-Process-Time"] = f"{duration:.4f}"

    return response


# Include routers
app.include_router(analyze_router, prefix="/api/v1")
app.include_router(history_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")


# Mount static files for uploads
if os.path.exists(settings.local_storage_path):
    app.mount(
        "/uploads",
        StaticFiles(directory=settings.local_storage_path),
        name="uploads"
    )


# Health check endpoint
@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """
    Health check endpoint.
    Returns API status, model status, and uptime.
    """
    ai_service = get_ai_service()

    uptime = time.time() - startup_time if startup_time else 0

    return HealthResponse(
        status="healthy",
        version="1.0.0",
        model_loaded=ai_service.model_loaded,
        database_connected=True,  # Would check actual connection in production
        uptime_seconds=uptime,
        timestamp=datetime.utcnow()
    )


# Prometheus metrics endpoint
@app.get("/metrics", tags=["System"])
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


# Root endpoint
@app.get("/", tags=["System"])
async def root():
    """API root - returns basic info."""
    return {
        "name": "Drone AI Agriculture API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


# WebSocket endpoint for real-time streaming
@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    """
    WebSocket endpoint for real-time analysis streaming.

    Clients can connect to receive real-time updates when:
    - New analyses are completed
    - Drone status updates
    - System alerts
    """
    await manager.connect(websocket)

    try:
        # Send welcome message
        await manager.send_personal(websocket, {
            "type": "connected",
            "message": "Connected to Drone AI Agriculture stream",
            "timestamp": datetime.utcnow().isoformat()
        })

        while True:
            # Wait for messages from client
            data = await websocket.receive_json()

            # Handle different message types
            message_type = data.get("type")

            if message_type == "ping":
                await manager.send_personal(websocket, {
                    "type": "pong",
                    "timestamp": datetime.utcnow().isoformat()
                })

            elif message_type == "subscribe":
                # Client wants to subscribe to specific events
                topics = data.get("topics", [])
                await manager.send_personal(websocket, {
                    "type": "subscribed",
                    "topics": topics,
                    "timestamp": datetime.utcnow().isoformat()
                })

            elif message_type == "drone_heartbeat":
                # Drone sending heartbeat
                await manager.broadcast({
                    "type": "drone_status",
                    "payload": data.get("payload", {}),
                    "timestamp": datetime.utcnow().isoformat()
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# Utility function to broadcast analysis results
async def broadcast_analysis(result: dict):
    """Broadcast new analysis result to all connected WebSocket clients."""
    await manager.broadcast({
        "type": "new_analysis",
        "payload": result,
        "timestamp": datetime.utcnow().isoformat()
    })


# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred",
            "timestamp": datetime.utcnow().isoformat()
        }
    )


# Run with uvicorn
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level="info"
    )