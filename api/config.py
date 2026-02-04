"""
Configuration module for the Drone AI Agriculture API.
Loads settings from environment variables with sensible defaults.
"""

import os
from typing import List, Optional
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # === API Configuration ===
    api_host: str = Field(default="0.0.0.0", description="API host address")
    api_port: int = Field(default=8000, description="API port")
    api_version: str = Field(default="v1", description="API version")
    debug: bool = Field(default=False, description="Debug mode")
    environment: str = Field(default="development", description="Environment name")

    # === Ngrok Configuration ===
    use_ngrok: bool = Field(default=False, description="Use ngrok for public URL")
    ngrok_auth_token: str = Field(default="", description="Ngrok authentication token")

    # === Security ===
    secret_key: str = Field(default="dev-secret-key-change-in-production", description="Secret key for JWT")
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_expiration_hours: int = Field(default=24, description="JWT expiration in hours")
    cors_origins: List[str] = Field(default=["http://localhost:3000", "http://localhost:8000", "*"], description="Allowed CORS origins")

    # === Database ===
    database_url: str = Field(default="sqlite+aiosqlite:///./data/agriculture.db", description="Database connection URL")

    # === AI Model ===
    model_path: str = Field(default="./models/agriculture_model.h5", description="Path to the trained model")
    onnx_model_path: str = Field(default="./models/agriculture_model.onnx", description="Path to ONNX model")
    confidence_threshold: float = Field(default=0.85, description="Minimum confidence threshold")
    max_image_size: int = Field(default=1920, description="Maximum image dimension")
    batch_size: int = Field(default=32, description="Batch size for inference")

    # === External AI Service (Plant.id) ===
    ai_backend: str = Field(default="local", description="AI backend: 'local' for local model, 'external' for Plant.id API, 'auto' for fallback")
    plant_id_api_key: str = Field(default="", description="Plant.id API key (get free key at https://plant.id/)")
    external_ai_timeout: int = Field(default=30, description="Timeout for external AI service in seconds")
    external_ai_fallback: bool = Field(default=True, description="Fallback to local model if external service fails")
    
    # === Storage ===
    storage_type: str = Field(default="local", description="Storage type: local, s3, minio")
    local_storage_path: str = Field(default="./data/uploads", description="Local storage path")
    s3_endpoint_url: Optional[str] = Field(default=None, description="S3 endpoint URL")
    s3_bucket_name: str = Field(default="drone-agriculture", description="S3 bucket name")
    aws_access_key_id: Optional[str] = Field(default=None, description="AWS access key")
    aws_secret_access_key: Optional[str] = Field(default=None, description="AWS secret key")
    aws_region: str = Field(default="eu-west-1", description="AWS region")
    
    # === MinIO ===
    minio_endpoint: str = Field(default="localhost:9000", description="MinIO endpoint")
    minio_access_key: str = Field(default="minioadmin", description="MinIO access key")
    minio_secret_key: str = Field(default="minioadmin", description="MinIO secret key")
    minio_bucket: str = Field(default="drone-agriculture", description="MinIO bucket")
    minio_secure: bool = Field(default=False, description="Use HTTPS for MinIO")
    
    # === Rate Limiting ===
    rate_limit_requests: int = Field(default=100, description="Rate limit requests")
    rate_limit_period: int = Field(default=60, description="Rate limit period in seconds")

    # === Logging ===
    log_level: str = Field(default="INFO", description="Log level")
    log_format: str = Field(default="json", description="Log format: json or text")
    log_file: Optional[str] = Field(default="./logs/api.log", description="Log file path")
    
    # === Drone Configuration ===
    drone_api_key: str = Field(default="drone-default-key", description="API key for drone authentication")
    drone_heartbeat_interval: int = Field(default=30, description="Drone heartbeat interval in seconds")
    offline_queue_max_size: int = Field(default=1000, description="Maximum offline queue size")

    # === Monitoring ===
    prometheus_enabled: bool = Field(default=True, description="Enable Prometheus metrics")
    prometheus_port: int = Field(default=9090, description="Prometheus port")
    health_check_interval: int = Field(default=60, description="Health check interval")

    # === WebSocket ===
    ws_heartbeat_interval: int = Field(default=30, description="WebSocket heartbeat interval")
    ws_max_connections: int = Field(default=100, description="Maximum WebSocket connections")
    
    # === Dataset Configuration ===
    dataset_path: str = Field(default="./data/datasets", description="Dataset path")
    dataset_cache_path: str = Field(default="./data/cache", description="Dataset cache path")

    # === Kaggle Configuration ===
    kaggle_username: Optional[str] = Field(default="", description="Kaggle username for dataset downloads")
    kaggle_key: Optional[str] = Field(default="", description="Kaggle API key")
    
    # === Email Configuration ===
    smtp_host: Optional[str] = Field(default="", description="SMTP server host")
    smtp_port: Optional[int] = Field(default=587, description="SMTP server port")
    smtp_user: Optional[str] = Field(default="", description="SMTP username")
    smtp_password: Optional[str] = Field(default="", description="SMTP password")
    notification_email: Optional[str] = Field(default="", description="Email for notifications")
    
    # === Weather API ===
    weather_api_key: Optional[str] = Field(default="", description="OpenWeatherMap API key")
    weather_api_url: Optional[str] = Field(default="https://api.openweathermap.org/data/2.5", description="OpenWeatherMap API URL")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    Uses lru_cache to ensure settings are loaded only once.
    """
    return Settings()

# Plant species supported by the model
PLANT_SPECIES = [
    "tomato",
    "potato",
    "corn",
    "wheat",
    "rice",
    "soybean",
    "cotton",
    "sugarcane",
    "sunflower",
    "grape",
    "apple",
    "orange",
    "strawberry",
    "lettuce",
    "carrot",
    "unknown"
]

# Growth stages
GROWTH_STAGES = [
    "germination",
    "seedling",
    "vegetative",
    "flowering",
    "fruiting",
    "mature",
    "harvest_ready",
    "unknown"
]

# Health statuses
HEALTH_STATUSES = [
    "healthy",
    "nitrogen_deficiency",
    "phosphorus_deficiency",
    "potassium_deficiency",
    "water_stress",
    "pest_damage",
    "disease",
    "nutrient_burn",
    "unknown"
]

# Disease types for detailed diagnosis
DISEASE_TYPES = [
    "bacterial_spot",
    "early_blight",
    "late_blight",
    "leaf_mold",
    "septoria_leaf_spot",
    "spider_mites",
    "target_spot",
    "mosaic_virus",
    "yellow_leaf_curl_virus",
    "powdery_mildew",
    "downy_mildew",
    "rust",
    "anthracnose",
    "none"
]