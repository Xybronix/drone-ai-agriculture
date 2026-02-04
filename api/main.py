"""
Drone AI Agriculture - Main API Entry Point
Cloud-based agricultural analysis API with AI-powered image classification.
"""
from io import BytesIO
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from tkinter import Image
from typing import Set
import uuid
import qrcode

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse, HTMLResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
from pyngrok import ngrok, conf

from api.config import get_settings
from api.database import init_database, close_database
from api.routes import analyze_router, history_router, auth_router
from api.services.ai_service import get_ai_service
from api.services.external_ai_service import get_external_ai_service, ExternalAIService
from api.models import HealthResponse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

settings = get_settings()

# Déclarer les variables globales pour les métriques
REQUEST_COUNT = None
REQUEST_LATENCY = None

# Track startup time for uptime calculation
startup_time = None

# Service externe instance
_external_service: ExternalAIService = None

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


def generate_qr_code(url: str, output_dir: str = "./qrcodes") -> str:
    """Generate QR code with transparent background."""
    os.makedirs(output_dir, exist_ok=True)
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    
    # Create image with transparent background
    img = qr.make_image(fill_color="black", back_color="transparent")
    img = img.convert("RGBA")
    
    # Make white pixels transparent
    data = img.getdata()
    new_data = []
    for item in data:
        if item[0] == 255 and item[1] == 255 and item[2] == 255:
            new_data.append((255, 255, 255, 0))
        else:
            new_data.append(item)
    img.putdata(new_data)
    
    filename = os.path.join(output_dir, "public_url_qrcode.png")
    img.save(filename, "PNG")
    return filename


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    global startup_time, REQUEST_COUNT, REQUEST_LATENCY, _external_service

    # Startup
    logger.info("=" * 60)
    logger.info("🌱 Starting Drone AI Agriculture API...")
    logger.info("=" * 60)

    startup_time = time.time()

    # Initialize database
    await init_database()
    logger.info("✓ Database initialized")

    # Create super admin
    from api.database import create_super_admin
    created = await create_super_admin()
    if created:
        logger.info("✓ Super admin created (username: superadmin, password: SuperAdmin2026!)")
    else:
        logger.info("✓ Super admin already exists")

    # Load AI model
    ai_service = get_ai_service()
    if ai_service.model_loaded:
        logger.info(f"✓ AI model loaded ({ai_service.model_type})")
    else:
        logger.warning("⚠ Local AI model not loaded - running in mock mode")
        logger.info("  Place models in: models/agriculture_model.h5 or models/agriculture_model.onnx")
    
    # Initialize External AI Service (Plant.id)
    try:
        _external_service = await get_external_ai_service()
        if _external_service.is_configured:
            logger.info("✓ Plant.id service configured and available")
            # Masquer la clé API pour la sécurité
            api_key_display = _external_service.api_key
            if len(api_key_display) > 12:
                api_key_display = f"{api_key_display[:8]}...{api_key_display[-4:]}"
            logger.info(f"  API Key: {api_key_display}")
            logger.info(f"  Service URL: {_external_service.PLANT_ID_URL}")
            
            # Vérifier les statistiques
            stats = _external_service.get_stats()
            logger.info(f"  Free tier: 100-200 requests/day (get more at https://plant.id/)")
        else:
            logger.warning("⚠ Plant.id service not configured - will use mock responses")
            logger.info("  To enable Plant.id:")
            logger.info("  1. Get free API key: https://plant.id/")
            logger.info("  2. Set environment: export PLANT_ID_API_KEY='your_key'")
            logger.info("  3. Or add to .env file: PLANT_ID_API_KEY='your_key'")
    except Exception as e:
        logger.error(f"✗ Failed to initialize Plant.id service: {e}")
        _external_service = None

    # Create upload directory
    os.makedirs(settings.local_storage_path, exist_ok=True)
    os.makedirs(os.path.join(settings.local_storage_path, "thumbnails"), exist_ok=True)
    logger.info(f"✓ Storage directories created: {settings.local_storage_path}")

    # Initialize Prometheus metrics
    from prometheus_client import Counter, Histogram
    
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

    logger.info("=" * 60)
    logger.info("📊 Services Status Summary:")
    logger.info("=" * 60)
    local_status = "✓ Available" if ai_service.model_type in ['tensorflow', 'onnx'] else "⚠ Mock mode"
    external_status = "✓ Available" if _external_service and _external_service.is_configured else "⚠ Mock mode"
    
    logger.info(f"  🖥  Local AI:   {local_status}")
    logger.info(f"  🌐 Plant.id:   {external_status}")
    logger.info(f"  💾 Database:   ✓ Connected")
    logger.info(f"  💿 Storage:    ✓ {settings.storage_type.capitalize()}")
    logger.info("=" * 60)
    
    # Display backend configuration
    logger.info("🛠️  Backend Configuration:")
    logger.info(f"  Default: {settings.ai_backend}")
    logger.info(f"  Auto-fallback: {'Enabled' if settings.external_ai_fallback else 'Disabled'}")
    
    logger.info("=" * 60)
    logger.info("🚀 API Ready!")
    logger.info("=" * 60)

    # Start ngrok tunnel if enabled
    if settings.use_ngrok:
        try:
            if settings.ngrok_auth_token:
                conf.get_default().auth_token = settings.ngrok_auth_token
            
            public_url = ngrok.connect(settings.api_port, "http").public_url
            
            logger.info("=" * 60)
            logger.info("🌍 NGROK TUNNEL ACTIVE")
            logger.info("=" * 60)
            logger.info(f"🔗 Public URL: {public_url}")
            logger.info(f"📱 Web Interface: {public_url}/web")
            logger.info(f"📚 API Docs: {public_url}/docs")
            
            # Generate QR Code
            qr_path = generate_qr_code(public_url)
            logger.info(f"📷 QR Code saved: {qr_path}")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"❌ Failed to start ngrok: {e}")
            logger.info("💡 Get your free auth token at: https://ngrok.com")

    logger.info(f"🌐 Web Interface:  http://{settings.api_host}:{settings.api_port}/")
    logger.info(f"💻 Dashboard Interface:  http://{settings.api_host}:{settings.api_port}/web")
    logger.info(f"📚 API Docs:       http://{settings.api_host}:{settings.api_port}/docs")
    logger.info(f"❤️  Health Check:   http://{settings.api_host}:{settings.api_port}/health")
    logger.info(f"📊 Metrics:        http://{settings.api_host}:{settings.api_port}/metrics")
    logger.info("=" * 60)
    logger.info("💡 Usage:")
    logger.info("  • Upload images via /api/v1/analyze")
    logger.info("  • Choose backend: local, external, or auto")
    logger.info("  • View history at /api/v1/history")
    logger.info("=" * 60)

    yield

    # Shutdown
    logger.info("\n" + "=" * 60)
    logger.info("🛑 Shutting down API...")
    logger.info("=" * 60)
    
    # Close external service
    if _external_service:
        await _external_service.close()
        logger.info("✓ Plant.id service closed")
    
    # Disconnect ngrok
    if settings.use_ngrok:
        ngrok.disconnect(public_url)
        logger.info("✓ Ngrok tunnel closed")
        
    await close_database()
    logger.info("✓ Database connections closed")
    
    logger.info("=" * 60)
    logger.info("👋 API shutdown complete")
    logger.info("=" * 60)


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

    ### Backend Options
    - **Local**: TensorFlow/ONNX model (fast, offline)
    - **External**: Plant.id API (accurate, 100-200 free requests/day)
    - **Auto**: Smart fallback between local and external

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

    # Record metrics only if they exist
    if REQUEST_COUNT and REQUEST_LATENCY:
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

