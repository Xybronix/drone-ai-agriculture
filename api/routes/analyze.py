"""
Image Analysis Routes.
Endpoints for analyzing agricultural images.
Supports both local model and external AI service (Plant.id).
"""

import logging
from datetime import datetime
from typing import Optional, Literal
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, Depends, BackgroundTasks, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from api.models import (
    AnalysisResult,
    AnalysisRequest,
    ErrorResponse,
    PlantDetection,
    SpeciesIdentification,
    GrowthStageResult,
    HealthDiagnosis,
    Recommendations,
    GrowthStage,
    HealthStatus
)
from api.database import get_session, Analysis
from api.services.ai_service import get_ai_service, AIService
from api.services.external_ai_service import get_external_ai_service, ExternalAIService
from api.services.storage_service import get_storage_service, StorageService
from api.services.recommendation_service import get_recommendation_service, RecommendationService
from api.routes.auth import get_optional_user
from api.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analyze", tags=["Analysis"])
settings = get_settings()


async def save_analysis_to_db(
    session: AsyncSession,
    result: AnalysisResult,
    image_path: str,
    backend: str = "local",
    user_id: Optional[int] = None,
    guest_identifier: Optional[str] = None
):
    """Background task to save analysis to database."""
    try:
        analysis = Analysis(
            id=result.analysis_id,
            timestamp=result.timestamp,
            processing_time_ms=result.processing_time_ms,
            drone_id=result.drone_id,
            field_id=result.field_id,
            latitude=result.location.get("latitude") if result.location else None,
            longitude=result.location.get("longitude") if result.location else None,
            altitude=result.location.get("altitude") if result.location else None,
            plant_detected=result.plant_detection.detected,
            plant_confidence=result.plant_detection.confidence,
            species=result.species_identification.species if result.species_identification else None,
            species_confidence=result.species_identification.confidence if result.species_identification else None,
            growth_stage=result.growth_stage.stage.value if result.growth_stage else None,
            growth_stage_confidence=result.growth_stage.confidence if result.growth_stage else None,
            health_status=result.health_diagnosis.status.value if result.health_diagnosis else None,
            health_confidence=result.health_diagnosis.confidence if result.health_diagnosis else None,
            disease_type=result.health_diagnosis.disease_type if result.health_diagnosis else None,
            severity=result.health_diagnosis.severity if result.health_diagnosis else None,
            image_path=image_path,
            image_url=result.image_url,
            thumbnail_url=None,
            recommendations=result.recommendations.model_dump() if result.recommendations else None,
            user_id=user_id,
            guest_identifier=guest_identifier,
            backend_used=backend
        )
        session.add(analysis)
        await session.commit()
        logger.info(f"Analysis {result.analysis_id} saved to database (backend: {backend}, user: {user_id or guest_identifier})")
    except Exception as e:
        logger.error(f"Failed to save analysis to database: {e}")
        await session.rollback()


async def analyze_with_external_service(image_data: bytes, latitude: Optional[float] = None, longitude: Optional[float] = None) -> dict:
    """Analyze image using external Plant.id service."""
    from PIL import Image
    from io import BytesIO

    external_service = await get_external_ai_service()
    image = Image.open(BytesIO(image_data))
    return await external_service.analyze_complete(image, latitude=latitude, longitude=longitude)


