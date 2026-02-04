"""
Recommendation Service for generating agricultural recommendations.
Analyzes diagnosis results and generates actionable recommendations.
"""

import logging
from typing import List, Optional, Dict, Any
from api.models import (
    PlantDetection,
    SpeciesIdentification,
    GrowthStageResult,
    HealthDiagnosis,
    Recommendations,
    RecommendedAction,
    ActionType,
    Priority,
    HealthStatus,
    GrowthStage
)

logger = logging.getLogger(__name__)


# Recommendation database organized by condition
RECOMMENDATION_DATABASE = {
    # Health-based recommendations
    HealthStatus.NITROGEN_DEFICIENCY: {
        "actions": [
            {
                "action_type": ActionType.FERTILIZATION,
                "priority": Priority.HIGH,
                "description": "Appliquer un engrais azoté (NPK 20-10-10 ou urée 46%)",
                "timing": "Dans les 48 heures",
                "products": ["Urée 46%", "NPK 20-10-10", "Nitrate d'ammonium"],
                "estimated_cost": 25.0
            },
            {
                "action_type": ActionType.MONITORING,
                "priority": Priority.MEDIUM,
                "description": "Surveiller la coloration des feuilles après traitement",
                "timing": "7 jours après application",
                "products": None,
                "estimated_cost": 0
            }
        ],
        "summary": "Carence en azote détectée. Application d'engrais azoté recommandée rapidement.",
        "next_inspection_days": 5
    },

    HealthStatus.PHOSPHORUS_DEFICIENCY: {
        "actions": [
            {
                "action_type": ActionType.FERTILIZATION,
                "priority": Priority.HIGH,
                "description": "Appliquer un engrais phosphaté (superphosphate ou DAP)",
                "timing": "Dans les 72 heures",
                "products": ["Superphosphate triple", "DAP 18-46-0", "Phosphate naturel"],
                "estimated_cost": 35.0
            },
            {
                "action_type": ActionType.SOIL_TREATMENT,
                "priority": Priority.MEDIUM,
                "description": "Vérifier et corriger le pH du sol si nécessaire",
                "timing": "Avant prochaine fertilisation",
                "products": ["Chite (si pH < 6)", "Soufre (si pH > 7.5)"],
                "estimated_cost": 20.0
            }
        ],
        "summary": "Carence en phosphore identifiée. Fertilisation phosphatée nécessaire.",
        "next_inspection_days": 7
    },

    HealthStatus.POTASSIUM_DEFICIENCY: {
        "actions": [
            {
                "action_type": ActionType.FERTILIZATION,
                "priority": Priority.HIGH,
                "description": "Appliquer un engrais potassique (sulfate de potassium ou KCl)",
                "timing": "Dans les 48 heures",
                "products": ["Sulfate de potassium", "Chlorure de potassium", "NPK 10-10-20"],
                "estimated_cost": 30.0
            }
        ],
        "summary": "Carence en potassium détectée. Apport de potassium recommandé.",
        "next_inspection_days": 5
    },

    HealthStatus.WATER_STRESS: {
        "actions": [
            {
                "action_type": ActionType.IRRIGATION,
                "priority": Priority.CRITICAL,
                "description": "Irrigation immédiate - augmenter la fréquence et/ou le volume",
                "timing": "Immédiatement",
                "products": None,
                "estimated_cost": 10.0
            },
            {
                "action_type": ActionType.SOIL_TREATMENT,
                "priority": Priority.MEDIUM,
                "description": "Appliquer un paillage pour conserver l'humidité du sol",
                "timing": "Dans les 24 heures",
                "products": ["Paille", "Copeaux de bois", "Film plastique"],
                "estimated_cost": 15.0
            },
            {
                "action_type": ActionType.MONITORING,
                "priority": Priority.HIGH,
                "description": "Installer des capteurs d'humidité du sol",
                "timing": "Dès que possible",
                "products": ["Capteur humidité sol"],
                "estimated_cost": 50.0
            }
        ],
        "summary": "Stress hydrique sévère détecté. Irrigation urgente nécessaire.",
        "next_inspection_days": 2
    },

    HealthStatus.PEST_DAMAGE: {
        "actions": [
            {
                "action_type": ActionType.PEST_CONTROL,
                "priority": Priority.HIGH,
                "description": "Identifier le ravageur et appliquer un traitement ciblé",
                "timing": "Dans les 24 heures",
                "products": ["Insecticide biologique", "Pyréthrines", "Bacillus thuringiensis"],
                "estimated_cost": 40.0
            },
            {
                "action_type": ActionType.MONITORING,
                "priority": Priority.MEDIUM,
                "description": "Installer des pièges pour surveiller la population de ravageurs",
                "timing": "Dans les 48 heures",
                "products": ["Pièges à phéromones", "Pièges jaunes collants"],
                "estimated_cost": 20.0
            }
        ],
        "summary": "Dégâts de ravageurs détectés. Traitement phytosanitaire recommandé.",
        "next_inspection_days": 3
    },

    HealthStatus.DISEASE: {
        "actions": [
            {
                "action_type": ActionType.DISEASE_TREATMENT,
                "priority": Priority.CRITICAL,
                "description": "Appliquer un fongicide adapté à la maladie identifiée",
                "timing": "Dans les 24 heures",
                "products": ["Fongicide cuivre", "Bouillie bordelaise", "Trichoderma"],
                "estimated_cost": 45.0
            },
            {
                "action_type": ActionType.PRUNING,
                "priority": Priority.HIGH,
                "description": "Retirer et détruire les parties de plantes infectées",
                "timing": "Immédiatement après traitement",
                "products": ["Sécateur désinfecté"],
                "estimated_cost": 5.0
            },
            {
                "action_type": ActionType.MONITORING,
                "priority": Priority.HIGH,
                "description": "Surveiller la propagation aux plantes voisines",
                "timing": "Quotidiennement pendant 7 jours",
                "products": None,
                "estimated_cost": 0
            }
        ],
        "summary": "Maladie fongique/bactérienne détectée. Traitement urgent nécessaire.",
        "next_inspection_days": 2
    },

    HealthStatus.NUTRIENT_BURN: {
        "actions": [
            {
                "action_type": ActionType.IRRIGATION,
                "priority": Priority.HIGH,
                "description": "Lessiver le sol avec une irrigation abondante",
                "timing": "Immédiatement",
                "products": None,
                "estimated_cost": 15.0
            },
            {
                "action_type": ActionType.MONITORING,
                "priority": Priority.MEDIUM,
                "description": "Suspendre toute fertilisation pendant 2 semaines minimum",
                "timing": "Immédiatement",
                "products": None,
                "estimated_cost": 0
            }
        ],
        "summary": "Brûlure par excès d'engrais détectée. Lessivage du sol recommandé.",
        "next_inspection_days": 7
    },

    HealthStatus.HEALTHY: {
        "actions": [
            {
                "action_type": ActionType.MONITORING,
                "priority": Priority.LOW,
                "description": "Continuer la surveillance régulière",
                "timing": "Selon le calendrier habituel",
                "products": None,
                "estimated_cost": 0
            }
        ],
        "summary": "Plante en bonne santé. Maintenir les pratiques actuelles.",
        "next_inspection_days": 14
    }
}

