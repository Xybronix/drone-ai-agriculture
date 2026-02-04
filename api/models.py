"""
Pydantic models for request/response validation.
Defines all data structures used in the API.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict
import uuid


# === Enums ===

class PlantPresence(str, Enum):
    """Plant detection status."""
    DETECTED = "detected"
    NOT_DETECTED = "not_detected"
    UNCERTAIN = "uncertain"


class HealthStatus(str, Enum):
    """Plant health status."""
    HEALTHY = "healthy"
    NITROGEN_DEFICIENCY = "nitrogen_deficiency"
    PHOSPHORUS_DEFICIENCY = "phosphorus_deficiency"
    POTASSIUM_DEFICIENCY = "potassium_deficiency"
    WATER_STRESS = "water_stress"
    PEST_DAMAGE = "pest_damage"
    DISEASE = "disease"
    NUTRIENT_BURN = "nutrient_burn"
    UNKNOWN = "unknown"


class GrowthStage(str, Enum):
    """Plant growth stage."""
    GERMINATION = "germination"
    SEEDLING = "seedling"
    VEGETATIVE = "vegetative"
    FLOWERING = "flowering"
    FRUITING = "fruiting"
    MATURE = "mature"
    HARVEST_READY = "harvest_ready"
    UNKNOWN = "unknown"


class Priority(str, Enum):
    """Action priority level."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionType(str, Enum):
    """Type of recommended action."""
    IRRIGATION = "irrigation"
    FERTILIZATION = "fertilization"
    PEST_CONTROL = "pest_control"
    DISEASE_TREATMENT = "disease_treatment"
    HARVESTING = "harvesting"
    MONITORING = "monitoring"
    SOIL_TREATMENT = "soil_treatment"
    PRUNING = "pruning"
    NO_ACTION = "no_action"


# === Request Models ===

class AnalysisRequest(BaseModel):
    """Request model for image analysis."""
    drone_id: Optional[str] = Field(default=None, description="Drone identifier")
    latitude: Optional[float] = Field(default=None, ge=-90, le=90, description="GPS latitude")
    longitude: Optional[float] = Field(default=None, ge=-180, le=180, description="GPS longitude")
    altitude: Optional[float] = Field(default=None, ge=0, description="Altitude in meters")
    timestamp: Optional[datetime] = Field(default=None, description="Capture timestamp")
    field_id: Optional[str] = Field(default=None, description="Field identifier")
    notes: Optional[str] = Field(default=None, max_length=1000, description="Additional notes")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "drone_id": "drone-001",
            "latitude": 48.8566,
            "longitude": 2.3522,
            "altitude": 50.0,
            "field_id": "field-A1",
            "notes": "Morning capture, clear sky"
        }
    })


class TokenRequest(BaseModel):
    """Request model for authentication token."""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)


class DroneRegistrationRequest(BaseModel):
    """Request model for drone registration."""
    drone_id: str = Field(..., description="Unique drone identifier")
    name: str = Field(..., description="Drone name")
    model: Optional[str] = Field(default=None, description="Drone model")
    firmware_version: Optional[str] = Field(default=None, description="Firmware version")


# === Response Models ===

class PlantDetection(BaseModel):
    """Plant detection result."""
    detected: bool = Field(..., description="Whether a plant was detected")
    confidence: float = Field(..., ge=0, le=1, description="Detection confidence")
    bounding_box: Optional[Dict[str, float]] = Field(
        default=None,
        description="Bounding box coordinates (x, y, width, height)"
    )


class SpeciesIdentification(BaseModel):
    """Species identification result."""
    species: str = Field(..., description="Identified species name")
    confidence: float = Field(..., ge=0, le=1, description="Identification confidence")
    alternative_species: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Alternative species with lower confidence"
    )
    scientific_name: Optional[str] = Field(default=None, description="Scientific name")
    top_suggestions: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Top species suggestions with similar images"
    )

    class Config:
        extra = "allow"


class GrowthStageResult(BaseModel):
    """Growth stage evaluation result."""
    stage: GrowthStage = Field(..., description="Current growth stage")
    confidence: float = Field(..., ge=0, le=1, description="Evaluation confidence")
    days_in_stage: Optional[int] = Field(
        default=None,
        description="Estimated days in current stage"
    )
    expected_next_stage: Optional[str] = Field(
        default=None,
        description="Expected next growth stage"
    )


class HealthDiagnosis(BaseModel):
    """Health diagnosis result."""
    status: HealthStatus = Field(..., description="Overall health status")
    confidence: float = Field(..., ge=0, le=1, description="Diagnosis confidence")
    disease_type: Optional[str] = Field(default=None, description="Specific disease if detected")
    affected_area_percentage: Optional[float] = Field(
        default=None,
        ge=0,
        le=100,
        description="Percentage of affected area"
    )
    severity: Optional[str] = Field(
        default=None,
        description="Severity level: mild, moderate, severe"
    )
    diseases: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Detailed list of detected diseases from external API"
    )
    class Config:
        extra = "allow"