def convert_external_to_result(external_result: dict, processing_time: float) -> tuple:
    """Convert external service result to internal format."""
    # Plant detection
    plant_detection = PlantDetection(
        detected=external_result.get("plant_detected", False),
        confidence=external_result.get("plant_confidence", 0.0),
        bounding_box={"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8} if external_result.get("plant_detected") else None
    )

    # Species identification avec images similaires
    species_id = None
    if external_result.get("plant_detected"):
        species_name = external_result.get("species", "unknown")
        if isinstance(species_name, str):
            species_name = species_name.lower().replace(" ", "_")[:50]

        top3 = external_result.get("species_top3", [])
        alternatives = []
        
        # Construire les suggestions avec images similaires
        top_suggestions = []
        similar_images_raw = external_result.get("similar_images_raw", [])
        
        for i, item in enumerate(top3[:6]):
            suggestion_data = {
                "species": item.get("species", "unknown"),
                "confidence": item.get("confidence", 0.0),
                "common_names": item.get("common_names", []),
                "similar_images": []
            }
            
            # Associer les images similaires si disponibles
            if i < len(similar_images_raw):
                suggestion_data["similar_images"] = similar_images_raw[i].get("similar_images", [])
            
            top_suggestions.append(suggestion_data)
            
            if i > 0:  # Skip first one for alternatives
                alternatives.append({
                    "species": item.get("species", "unknown"),
                    "confidence": item.get("confidence", 0.0)
                })

        species_id = SpeciesIdentification(
            species=species_name,
            confidence=external_result.get("species_confidence", 0.0),
            alternative_species=alternatives
        )
        
        # Ajouter les suggestions complètes comme attribut supplémentaire
        species_id.top_suggestions = top_suggestions

    # Growth stage
    growth_stage = None
    if external_result.get("plant_detected"):
        growth_stage = GrowthStageResult(
            stage=GrowthStage("vegetative"),
            confidence=0.5,
            days_in_stage=7,
            expected_next_stage="flowering"
        )

    # Health diagnosis
    health_diagnosis = None
    if external_result.get("plant_detected"):
        health_status_str = external_result.get("health_status", "healthy")
        if health_status_str == "sain":
            health_status_str = "healthy"

        status_mapping = {
            "healthy": "healthy",
            "sain": "healthy",
            "malade": "disease",
            "disease": "disease",
            "stress_hydrique": "water_stress",
            "water_stress": "water_stress"
        }
        mapped_status = status_mapping.get(health_status_str.lower(), "unknown")

        try:
            health_status = HealthStatus(mapped_status)
        except ValueError:
            health_status = HealthStatus("unknown")

        disease_type = None
        severity = None
        diseases = external_result.get("diseases", [])
        if diseases and not external_result.get("is_healthy", True):
            disease_type = diseases[0].get("name", "unknown")
            prob = diseases[0].get("probability", 0.5)
            severity = "severe" if prob > 0.7 else "moderate" if prob > 0.4 else "mild"

        health_diagnosis = HealthDiagnosis(
            status=health_status,
            confidence=external_result.get("health_confidence", 0.0),
            disease_type=disease_type,
            affected_area_percentage=30.0 if disease_type else None,
            severity=severity
        )
        
        # Ajouter les maladies détaillées
        if diseases:
            health_diagnosis = HealthDiagnosis(
                status=health_status,
                confidence=external_result.get("health_confidence", 0.0),
                disease_type=disease_type,
                affected_area_percentage=30.0 if disease_type else None,
                severity=severity,
                diseases=diseases
            )

    return plant_detection, species_id, growth_stage, health_diagnosis


@router.post(
    "",
    response_model=AnalysisResult,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Server error"}
    },
    summary="Analyze an agricultural image",
    description="""
    Analyze an agricultural image to detect plants, identify species,
    evaluate growth stage, diagnose health issues, and generate recommendations.

    **Backend Options:**
    - `local`: Use local AI model (default)
    - `external`: Use Plant.id API (requires API key)
    - `auto`: Try external first, fallback to local

    **Multi-task Classification:**
    - Plant detection
    - Species identification
    - Growth stage evaluation
    - Health diagnosis

    **Response includes:**
    - Detailed analysis results for each task
    - Prioritized recommendations
    - Image storage URL (if enabled)
    """
)
async def analyze_image(
    background_tasks: BackgroundTasks,
    request: Request,
    image: UploadFile = File(..., description="Image file to analyze (JPEG, PNG)"),
    backend: Literal["local", "external", "auto"] = Form(
        default="local",
        description="AI backend: 'local', 'external' (Plant.id), or 'auto'"
    ),
    drone_id: Optional[str] = Form(None, description="Drone identifier"),
    latitude: Optional[float] = Form(None, ge=-90, le=90, description="GPS latitude"),
    longitude: Optional[float] = Form(None, ge=-180, le=180, description="GPS longitude"),
    altitude: Optional[float] = Form(None, ge=0, description="Altitude in meters"),
    field_id: Optional[str] = Form(None, description="Field identifier"),
    notes: Optional[str] = Form(None, description="Additional notes"),
    session: AsyncSession = Depends(get_session)
):
    """
    Analyze an uploaded image for agricultural insights.

    Supports two AI backends:
    1. Local model (TensorFlow/ONNX)
    2. External service (Plant.id API)
    """
    # Validate file type
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload an image (JPEG, PNG)."
        )

    # Read image data
    try:
        image_data = await image.read()
        if len(image_data) == 0:
            raise HTTPException(status_code=400, detail="Empty file uploaded")
        if len(image_data) > 10 * 1024 * 1024:  # 10MB limit
            raise HTTPException(status_code=400, detail="File too large. Maximum size is 10MB.")
    except Exception as e:
        logger.error(f"Error reading uploaded file: {e}")
        raise HTTPException(status_code=400, detail="Failed to read uploaded file")

    # Get services
    storage_service = get_storage_service()
    recommendation_service = get_recommendation_service()

    # Determine which backend to use
    effective_backend = backend or settings.ai_backend

    used_backend = effective_backend
    start_time = datetime.utcnow()

    try:
        if effective_backend == "external" or effective_backend == "auto":
            # Try external service
            try:
                external_result = await analyze_with_external_service(image_data, latitude=latitude, longitude=longitude)

                if external_result.get("error"):
                    if effective_backend == "auto" and settings.external_ai_fallback:
                        logger.warning("External service failed, falling back to local")
                        effective_backend = "local"
                    else:
                        raise HTTPException(
                            status_code=503,
                            detail=f"External AI service error: {external_result.get('error_message')}"
                        )
                else:
                    processing_time = external_result.get("inference_time_ms", 0)

                    # Vérifier si ce n'est pas une plante
                    if external_result.get("not_a_plant") or not external_result.get("plant_detected", True):
                        # Retourner directement sans sauvegarder en BD
                        return JSONResponse(
                            status_code=200,
                            content={
                                "analysis_id": str(uuid.uuid4()),
                                "timestamp": datetime.utcnow().isoformat(),
                                "processing_time_ms": processing_time,
                                "plant_detection": {
                                    "detected": False,
                                    "confidence": external_result.get("plant_confidence", 0.0)
                                },
                                "message": "L'image fournie ne semble pas contenir une plante identifiable.",
                                "not_a_plant": True,
                                "backend": "external",
                                "similar_images_raw": external_result.get("similar_images_raw", [])
                            }
                        )
                    
                    plant_detection, species_id, growth_stage, health_diagnosis = \
                        convert_external_to_result(external_result, processing_time)
                    used_backend = "external"

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"External service error: {e}")
                if effective_backend == "auto" and settings.external_ai_fallback:
                    effective_backend = "local"
                else:
                    raise HTTPException(
                        status_code=503,
                        detail=f"External AI service unavailable: {str(e)}"
                    )

        if effective_backend == "local":
            # Use local model
            ai_service = get_ai_service()

            if not ai_service.model_loaded:
                raise HTTPException(
                    status_code=503,
                    detail="AI model not available. Please try again later."
                )

            plant_detection, species_id, growth_stage, health_diagnosis, processing_time = \
                ai_service.analyze_image(image_data)
            used_backend = "local"

        # Generate recommendations
        recommendations = recommendation_service.generate_recommendations(
            plant_detection=plant_detection,
            species_id=species_id,
            growth_stage=growth_stage,
            health_diagnosis=health_diagnosis
        )

        # Save image to storage
        image_path = None
        image_url = None
        try:
            image_path, image_url, thumbnail_url = await storage_service.save_image(
                image_data,
                original_filename=image.filename or "image.jpg"
            )
        except Exception as e:
            logger.warning(f"Failed to save image: {e}")

        # Build location dict
        location = None
        if latitude is not None and longitude is not None:
            location = {
                "latitude": latitude,
                "longitude": longitude,
                "altitude": altitude
            }

        # Calculate total processing time
        if 'processing_time' not in dir():
            processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000

        # Create result
        result = AnalysisResult(
            analysis_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            processing_time_ms=processing_time,
            plant_detection=plant_detection,
            species_identification=species_id,
            growth_stage=growth_stage,
            health_diagnosis=health_diagnosis,
            recommendations=recommendations,
            image_url=image_url,
            drone_id=drone_id,
            location=location,
            field_id=field_id
        )

        # Get user info or guest identifier
        user_id = None
        guest_identifier = None
        
        # Try to get current user from token
        from api.routes.auth import get_optional_user, security
        from fastapi.security import HTTPAuthorizationCredentials
        
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                token = auth_header.split(" ")[1]
                from api.routes.auth import decode_token
                payload = decode_token(token)
                if payload:
                    username = payload.get("sub")
                    from sqlalchemy import select
                    from api.database import User
                    user_result = await session.execute(
                        select(User).where(User.username == username)
                    )
                    user = user_result.scalar_one_or_none()
                    if user:
                        user_id = user.id
            except Exception as e:
                logger.debug(f"Could not extract user from token: {e}")
        
        # If no user, use guest identifier (IP address)
        if user_id is None:
            guest_identifier = request.client.host if request.client else "unknown"
            # Add some uniqueness
            import hashlib
            user_agent = request.headers.get("User-Agent", "")
            guest_identifier = hashlib.md5(f"{guest_identifier}:{user_agent}".encode()).hexdigest()[:16]
        
        # Save to database in background
        background_tasks.add_task(
            save_analysis_to_db,
            session,
            result,
            image_path,
            used_backend,
            user_id,
            guest_identifier
        )

        logger.info(
            f"Analysis completed: {result.analysis_id}, "
            f"backend={used_backend}, "
            f"plant_detected={plant_detection.detected}, "
            f"processing_time={processing_time:.2f}ms"
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}"
        )


