"""
Service d'IA Externe - Plant.id API

Ce module gere l'integration avec le service externe Plant.id pour:
- Identification d'especes de plantes
- Diagnostic de maladies
- Evaluation de la sante des plantes

Plant.id offre 100-200 requetes gratuites par jour sans engagement bancaire.
Inscription gratuite sur: https://plant.id/
"""

import json
import os
import base64
import logging
import time
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from io import BytesIO

import httpx
from PIL import Image

logger = logging.getLogger(__name__)


class ExternalAIService:
    """
    Service d'IA externe utilisant Plant.id API.
    
    Fonctionnalites:
    - Identification d'especes de plantes
    - Diagnostic de maladies et problemes de sante
    - Suggestions de soins
    
    API Documentation: https://plant.id/docs
    """
    
    # URLs des APIs Plant.id
    PLANT_ID_URL = "https://plant.id/api/v3/identification"
    PLANT_HEALTH_URL = "https://plant.id/api/v3/health_assessment"
    
    # Mapping des stades de croissance (estimation basee sur la taille/apparence)
    GROWTH_STAGE_MAPPING = {
        "seedling": "plantule",
        "young": "vegetatif",
        "mature": "floraison",
        "flowering": "floraison",
        "fruiting": "fructification",
        "dormant": "senescence"
    }
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialise le service externe.
        
        Args:
            api_key: Cle API Plant.id (gratuite sur https://plant.id/)
        """
        self.api_key = api_key or os.getenv("PLANT_ID_API_KEY", "")
        self.is_configured = bool(self.api_key)
        
        # Client HTTP async
        self.client: Optional[httpx.AsyncClient] = None
        
        # Statistiques
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "avg_response_time_ms": 0
        }
        
        if not self.is_configured:
            logger.warning(
                "Plant.id API key not configured. "
                "Get your free API key at https://plant.id/"
            )
    
    async def initialize(self):
        """Initialise le client HTTP."""
        if self.client is None:
            self.client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "Api-Key": self.api_key,
                    "Content-Type": "application/json"
                }
            )
        return self.is_configured
    
    async def close(self):
        """Ferme le client HTTP."""
        if self.client:
            await self.client.aclose()
            self.client = None
    
    def _encode_image(self, image: Image.Image) -> str:
        """Encode une image PIL en base64."""
        # Convertir en RGB si necessaire
        if image.mode != "RGB":
            image = image.convert("RGB")
        
        # Redimensionner si trop grande (max 1500x1500 pour l'API)
        max_size = 1500
        if image.width > max_size or image.height > max_size:
            image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        # Encoder en JPEG base64
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=85)
        buffer.seek(0)
        
        return base64.b64encode(buffer.read()).decode("utf-8")
    
    async def identify_plant(self, image: Image.Image, latitude: Optional[float] = None, longitude: Optional[float] = None) -> Dict[str, Any]:
        """
        Identifie une plante dans l'image.
        
        Args:
            image: Image PIL a analyser
            
        Returns:
            Resultats de l'identification
        """
        if not self.is_configured:
            return self._mock_response("identification")
        
        await self.initialize()
        
        start_time = time.time()
        
        try:
            # Encoder l'image
            image_base64 = self._encode_image(image)
            
            # Preparer la requete
            payload = {
                "images": [f"data:image/jpeg;base64,{image_base64}"],
                "similar_images": True,
                "classification_level": "species"
            }

            if latitude is not None and longitude is not None:
                payload["latitude"] = latitude
                payload["longitude"] = longitude
                logger.info(f"Using geolocation: lat={latitude}, lon={longitude}")
            
            # Envoyer la requete
            response = await self.client.post(
                self.PLANT_ID_URL,
                json=payload
            )
            
            response_time = (time.time() - start_time) * 1000
            self._update_stats(True, response_time)
            
            if response.status_code in [200, 201]:
                return self._parse_identification_response(response.json())
            else:
                logger.error(f"Plant.id API error: {response.status_code} - {response.text}")
                return self._error_response(f"API error: {response.status_code}")
                
        except Exception as e:
            self._update_stats(False, 0)
            logger.error(f"External AI error: {e}")
            return self._error_response(str(e))
    
    async def assess_health(self, image: Image.Image, latitude: Optional[float] = None, longitude: Optional[float] = None) -> Dict[str, Any]:
        """
        Evalue la sante d'une plante dans l'image.
        
        Args:
            image: Image PIL a analyser
            
        Returns:
            Resultats du diagnostic de sante
        """
        if not self.is_configured:
            return self._mock_response("health")
        
        await self.initialize()
        
        start_time = time.time()
        
        try:
            # Encoder l'image
            image_base64 = self._encode_image(image)
            
            # Preparer la requete
            payload = {
                "images": [f"data:image/jpeg;base64,{image_base64}"],
                "similar_images":True,
                "health": "all",
                "disease_model": "full"
            }

            if latitude is not None and longitude is not None:
                payload["latitude"] = latitude
                payload["longitude"] = longitude
            
            # Envoyer la requete
            response = await self.client.post(
                self.PLANT_HEALTH_URL,
                json=payload
            )
            
            response_time = (time.time() - start_time) * 1000
            self._update_stats(True, response_time)
            
            if response.status_code in [200, 201]:
                return self._parse_health_response(response.json())
            else:
                logger.error(f"Plant.id Health API error: {response.status_code} - {response.text}")
                return {
                    "health_status": "unknown",
                    "health_confidence": 0.0,
                    "health_score": 0.0,
                    "is_healthy": True,
                    "diseases": [],
                    "health_issues": [],
                    "treatments": []
                }
                
        except Exception as e:
            self._update_stats(False, 0)
            logger.error(f"External AI health error: {e}")
            return {
                "health_status": "unknown",
                "health_confidence": 0.0,
                "health_score": 0.0,
                "is_healthy": True,
                "diseases": [],
                "health_issues": [],
                "treatments": []
            }
    
    async def analyze_complete(self, image: Image.Image, latitude: Optional[float] = None, longitude: Optional[float] = None) -> Dict[str, Any]:
        """
        Analyse complete: identification + sante.
        
        Args:
            image: Image PIL a analyser
            
        Returns:
            Resultats combines d'identification et de sante
        """
        start_time = time.time()
        
        # Executer les deux analyses en parallele
        identification_task = self.identify_plant(image, latitude=latitude, longitude=longitude)
        health_task = self.assess_health(image, latitude=latitude, longitude=longitude)
        
        identification, health = await asyncio.gather(
            identification_task,
            health_task,
            return_exceptions=True
        )
        
        # Gerer les exceptions
        if isinstance(identification, Exception):
            identification = self._error_response(str(identification))
        if isinstance(health, Exception):
            health = self._error_response(str(health))
        
        # Combiner les resultats
        result = self._combine_results(identification, health)
        result["inference_time_ms"] = (time.time() - start_time) * 1000
        result["backend"] = "plant.id"
        
        return result
    
    def _parse_identification_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse la reponse d'identification Plant.id."""
        result = {
            "plant_detected": False,
            "plant_confidence": 0.0,
            "species": "unknown",
            "species_confidence": 0.0,
            "species_top3": [],
            "common_names": [],
            "scientific_name": "",
            "family": "",
            "genus": ""
        }
        
        logger.info(f"Plant.id raw response: {json.dumps(data, indent=2)}")

        # Verifier si une plante est detectee
        is_plant = data.get("result", {}).get("is_plant", {})
        result["plant_detected"] = is_plant.get("binary", False)
        result["plant_confidence"] = is_plant.get("probability", 0.0)
        
        # Extraire les suggestions d'especes
        classification = data.get("result", {}).get("classification", {})
        suggestions = classification.get("suggestions", [])

        logger.info(f"Plant detection: binary={result['plant_detected']}, probability={result['plant_confidence']}")
        
        if not result["plant_detected"]:
            logger.info("Plant.id confirms this is NOT a plant image")
            result["not_a_plant"] = True

        """
        if suggestions and not result["plant_detected"]:
            logger.warning(f"Plant.id returned classifications but plant_detected=False. Overriding...")
            result["plant_detected"] = True
            result["plant_confidence"] = max(suggestions[0].get("probability", 0.0), 0.5)
        """
        
        if suggestions:
            # Premiere suggestion (meilleure)
            top = suggestions[0]
            result["species"] = top.get("name", "unknown")
            result["species_confidence"] = top.get("probability", 0.0)
            result["scientific_name"] = top.get("name", "")
            
            # Noms communs
            details = top.get("details", {})
            result["common_names"] = details.get("common_names", [])
            
            # Taxonomie
            taxonomy = details.get("taxonomy", {})
            result["family"] = taxonomy.get("family", "")
            result["genus"] = taxonomy.get("genus", "")
            
            # Top 3 suggestions
            for i, suggestion in enumerate(suggestions[:3]):
                result["species_top3"].append({
                    "species": suggestion.get("name", "unknown"),
                    "confidence": round(suggestion.get("probability", 0.0), 4),
                    "common_names": suggestion.get("details", {}).get("common_names", [])
                })
        
        # Conserver les images similaires brutes pour l'affichage
        result["similar_images_raw"] = []
        for suggestion in suggestions[:6]:
            similar_imgs = suggestion.get("similar_images", [])
            result["similar_images_raw"].append({
                "species": suggestion.get("name", "unknown"),
                "probability": suggestion.get("probability", 0.0),
                "similar_images": similar_imgs
            })
            
        logger.info(f"Parsed result: {result}")
        return result
    
    def _parse_health_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse la reponse de diagnostic de sante Plant.id."""
        result = {
            "health_status": "unknown",
            "health_confidence": 0.0,
            "health_score": 0.0,
            "is_healthy": True,
            "diseases": [],
            "health_issues": [],
            "treatments": []
        }
        
        health_assessment = data.get("result", {}).get("is_healthy", {})
        result["is_healthy"] = health_assessment.get("binary", True)
        result["health_score"] = health_assessment.get("probability", 1.0)
        
        if result["is_healthy"]:
            result["health_status"] = "sain"
            result["health_confidence"] = result["health_score"]
        else:
            result["health_status"] = "malade"
            result["health_confidence"] = 1.0 - result["health_score"]
        
        # Extraire les maladies detectees
        disease_data = data.get("result", {}).get("disease", {})
        suggestions = disease_data.get("suggestions", [])
        
        for disease in suggestions:
            disease_info = {
                "name": disease.get("name", "unknown"),
                "probability": disease.get("probability", 0.0),
                "description": "",
                "treatment": "",
                "cause": ""
            }
            
            details = disease.get("details", {})
            disease_info["description"] = details.get("description", "")
            disease_info["cause"] = details.get("cause", "")
            
            # Traitements
            treatment = details.get("treatment", {})
            if isinstance(treatment, dict):
                treatments = []
                if treatment.get("biological"):
                    treatments.extend(treatment["biological"])
                if treatment.get("chemical"):
                    treatments.extend(treatment["chemical"])
                if treatment.get("prevention"):
                    treatments.extend(treatment["prevention"])
                disease_info["treatment"] = "; ".join(treatments[:3])
            
            result["diseases"].append(disease_info)
            
            # Ajouter aux issues
            severity = "high" if disease_info["probability"] > 0.7 else "medium" if disease_info["probability"] > 0.4 else "low"
            result["health_issues"].append({
                "issue": disease_info["name"],
                "confidence": round(disease_info["probability"], 4),
                "severity": severity,
                "description": disease_info["description"][:200] if disease_info["description"] else ""
            })
        
        return result
    
    def _combine_results(
        self,
        identification: Dict[str, Any],
        health: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Combine les resultats d'identification et de sante."""
        # Si ce n'est pas une plante, retourner un résultat simplifié
        if identification.get("not_a_plant") or not identification.get("plant_detected", False):
            return {
                "plant_detected": False,
                "plant_confidence": identification.get("plant_confidence", 0.0),
                "not_a_plant": True,
                "message": "L'image fournie ne semble pas contenir une plante identifiable.",
                "species": None,
                "species_confidence": 0.0,
                "species_top3": [],
                "health_status": None,
                "health_confidence": 0.0,
                "is_healthy": None,
                "diseases": [],
                "similar_images_raw": identification.get("similar_images_raw", [])
            }
        
        # Mapper le nom d'espece scientifique vers un nom simple
        species_name = identification.get("species", "unknown")
        common_names = identification.get("common_names", [])
        
        # Utiliser le premier nom commun s'il existe
        if common_names:
            display_species = common_names[0].lower().replace(" ", "_")
        else:
            display_species = species_name.lower().replace(" ", "_")
        
        # Determiner le statut de sante
        if health.get("is_healthy", True):
            health_status = "sain"
        elif health.get("diseases"):
            # Utiliser le nom de la premiere maladie
            health_status = health["diseases"][0]["name"].lower().replace(" ", "_")
        else:
            health_status = "stress_hydrique"  # Default si malade mais pas de maladie specifique
        
        return {
            "plant_detected": identification.get("plant_detected", False),
            "plant_confidence": round(identification.get("plant_confidence", 0.0), 4),
            "species": display_species,
            "species_scientific": species_name,
            "species_confidence": round(identification.get("species_confidence", 0.0), 4),
            "species_top3": identification.get("species_top3", []),
            "common_names": common_names,
            "family": identification.get("family", ""),
            "genus": identification.get("genus", ""),
            "growth_stage": "vegetatif",  # Plant.id ne fournit pas cette info
            "growth_stage_confidence": 0.5,
            "health_status": health_status,
            "health_confidence": round(health.get("health_confidence", 0.0), 4),
            "health_score": round(health.get("health_score", 1.0), 4),
            "is_healthy": health.get("is_healthy", True),
            "health_issues": health.get("health_issues", []),
            "diseases": health.get("diseases", []),
            "treatments": health.get("treatments", [])
        }
    
    def _mock_response(self, response_type: str) -> Dict[str, Any]:
        """Genere une reponse simulee quand l'API n'est pas configuree."""
        import random
        
        if response_type == "identification":
            return {
                "plant_detected": True,
                "plant_confidence": random.uniform(0.85, 0.98),
                "species": "Solanum lycopersicum",
                "species_confidence": random.uniform(0.7, 0.95),
                "species_top3": [
                    {"species": "Solanum lycopersicum", "confidence": 0.85, "common_names": ["Tomato"]},
                    {"species": "Solanum tuberosum", "confidence": 0.08, "common_names": ["Potato"]},
                    {"species": "Capsicum annuum", "confidence": 0.04, "common_names": ["Pepper"]}
                ],
                "common_names": ["Tomato", "Garden Tomato"],
                "scientific_name": "Solanum lycopersicum",
                "family": "Solanaceae",
                "genus": "Solanum",
                "_mock": True
            }
        else:  # health
            is_healthy = random.random() > 0.3
            return {
                "health_status": "sain" if is_healthy else "maladie",
                "health_confidence": random.uniform(0.7, 0.95),
                "health_score": random.uniform(0.7, 1.0) if is_healthy else random.uniform(0.2, 0.5),
                "is_healthy": is_healthy,
                "diseases": [] if is_healthy else [{
                    "name": "Early Blight",
                    "probability": random.uniform(0.5, 0.9),
                    "description": "Fungal disease causing dark spots on leaves",
                    "treatment": "Apply copper-based fungicide; Remove affected leaves"
                }],
                "health_issues": [] if is_healthy else [{
                    "issue": "early_blight",
                    "confidence": random.uniform(0.5, 0.9),
                    "severity": "medium"
                }],
                "_mock": True
            }
    
    def _error_response(self, error_message: str) -> Dict[str, Any]:
        """Genere une reponse d'erreur."""
        return {
            "error": True,
            "error_message": error_message,
            "plant_detected": False,
            "plant_confidence": 0.0,
            "species": "unknown",
            "health_status": "unknown",
            "health_score": 0.0
        }
    
    def _update_stats(self, success: bool, response_time: float):
        """Met a jour les statistiques."""
        self.stats["total_requests"] += 1
        
        if success:
            self.stats["successful_requests"] += 1
            n = self.stats["successful_requests"]
            avg = self.stats["avg_response_time_ms"]
            self.stats["avg_response_time_ms"] = (avg * (n - 1) + response_time) / n
        else:
            self.stats["failed_requests"] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du service."""
        return {
            **self.stats,
            "is_configured": self.is_configured,
            "api_url": self.PLANT_ID_URL
        }


# Instance globale
_external_service: Optional[ExternalAIService] = None


async def get_external_ai_service() -> ExternalAIService:
    """Factory pour obtenir l'instance du service externe."""
    global _external_service
    
    if _external_service is None:
        # Try importing settings
        try:
            from api.config import get_settings
            settings = get_settings()
            api_key = settings.plant_id_api_key
        except:
            api_key = ""
        
        # Fallback to os.getenv
        if not api_key:
            api_key = os.getenv("PLANT_ID_API_KEY", "")
        
        _external_service = ExternalAIService(api_key=api_key)
        await _external_service.initialize()
    
    return _external_service


async def analyze_image_external(image_data: bytes) -> Dict[str, Any]:
    """
    Fonction helper pour analyser une image avec le service externe.
    
    Args:
        image_data: Donnees binaires de l'image
        
    Returns:
        Resultats de l'analyse
    """
    service = await get_external_ai_service()
    image = Image.open(BytesIO(image_data))
    return await service.analyze_complete(image)