# Growth stage specific recommendations
GROWTH_STAGE_RECOMMENDATIONS = {
    GrowthStage.GERMINATION: {
        "actions": [
            {
                "action_type": ActionType.IRRIGATION,
                "priority": Priority.MEDIUM,
                "description": "Maintenir une humidité constante du sol",
                "timing": "Quotidiennement",
                "products": None,
                "estimated_cost": 5.0
            }
        ],
        "additional_notes": "Stade critique - éviter le dessèchement et l'engorgement."
    },

    GrowthStage.SEEDLING: {
        "actions": [
            {
                "action_type": ActionType.FERTILIZATION,
                "priority": Priority.MEDIUM,
                "description": "Apport léger d'engrais starter (NPK équilibré)",
                "timing": "Dans la semaine",
                "products": ["NPK 10-10-10 dilué"],
                "estimated_cost": 10.0
            }
        ],
        "additional_notes": "Phase de croissance initiale - nutrition légère recommandée."
    },

    GrowthStage.VEGETATIVE: {
        "actions": [
            {
                "action_type": ActionType.FERTILIZATION,
                "priority": Priority.MEDIUM,
                "description": "Apport d'engrais riche en azote pour la croissance foliaire",
                "timing": "Hebdomadaire",
                "products": ["NPK 20-10-10", "Urée diluée"],
                "estimated_cost": 20.0
            }
        ],
        "additional_notes": "Phase de croissance active - besoins en azote élevés."
    },

    GrowthStage.FLOWERING: {
        "actions": [
            {
                "action_type": ActionType.FERTILIZATION,
                "priority": Priority.MEDIUM,
                "description": "Apport d'engrais riche en phosphore et potassium",
                "timing": "Bi-hebdomadaire",
                "products": ["NPK 10-20-20", "Engrais floraison"],
                "estimated_cost": 25.0
            },
            {
                "action_type": ActionType.PEST_CONTROL,
                "priority": Priority.MEDIUM,
                "description": "Surveillance accrue des pollinisateurs et ravageurs",
                "timing": "Quotidiennement",
                "products": None,
                "estimated_cost": 0
            }
        ],
        "additional_notes": "Phase floraison - attention aux carences en P et K."
    },

    GrowthStage.FRUITING: {
        "actions": [
            {
                "action_type": ActionType.FERTILIZATION,
                "priority": Priority.MEDIUM,
                "description": "Apport de potassium pour le développement des fruits",
                "timing": "Hebdomadaire",
                "products": ["Sulfate de potassium", "NPK 10-10-30"],
                "estimated_cost": 30.0
            },
            {
                "action_type": ActionType.IRRIGATION,
                "priority": Priority.HIGH,
                "description": "Irrigation régulière et constante pour fruits juteux",
                "timing": "Selon les besoins",
                "products": None,
                "estimated_cost": 10.0
            }
        ],
        "additional_notes": "Phase fructification - besoins en eau et potassium élevés."
    },

    GrowthStage.MATURE: {
        "actions": [
            {
                "action_type": ActionType.MONITORING,
                "priority": Priority.MEDIUM,
                "description": "Surveiller la maturité pour récolte optimale",
                "timing": "Quotidiennement",
                "products": None,
                "estimated_cost": 0
            }
        ],
        "additional_notes": "Proche de la récolte - réduire l'irrigation progressivement."
    },

    GrowthStage.HARVEST_READY: {
        "actions": [
            {
                "action_type": ActionType.HARVESTING,
                "priority": Priority.CRITICAL,
                "description": "Récolter dans les meilleurs délais",
                "timing": "Immédiatement",
                "products": ["Matériel de récolte"],
                "estimated_cost": 50.0
            }
        ],
        "additional_notes": "Prêt pour la récolte - ne pas tarder pour qualité optimale."
    }
}