# Serve web interface
@app.get("/web", response_class=HTMLResponse)
async def serve_homepage():
    """Serve the web interface homepage."""
    try:
        # Try multiple possible locations
        possible_paths = [
            os.path.join(os.path.dirname(__file__), "web", "index.html"),
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "index.html"),
            os.path.join(os.getcwd(), "web", "index.html"),
        ]
        
        for web_path in possible_paths:
            if os.path.exists(web_path):
                return FileResponse(web_path, media_type="text/html")
        
        # If not found, return simple HTML
        return HTMLResponse(content=root().body.decode(), status_code=404)
    except Exception as e:
        logger.error(f"Failed to serve homepage: {e}")
        return HTMLResponse(content=f"<h1>Error: {e}</h1>", status_code=500)


# Health check endpoint
@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """
    Health check endpoint.
    Returns API status, model status, and uptime.
    """
    ai_service = get_ai_service()

     # Check external service status
    external_available = False
    if _external_service:
        external_available = _external_service.is_configured
    
    uptime = time.time() - startup_time if startup_time else 0

    return HealthResponse(
        status="healthy",
        version="1.0.0",
        model_loaded=ai_service.model_loaded,
        database_connected=True,  # Would check actual connection in production
        uptime_seconds=uptime,
        timestamp=datetime.utcnow()
    )