@router.post(
    "/external",
    summary="Analyze using external AI service only",
    description="Analyze image using Plant.id API exclusively"
)
async def analyze_external_only(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(..., description="Image file to analyze"),
    drone_id: Optional[str] = Form(None),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    altitude: Optional[float] = Form(None),
    field_id: Optional[str] = Form(None),
    session: AsyncSession = Depends(get_session)
):
    """Analyze using external service only (Plant.id)."""
    return await analyze_image(
        background_tasks=background_tasks,
        image=image,
        backend="external",
        drone_id=drone_id,
        latitude=latitude,
        longitude=longitude,
        altitude=altitude,
        field_id=field_id,
        session=session
    )


@router.get(
    "/backends",
    summary="Get available AI backends",
    description="Returns information about available AI backends"
)
async def get_backends():
    """Get information about available AI backends."""
    ai_service = get_ai_service()
    external_service = await get_external_ai_service()

    return {
        "default_backend": settings.ai_backend,
        "backends": {
            "local": {
                "available": ai_service.model_loaded,
                "type": ai_service.model_type,
                "description": "Local TensorFlow/ONNX model"
            },
            "external": {
                "available": external_service.is_configured,
                "service": "Plant.id",
                "description": "Plant.id API for plant identification and health diagnosis",
                "api_url": "https://plant.id/",
                "free_tier": "100-200 requests/day"
            }
        },
        "fallback_enabled": settings.external_ai_fallback
    }