class RecommendationService:
    """
    Service for generating agricultural recommendations.

    Analyzes plant detection, species, growth stage, and health
    to generate prioritized actionable recommendations.
    """

    def __init__(self):
        """Initialize recommendation service."""
        self.recommendation_db = RECOMMENDATION_DATABASE
        self.growth_stage_db = GROWTH_STAGE_RECOMMENDATIONS

    def generate_recommendations(
        self,
        plant_detection: PlantDetection,
        species_id: Optional[SpeciesIdentification] = None,
        growth_stage: Optional[GrowthStageResult] = None,
        health_diagnosis: Optional[HealthDiagnosis] = None,
        weather_data: Optional[Dict[str, Any]] = None
    ) -> Recommendations:
        """
        Generate recommendations based on analysis results.

        Args:
            plant_detection: Plant detection result.
            species_id: Species identification (optional).
            growth_stage: Growth stage (optional).
            health_diagnosis: Health diagnosis (optional).
            weather_data: Weather data for context (optional).

        Returns:
            Recommendations object with prioritized actions.
        """
        actions: List[RecommendedAction] = []
        summary_parts = []

        # If no plant detected
        if not plant_detection.detected:
            return Recommendations(
                actions=[
                    RecommendedAction(
                        action_type=ActionType.MONITORING,
                        priority=Priority.LOW,
                        description="Aucune plante détectée. Vérifier la zone capturée.",
                        timing="Lors de la prochaine inspection"
                    )
                ],
                summary="Aucune plante détectée dans l'image. Ajuster la position du drone ou vérifier la zone.",
                next_inspection_days=7
            )

        # Add health-based recommendations
        if health_diagnosis:
            health_rec = self.recommendation_db.get(health_diagnosis.status)
            if health_rec:
                for action_data in health_rec["actions"]:
                    # Adjust priority based on severity
                    priority = action_data["priority"]
                    if health_diagnosis.severity == "severe":
                        priority = Priority.CRITICAL
                    elif health_diagnosis.severity == "moderate" and priority == Priority.MEDIUM:
                        priority = Priority.HIGH

                    actions.append(RecommendedAction(
                        action_type=action_data["action_type"],
                        priority=priority,
                        description=action_data["description"],
                        timing=action_data["timing"],
                        products=action_data.get("products"),
                        estimated_cost=action_data.get("estimated_cost")
                    ))

                summary_parts.append(health_rec["summary"])
                next_inspection = health_rec["next_inspection_days"]

                # Adjust for severity
                if health_diagnosis.severity == "severe":
                    next_inspection = max(1, next_inspection // 2)

        # Add growth stage specific recommendations
        if growth_stage and growth_stage.stage != GrowthStage.UNKNOWN:
            stage_rec = self.growth_stage_db.get(growth_stage.stage)
            if stage_rec:
                for action_data in stage_rec["actions"]:
                    # Check if similar action already exists
                    existing = any(
                        a.action_type == action_data["action_type"]
                        and a.priority.value >= action_data["priority"].value
                        for a in actions
                    )
                    if not existing:
                        actions.append(RecommendedAction(
                            action_type=action_data["action_type"],
                            priority=action_data["priority"],
                            description=action_data["description"],
                            timing=action_data["timing"],
                            products=action_data.get("products"),
                            estimated_cost=action_data.get("estimated_cost")
                        ))

                if stage_rec.get("additional_notes"):
                    summary_parts.append(stage_rec["additional_notes"])

        # Weather considerations
        weather_notes = None
        if weather_data:
            weather_notes = self._get_weather_advice(weather_data)
            if weather_notes:
                summary_parts.append(weather_notes)

        # Sort actions by priority
        priority_order = {
            Priority.CRITICAL: 0,
            Priority.HIGH: 1,
            Priority.MEDIUM: 2,
            Priority.LOW: 3
        }
        actions.sort(key=lambda a: priority_order.get(a.priority, 99))

        # Generate summary
        if not summary_parts:
            if health_diagnosis and health_diagnosis.status == HealthStatus.HEALTHY:
                summary = "Plante en bonne santé. Continuer les pratiques actuelles."
            else:
                summary = "Analyse terminée. Surveillance régulière recommandée."
        else:
            summary = " ".join(summary_parts)

        # Determine next inspection
        if not actions:
            next_inspection = 14
        elif any(a.priority == Priority.CRITICAL for a in actions):
            next_inspection = 1
        elif any(a.priority == Priority.HIGH for a in actions):
            next_inspection = 3
        else:
            next_inspection = 7

        return Recommendations(
            actions=actions,
            summary=summary,
            next_inspection_days=next_inspection,
            weather_considerations=weather_notes
        )

    def _get_weather_advice(self, weather_data: Dict[str, Any]) -> Optional[str]:
        """Generate weather-based advice."""
        advice_parts = []

        if weather_data.get("rain_forecast"):
            advice_parts.append("Pluie prévue - reporter les traitements foliaires.")

        if weather_data.get("temperature", 20) > 35:
            advice_parts.append("Température élevée - irriguer tôt le matin.")

        if weather_data.get("wind_speed", 0) > 20:
            advice_parts.append("Vent fort - éviter les pulvérisations.")

        if weather_data.get("frost_risk"):
            advice_parts.append("Risque de gel - protéger les cultures sensibles.")

        return " ".join(advice_parts) if advice_parts else None

    def estimate_total_cost(self, recommendations: Recommendations) -> float:
        """Calculate total estimated cost of recommendations."""
        return sum(
            action.estimated_cost or 0
            for action in recommendations.actions
        )


# Singleton instance
_recommendation_service: Optional[RecommendationService] = None


def get_recommendation_service() -> RecommendationService:
    """Get or create Recommendation Service singleton."""
    global _recommendation_service
    if _recommendation_service is None:
        _recommendation_service = RecommendationService()
    return _recommendation_service