# Extended health endpoint with detailed info
@app.get("/health/detailed", tags=["System"])
async def health_detailed():
    """Detailed health check with service status."""
    ai_service = get_ai_service()
    
    services = {
        "api": {
            "status": "healthy",
            "version": "1.0.0",
            "uptime_seconds": time.time() - startup_time if startup_time else 0
        },
        "database": {
            "status": "connected",
            "url": settings.database_url.split('://')[0] if '://' in settings.database_url else settings.database_url
        },
        "local_ai": {
            "status": "available" if ai_service.model_type in ['tensorflow', 'onnx'] else "mock",
            "model_type": ai_service.model_type,
            "model_loaded": ai_service.model_loaded
        },
        "external_ai": {
            "status": "available" if _external_service and _external_service.is_configured else "mock",
            "service": "plant.id",
            "configured": _external_service.is_configured if _external_service else False,
            "api_url": _external_service.PLANT_ID_URL if _external_service else None
        },
        "storage": {
            "type": settings.storage_type,
            "status": "available",
            "path": settings.local_storage_path
        }
    }
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "status": "healthy",
        "services": services
    }


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
    return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
            <head>
                <title>Drone AI Agriculture</title>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
                        color: white;
                        margin: 0;
                        min-height: 100vh;
                        display: flex;
                        flex-direction: column;
                        align-items: center;
                        justify-content: center;
                        padding: 20px;
                    }
                    .container {
                        max-width: 800px;
                        text-align: center;
                    }
                    .logo {
                        font-size: 3rem;
                        margin-bottom: 1rem;
                    }
                    h1 {
                        font-size: 2.5rem;
                        margin-bottom: 1rem;
                        background: linear-gradient(135deg, #10b981 0%, #3b82f6 100%);
                        -webkit-background-clip: text;
                        -webkit-text-fill-color: transparent;
                        background-clip: text;
                    }
                    .card {
                        background: rgba(30, 41, 59, 0.8);
                        border: 1px solid #334155;
                        border-radius: 1rem;
                        padding: 2rem;
                        margin: 2rem 0;
                        backdrop-filter: blur(10px);
                    }
                    .links {
                        display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                        gap: 1rem;
                        margin-top: 2rem;
                    }
                    .link {
                        display: flex;
                        flex-direction: column;
                        align-items: center;
                        padding: 1.5rem;
                        background: #1e293b;
                        border-radius: 0.75rem;
                        text-decoration: none;
                        color: white;
                        transition: all 0.3s ease;
                        border: 2px solid transparent;
                    }
                    .link:hover {
                        transform: translateY(-2px);
                        border-color: #10b981;
                        box-shadow: 0 10px 30px rgba(16, 185, 129, 0.2);
                    }
                    .link i {
                        font-size: 2rem;
                        margin-bottom: 0.5rem;
                    }
                    .link .title {
                        font-weight: 600;
                        margin-bottom: 0.25rem;
                    }
                    .link .desc {
                        font-size: 0.875rem;
                        opacity: 0.7;
                    }
                    .status {
                        display: inline-flex;
                        align-items: center;
                        gap: 0.5rem;
                        padding: 0.5rem 1rem;
                        border-radius: 9999px;
                        font-size: 0.875rem;
                        font-weight: 600;
                    }
                    .status.online {
                        background: rgba(16, 185, 129, 0.2);
                        color: #10b981;
                    }
                    .status.offline {
                        background: rgba(239, 68, 68, 0.2);
                        color: #ef4444;
                    }
                    code {
                        background: #0f172a;
                        padding: 0.25rem 0.5rem;
                        border-radius: 0.375rem;
                        font-family: 'JetBrains Mono', monospace;
                        font-size: 0.875rem;
                    }
                </style>
                <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
            </head>
            <body>
                <div class="container">
                    <div class="logo">🌱</div>
                    <h1>Drone AI Agriculture API</h1>
                    
                    <div class="card">
                        <div class="status online">
                            <span class="w-3 h-3 rounded-full bg-green-500"></span>
                            <span>API Online</span>
                        </div>
                        
                        <p style="margin-top: 1rem; opacity: 0.8;">
                            API agricole intelligente avec analyse d'images par IA
                        </p>
                        
                        <div style="margin-top: 2rem; text-align: left; max-width: 600px; margin-left: auto; margin-right: auto;">
                            <h3 style="margin-bottom: 1rem;">Services disponibles :</h3>
                            <ul style="list-style: none; padding: 0;">
                                <li style="margin-bottom: 0.5rem;">✓ <strong>IA locale</strong> : TensorFlow/ONNX</li>
                                <li style="margin-bottom: 0.5rem;">✓ <strong>Plant.id</strong> : Service externe d'identification</li>
                                <li style="margin-bottom: 0.5rem;">✓ <strong>Base de données</strong> : Stockage des analyses</li>
                                <li style="margin-bottom: 0.5rem;">✓ <strong>WebSocket</strong> : Communication temps réel</li>
                            </ul>
                        </div>
                    </div>
                    
                    <div class="links">
                        <a href="/docs" class="link">
                            <i class="fas fa-book" style="color: #10b981;"></i>
                            <div class="title">API Documentation</div>
                            <div class="desc">Documentation Swagger/OpenAPI</div>
                        </a>
                        
                        <a href="/web" class="link">
                            <i class="fas fa-globe" style="color: #3b82f6;"></i>
                            <div class="title">Interface Web</div>
                            <div class="desc">Interface utilisateur complète</div>
                        </a>
                        
                        <a href="/health" class="link">
                            <i class="fas fa-heart-pulse" style="color: #ef4444;"></i>
                            <div class="title">Health Check</div>
                            <div class="desc">État des services</div>
                        </a>
                        
                        <a href="/metrics" class="link">
                            <i class="fas fa-chart-line" style="color: #8b5cf6;"></i>
                            <div class="title">Métriques</div>
                            <div class="desc">Statistiques Prometheus</div>
                        </a>
                    </div>
                </div>
            </body>
        </html>
        """)

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


# Backend status endpoint
@app.get("/api/v1/backends/status", tags=["System"])
async def get_backend_status():
    """Get status of all available AI backends."""
    ai_service = get_ai_service()
    
    backends = {
        "local": {
            "available": ai_service.model_type in ["tensorflow", "onnx"],
            "type": ai_service.model_type,
            "model_loaded": ai_service.model_loaded,
            "status": "ready" if ai_service.model_type in ["tensorflow", "onnx"] else "mock",
            "description": "Local TensorFlow/ONNX model"
        },
        "external": {
            "available": _external_service is not None and _external_service.is_configured,
            "status": "configured" if _external_service and _external_service.is_configured else "not_configured",
            "service": "plant.id",
            "description": "Plant.id API for plant identification and health diagnosis",
            "api_url": "https://plant.id/",
            "free_tier": "100-200 requests/day"
        }
    }
    
    return {
        "backends": backends,
        "default_backend": settings.ai_backend,
        "fallback_enabled": settings.external_ai_fallback,
        "timestamp": datetime.utcnow().isoformat()
    }


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