@router.post(
    "/batch",
    response_model=list[AnalysisResult],
    summary="Analyze multiple images",
    description="Analyze multiple images in a single request (max 10)"
)
async def analyze_batch(
    background_tasks: BackgroundTasks,
    images: list[UploadFile] = File(..., description="Image files to analyze (max 10)"),
    backend: Literal["local", "external", "auto"] = Form(default="local"),
    drone_id: Optional[str] = Form(None),
    field_id: Optional[str] = Form(None),
    session: AsyncSession = Depends(get_session)
):
    """Analyze multiple images in batch."""
    if len(images) > 10:
        raise HTTPException(
            status_code=400,
            detail="Maximum 10 images per batch request"
        )

    results = []
    ai_service = get_ai_service()
    storage_service = get_storage_service()
    recommendation_service = get_recommendation_service()

    for image in images:
        try:
            image_data = await image.read()

            # Choose backend
            if backend == "external" or backend == "auto":
                try:
                    external_result = await analyze_with_external_service(image_data)
                    if not external_result.get("error"):
                        processing_time = external_result.get("inference_time_ms", 0)
                        plant_detection, species_id, growth_stage, health_diagnosis = \
                            convert_external_to_result(external_result, processing_time)
                    else:
                        raise Exception("External service error")
                except Exception:
                    if backend == "auto":
                        plant_detection, species_id, growth_stage, health_diagnosis, processing_time = \
                            ai_service.analyze_image(image_data)
                    else:
                        continue
            else:
                plant_detection, species_id, growth_stage, health_diagnosis, processing_time = \
                    ai_service.analyze_image(image_data)

            recommendations = recommendation_service.generate_recommendations(
                plant_detection=plant_detection,
                species_id=species_id,
                growth_stage=growth_stage,
                health_diagnosis=health_diagnosis
            )

            image_path, image_url, _ = await storage_service.save_image(
                image_data,
                original_filename=image.filename or "image.jpg"
            )

            result = AnalysisResult(
                analysis_id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                processing_time_ms=processing_time,
                plant_detection=plant_detection,
                species_identification=species_id,
                growth_stage=growth_stage,
                health_diagnosis=health_diagnosis,
                recommendations=recommendations,
                image_url=image_url,
                drone_id=drone_id,
                field_id=field_id
            )

            results.append(result)

            background_tasks.add_task(
                save_analysis_to_db,
                session,
                result,
                image_path,
                backend
            )

        except Exception as e:
            logger.error(f"Failed to analyze image {image.filename}: {e}")

    return results


