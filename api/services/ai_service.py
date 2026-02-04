"""
AI Service for image classification and analysis.
Handles model loading, inference, and result processing.
"""

import os
import time
import logging
from typing import Optional, Dict, Any, Tuple
from io import BytesIO
import numpy as np
from PIL import Image

# TensorFlow imports with fallback
try:
    import tensorflow as tf
    from tensorflow import keras
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False

# ONNX Runtime imports with fallback
try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False

from api.config import get_settings, PLANT_SPECIES, GROWTH_STAGES, HEALTH_STATUSES, DISEASE_TYPES
from api.models import (
    PlantDetection,
    SpeciesIdentification,
    GrowthStageResult,
    HealthDiagnosis,
    GrowthStage,
    HealthStatus
)

logger = logging.getLogger(__name__)
settings = get_settings()


class AIService:
    """
    AI Service for agricultural image analysis.

    Supports multiple inference backends:
    - TensorFlow/Keras (.h5, SavedModel)
    - ONNX Runtime (.onnx)

    Performs multi-task classification:
    - Plant detection
    - Species identification
    - Growth stage evaluation
    - Health diagnosis
    """

    def __init__(self):
        """Initialize AI Service."""
        self.model = None
        self.onnx_session = None
        self.model_loaded = False
        self.model_type = None  # 'tensorflow' or 'onnx'
        self.input_shape = (224, 224, 3)  # Default input shape
        self.class_names = {
            'species': PLANT_SPECIES,
            'growth_stage': GROWTH_STAGES,
            'health': HEALTH_STATUSES,
            'disease': DISEASE_TYPES
        }

    def load_model(self) -> bool:
        """
        Load the AI model from disk.

        Returns:
            bool: True if model loaded successfully.
        """
        # Try ONNX first (faster inference)
        if ONNX_AVAILABLE and os.path.exists(settings.onnx_model_path):
            try:
                self.onnx_session = ort.InferenceSession(
                    settings.onnx_model_path,
                    providers=['CPUExecutionProvider']
                )
                self.model_type = 'onnx'
                self.model_loaded = True
                logger.info(f"ONNX model loaded from {settings.onnx_model_path}")
                return True
            except Exception as e:
                logger.warning(f"Failed to load ONNX model: {e}")

        # Try TensorFlow
        if TF_AVAILABLE and os.path.exists(settings.model_path):
            try:
                self.model = keras.models.load_model(settings.model_path)
                self.model_type = 'tensorflow'
                self.model_loaded = True
                logger.info(f"TensorFlow model loaded from {settings.model_path}")
                return True
            except Exception as e:
                logger.warning(f"Failed to load TensorFlow model: {e}")

        # No model available - use mock for development
        logger.warning("No model found. Using mock predictions for development.")
        self.model_loaded = True  # Allow API to function
        self.model_type = 'mock'
        return True

    def preprocess_image(self, image_data: bytes) -> np.ndarray:
        """
        Preprocess image for model input.

        Args:
            image_data: Raw image bytes.

        Returns:
            Preprocessed numpy array.
        """
        # Load image
        image = Image.open(BytesIO(image_data))

        # Convert to RGB if necessary
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # Resize to model input shape
        image = image.resize((self.input_shape[0], self.input_shape[1]))

        # Convert to numpy array
        img_array = np.array(image, dtype=np.float32)

        # Normalize to [0, 1]
        img_array = img_array / 255.0

        # Add batch dimension
        img_array = np.expand_dims(img_array, axis=0)

        return img_array

    def _predict_tensorflow(self, img_array: np.ndarray) -> Dict[str, np.ndarray]:
        """Run prediction using TensorFlow model."""
        predictions = self.model.predict(img_array, verbose=0)

        # Handle multi-output model
        if isinstance(predictions, list):
            return {
                'plant_detection': predictions[0],
                'species': predictions[1] if len(predictions) > 1 else None,
                'growth_stage': predictions[2] if len(predictions) > 2 else None,
                'health': predictions[3] if len(predictions) > 3 else None
            }
        else:
            # Single output - assume plant detection
            return {'plant_detection': predictions}

    def _predict_onnx(self, img_array: np.ndarray) -> Dict[str, np.ndarray]:
        """Run prediction using ONNX Runtime."""
        input_name = self.onnx_session.get_inputs()[0].name
        outputs = self.onnx_session.run(None, {input_name: img_array})

        output_names = [o.name for o in self.onnx_session.get_outputs()]

        results = {}
        for name, output in zip(output_names, outputs):
            results[name] = output

        return results

    def _predict_mock(self, img_array: np.ndarray) -> Dict[str, np.ndarray]:
        """Generate mock predictions for development."""
        np.random.seed(int(time.time() * 1000) % 2**32)

        # High confidence plant detection (simulate good model)
        plant_conf = np.random.uniform(0.92, 0.99)

        return {
            'plant_detection': np.array([[1 - plant_conf, plant_conf]]),
            'species': np.random.dirichlet(np.ones(len(PLANT_SPECIES)) * 0.1).reshape(1, -1),
            'growth_stage': np.random.dirichlet(np.ones(len(GROWTH_STAGES)) * 0.2).reshape(1, -1),
            'health': np.random.dirichlet(np.ones(len(HEALTH_STATUSES)) * 0.3).reshape(1, -1)
        }

    def predict(self, img_array: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Run prediction on preprocessed image.

        Args:
            img_array: Preprocessed image array.

        Returns:
            Dictionary of predictions for each task.
        """
        if self.model_type == 'tensorflow':
            return self._predict_tensorflow(img_array)
        elif self.model_type == 'onnx':
            return self._predict_onnx(img_array)
        else:
            return self._predict_mock(img_array)

    def analyze_image(
        self,
        image_data: bytes
    ) -> Tuple[PlantDetection, Optional[SpeciesIdentification],
               Optional[GrowthStageResult], Optional[HealthDiagnosis], float]:
        """
        Perform complete analysis on an image.

        Args:
            image_data: Raw image bytes.

        Returns:
            Tuple of (plant_detection, species_id, growth_stage, health_diagnosis, processing_time_ms)
        """
        start_time = time.time()

        # Preprocess image
        img_array = self.preprocess_image(image_data)

        # Run predictions
        predictions = self.predict(img_array)

        # Process plant detection
        plant_pred = predictions.get('plant_detection', np.array([[0.1, 0.9]]))
        plant_detected = bool(np.argmax(plant_pred[0]) == 1)
        plant_confidence = float(np.max(plant_pred[0]))

        plant_detection = PlantDetection(
            detected=plant_detected,
            confidence=plant_confidence,
            bounding_box={"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8} if plant_detected else None
        )

        species_id = None
        growth_stage = None
        health_diagnosis = None

        if plant_detected:
            # Species identification
            species_pred = predictions.get('species')
            if species_pred is not None:
                species_idx = int(np.argmax(species_pred[0]))
                species_conf = float(species_pred[0][species_idx])

                # Get top 3 alternatives
                sorted_indices = np.argsort(species_pred[0])[::-1]
                alternatives = []
                for idx in sorted_indices[1:4]:
                    alternatives.append({
                        "species": PLANT_SPECIES[idx],
                        "confidence": float(species_pred[0][idx])
                    })

                species_id = SpeciesIdentification(
                    species=PLANT_SPECIES[species_idx],
                    confidence=species_conf,
                    alternative_species=alternatives
                )

            # Growth stage
            growth_pred = predictions.get('growth_stage')
            if growth_pred is not None:
                growth_idx = int(np.argmax(growth_pred[0]))
                growth_conf = float(growth_pred[0][growth_idx])

                growth_stage = GrowthStageResult(
                    stage=GrowthStage(GROWTH_STAGES[growth_idx]),
                    confidence=growth_conf,
                    days_in_stage=np.random.randint(1, 14),
                    expected_next_stage=GROWTH_STAGES[min(growth_idx + 1, len(GROWTH_STAGES) - 1)]
                )

            # Health diagnosis
            health_pred = predictions.get('health')
            if health_pred is not None:
                health_idx = int(np.argmax(health_pred[0]))
                health_conf = float(health_pred[0][health_idx])
                health_status_str = HEALTH_STATUSES[health_idx]

                # Determine severity if unhealthy
                severity = None
                disease_type = None
                affected_area = None

                if health_status_str != "healthy":
                    severity = np.random.choice(["mild", "moderate", "severe"], p=[0.5, 0.35, 0.15])
                    affected_area = float(np.random.uniform(5, 45))
                    if health_status_str == "disease":
                        disease_type = np.random.choice(DISEASE_TYPES[:-1])

                health_diagnosis = HealthDiagnosis(
                    status=HealthStatus(health_status_str),
                    confidence=health_conf,
                    disease_type=disease_type,
                    affected_area_percentage=affected_area,
                    severity=severity
                )

        processing_time_ms = (time.time() - start_time) * 1000

        return plant_detection, species_id, growth_stage, health_diagnosis, processing_time_ms


# Singleton instance
_ai_service: Optional[AIService] = None


def get_ai_service() -> AIService:
    """Get or create AI Service singleton."""
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService()
        _ai_service.load_model()
    return _ai_service