class RecommendedAction(BaseModel):
    """Single recommended action."""
    action_type: ActionType = Field(..., description="Type of action")
    priority: Priority = Field(..., description="Action priority")
    description: str = Field(..., description="Detailed action description")
    timing: Optional[str] = Field(default=None, description="When to perform action")
    products: Optional[List[str]] = Field(
        default=None,
        description="Recommended products"
    )
    estimated_cost: Optional[float] = Field(
        default=None,
        description="Estimated cost in EUR"
    )


class Recommendations(BaseModel):
    """Complete recommendations based on analysis."""
    actions: List[RecommendedAction] = Field(
        default_factory=list,
        description="List of recommended actions"
    )
    summary: str = Field(..., description="Summary of recommendations")
    next_inspection_days: Optional[int] = Field(
        default=7,
        description="Days until next recommended inspection"
    )
    weather_considerations: Optional[str] = Field(
        default=None,
        description="Weather-related advice"
    )


class AnalysisResult(BaseModel):
    """Complete analysis result."""
    analysis_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique analysis identifier"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Analysis timestamp"
    )
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")

    # Analysis components
    plant_detection: PlantDetection = Field(..., description="Plant detection result")
    species_identification: Optional[SpeciesIdentification] = Field(
        default=None,
        description="Species identification (if plant detected)"
    )
    growth_stage: Optional[GrowthStageResult] = Field(
        default=None,
        description="Growth stage (if plant detected)"
    )
    health_diagnosis: Optional[HealthDiagnosis] = Field(
        default=None,
        description="Health diagnosis (if plant detected)"
    )
    recommendations: Recommendations = Field(..., description="Recommendations")

    # Metadata
    image_url: Optional[str] = Field(default=None, description="Stored image URL")
    drone_id: Optional[str] = Field(default=None, description="Source drone ID")
    location: Optional[Dict[str, Optional[float]]] = Field(
        default=None,
        description="GPS location"
    )
    field_id: Optional[str] = Field(default=None, description="Field identifier")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "analysis_id": "123e4567-e89b-12d3-a456-426614174000",
            "timestamp": "2024-01-15T10:30:00Z",
            "processing_time_ms": 245.5,
            "plant_detection": {
                "detected": True,
                "confidence": 0.98
            },
            "species_identification": {
                "species": "tomato",
                "confidence": 0.95
            },
            "growth_stage": {
                "stage": "flowering",
                "confidence": 0.89
            },
            "health_diagnosis": {
                "status": "nitrogen_deficiency",
                "confidence": 0.87,
                "severity": "mild"
            },
            "recommendations": {
                "actions": [
                    {
                        "action_type": "fertilization",
                        "priority": "high",
                        "description": "Apply nitrogen-rich fertilizer",
                        "timing": "Within 48 hours"
                    }
                ],
                "summary": "Nitrogen deficiency detected. Apply fertilizer promptly.",
                "next_inspection_days": 5
            }
        }
    })


class HistoryEntry(BaseModel):
    """Single history entry for analysis results."""
    analysis_id: str
    timestamp: datetime
    drone_id: Optional[str]
    field_id: Optional[str]
    species: Optional[str]
    health_status: Optional[str]
    growth_stage: Optional[str]
    location: Optional[Dict[str, float]]
    thumbnail_url: Optional[str]


class HistoryResponse(BaseModel):
    """Response model for history endpoint."""
    total: int = Field(..., description="Total number of records")
    page: int = Field(..., description="Current page")
    page_size: int = Field(..., description="Items per page")
    entries: List[HistoryEntry] = Field(..., description="History entries")


class HealthResponse(BaseModel):
    """API health check response."""
    status: str = Field(..., description="API status")
    version: str = Field(..., description="API version")
    model_loaded: bool = Field(..., description="Whether AI model is loaded")
    database_connected: bool = Field(..., description="Database connection status")
    uptime_seconds: float = Field(..., description="API uptime in seconds")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Current timestamp"
    )


class TokenResponse(BaseModel):
    """Authentication token response."""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration in seconds")


class ErrorResponse(BaseModel):
    """Error response model."""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Additional details")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Error timestamp"
    )


class DroneHeartbeat(BaseModel):
    """Drone heartbeat message."""
    drone_id: str = Field(..., description="Drone identifier")
    status: str = Field(..., description="Drone status")
    battery_level: Optional[float] = Field(default=None, ge=0, le=100)
    location: Optional[Dict[str, float]] = Field(default=None)
    queue_size: Optional[int] = Field(default=None, ge=0)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class WebSocketMessage(BaseModel):
    """WebSocket message structure."""
    type: str = Field(..., description="Message type")
    payload: Dict[str, Any] = Field(..., description="Message payload")
    timestamp: datetime = Field(default_factory=datetime.utcnow)