@router.get(
    "/{analysis_id}",
    response_model=AnalysisResult,
    summary="Get analysis by ID",
    responses={404: {"model": ErrorResponse}}
)
async def get_analysis(
    analysis_id: str,
    session: AsyncSession = Depends(get_session)
):
    """Retrieve a specific analysis by its ID."""
    result = await session.execute(
        select(Analysis).where(Analysis.id == analysis_id)
    )
    analysis = result.scalar_one_or_none()

    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    return _analysis_to_result(analysis)


def _analysis_to_result(analysis: Analysis) -> dict:
    """Convert database model to API response."""
    result = {
        "analysis_id": analysis.id,
        "timestamp": analysis.timestamp,
        "processing_time_ms": analysis.processing_time_ms,
        "plant_detection": {
            "detected": analysis.plant_detected,
            "confidence": analysis.plant_confidence or 0
        },
        "drone_id": analysis.drone_id,
        "field_id": analysis.field_id,
        "image_url": analysis.image_url
    }

    if analysis.latitude and analysis.longitude:
        result["location"] = {
            "latitude": analysis.latitude,
            "longitude": analysis.longitude,
            "altitude": analysis.altitude
        }

    if analysis.species:
        result["species_identification"] = {
            "species": analysis.species,
            "confidence": analysis.species_confidence or 0
        }

    if analysis.growth_stage:
        result["growth_stage"] = {
            "stage": analysis.growth_stage,
            "confidence": analysis.growth_stage_confidence or 0
        }

    if analysis.health_status:
        result["health_diagnosis"] = {
            "status": analysis.health_status,
            "confidence": analysis.health_confidence or 0,
            "disease_type": analysis.disease_type,
            "severity": analysis.severity
        }

    if analysis.recommendations:
        result["recommendations"] = analysis.recommendations
    else:
        result["recommendations"] = {
            "actions": [],
            "summary": "No recommendations available"
        }

    return result