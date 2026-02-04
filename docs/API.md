# 📡 Documentation API - Drone AI Agriculture

## Vue d'ensemble

L'API Drone AI Agriculture fournit des endpoints RESTful pour l'analyse d'images agricoles, la gestion de l'historique et l'authentification.

**Base URL**: `http://localhost:8000` (développement) ou `https://votre-api.onrender.com` (production)

**Documentation interactive**: `/docs` (Swagger UI) ou `/redoc` (ReDoc)

## Authentification

L'API utilise des tokens JWT (JSON Web Tokens) pour l'authentification.

### Obtenir un token

```bash
curl -X POST "http://localhost:8000/api/v1/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"username": "user", "password": "password"}'
```

**Réponse:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

### Utiliser le token

Inclure le token dans l'en-tête `Authorization`:

```bash
curl -H "Authorization: Bearer <votre_token>" \
  "http://localhost:8000/api/v1/history"
```

## Endpoints

### 🔍 Analyse d'images

#### POST /api/v1/analyze

Analyse une image agricole et retourne les résultats de classification.

**Request:**
```bash
curl -X POST "http://localhost:8000/api/v1/analyze" \
  -H "Authorization: Bearer <token>" \
  -F "image=@photo.jpg" \
  -F "drone_id=drone-001" \
  -F "latitude=48.8566" \
  -F "longitude=2.3522" \
  -F "field_id=field-A1"
```

**Paramètres:**
| Paramètre | Type | Requis | Description |
|-----------|------|--------|-------------|
| image | file | ✅ | Image JPEG ou PNG (max 10MB) |
| drone_id | string | ❌ | Identifiant du drone |
| latitude | float | ❌ | Latitude GPS (-90 à 90) |
| longitude | float | ❌ | Longitude GPS (-180 à 180) |
| altitude | float | ❌ | Altitude en mètres |
| field_id | string | ❌ | Identifiant du champ |
| notes | string | ❌ | Notes additionnelles |

**Réponse (200 OK):**
```json
{
  "analysis_id": "123e4567-e89b-12d3-a456-426614174000",
  "timestamp": "2024-01-15T10:30:00Z",
  "processing_time_ms": 245.5,
  "plant_detection": {
    "detected": true,
    "confidence": 0.98,
    "bounding_box": {
      "x": 0.1,
      "y": 0.1,
      "width": 0.8,
      "height": 0.8
    }
  },
  "species_identification": {
    "species": "tomato",
    "confidence": 0.95,
    "alternative_species": [
      {"species": "potato", "confidence": 0.03},
      {"species": "pepper", "confidence": 0.02}
    ]
  },
  "growth_stage": {
    "stage": "flowering",
    "confidence": 0.89,
    "days_in_stage": 5,
    "expected_next_stage": "fruiting"
  },
  "health_diagnosis": {
    "status": "nitrogen_deficiency",
    "confidence": 0.87,
    "disease_type": null,
    "affected_area_percentage": 15.5,
    "severity": "mild"
  },
  "recommendations": {
    "actions": [
      {
        "action_type": "fertilization",
        "priority": "high",
        "description": "Appliquer un engrais azoté (NPK 20-10-10)",
        "timing": "Dans les 48 heures",
        "products": ["Urée 46%", "NPK 20-10-10"],
        "estimated_cost": 25.0
      }
    ],
    "summary": "Carence en azote détectée. Application d'engrais azoté recommandée.",
    "next_inspection_days": 5,
    "weather_considerations": null
  },
  "image_url": "/uploads/20240115_103000_abc123.jpg",
  "drone_id": "drone-001",
  "location": {
    "latitude": 48.8566,
    "longitude": 2.3522,
    "altitude": 50.0
  },
  "field_id": "field-A1"
}
```

#### POST /api/v1/analyze/batch

Analyse plusieurs images en une seule requête (max 10).

```bash
curl -X POST "http://localhost:8000/api/v1/analyze/batch" \
  -H "Authorization: Bearer <token>" \
  -F "images=@photo1.jpg" \
  -F "images=@photo2.jpg" \
  -F "drone_id=drone-001"
```

#### GET /api/v1/analyze/{analysis_id}

Récupère une analyse spécifique par son ID.

```bash
curl "http://localhost:8000/api/v1/analyze/123e4567-e89b-12d3-a456-426614174000" \
  -H "Authorization: Bearer <token>"
```

---

### 📊 Historique

#### GET /api/v1/history

Récupère l'historique des analyses avec pagination et filtres.

**Paramètres de requête:**
| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| page | int | 1 | Numéro de page |
| page_size | int | 20 | Éléments par page (max 100) |
| start_date | datetime | - | Date de début |
| end_date | datetime | - | Date de fin |
| drone_id | string | - | Filtrer par drone |
| field_id | string | - | Filtrer par champ |
| species | string | - | Filtrer par espèce |
| health_status | string | - | Filtrer par état de santé |
| growth_stage | string | - | Filtrer par stade |
| plant_detected | bool | - | Filtrer par détection |

**Exemple:**
```bash
curl "http://localhost:8000/api/v1/history?page=1&page_size=10&health_status=healthy" \
  -H "Authorization: Bearer <token>"
```

**Réponse:**
```json
{
  "total": 150,
  "page": 1,
  "page_size": 10,
  "entries": [
    {
      "analysis_id": "123e4567-e89b-12d3-a456-426614174000",
      "timestamp": "2024-01-15T10:30:00Z",
      "drone_id": "drone-001",
      "field_id": "field-A1",
      "species": "tomato",
      "health_status": "healthy",
      "growth_stage": "flowering",
      "location": {"latitude": 48.8566, "longitude": 2.3522},
      "thumbnail_url": "/uploads/thumbnails/thumb_20240115_103000.jpg"
    }
  ]
}
```

#### GET /api/v1/history/stats

Obtient des statistiques agrégées.

```bash
curl "http://localhost:8000/api/v1/history/stats" \
  -H "Authorization: Bearer <token>"
```

**Réponse:**
```json
{
  "total_analyses": 1500,
  "plants_detected": 1425,
  "detection_rate": 95.0,
  "health_distribution": {
    "healthy": 1200,
    "nitrogen_deficiency": 150,
    "disease": 75
  },
  "species_distribution": {
    "tomato": 500,
    "potato": 300,
    "corn": 400
  },
  "growth_stage_distribution": {
    "vegetative": 400,
    "flowering": 350,
    "fruiting": 300
  },
  "avg_processing_time_ms": 215.5,
  "daily_analyses": [
    {"date": "2024-01-15", "count": 50},
    {"date": "2024-01-14", "count": 45}
  ]
}
```

#### GET /api/v1/history/export

Exporte l'historique en JSON ou CSV.

```bash
# Export JSON
curl "http://localhost:8000/api/v1/history/export?format=json&limit=1000" \
  -H "Authorization: Bearer <token>" \
  -o export.json

# Export CSV
curl "http://localhost:8000/api/v1/history/export?format=csv&limit=1000" \
  -H "Authorization: Bearer <token>" \
  -o export.csv
```

#### DELETE /api/v1/history/{analysis_id}

Supprime une analyse (conformité RGPD).

```bash
curl -X DELETE "http://localhost:8000/api/v1/history/123e4567-..." \
  -H "Authorization: Bearer <token>"
```

---

### 🔐 Authentification

#### POST /api/v1/auth/token
Obtenir un token d'accès.

#### POST /api/v1/auth/register
Créer un nouveau compte utilisateur.

#### GET /api/v1/auth/me
Obtenir les informations de l'utilisateur connecté.

#### POST /api/v1/auth/change-password
Changer le mot de passe.

#### POST /api/v1/auth/drone-token
Générer un token longue durée pour un drone (admin uniquement).

---

### ⚙️ Système

#### GET /health

Vérification de l'état de l'API.

```bash
curl "http://localhost:8000/health"
```

**Réponse:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "model_loaded": true,
  "database_connected": true,
  "uptime_seconds": 3600.5,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

#### GET /metrics

Métriques Prometheus pour le monitoring.

---

### 🔌 WebSocket

#### WS /ws/stream

Connexion WebSocket pour le streaming en temps réel.

**Événements reçus:**
```json
// Nouvelle analyse
{
  "type": "new_analysis",
  "payload": { ... },
  "timestamp": "2024-01-15T10:30:00Z"
}

// Status drone
{
  "type": "drone_status",
  "payload": {
    "drone_id": "drone-001",
    "status": "active",
    "battery_level": 85
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Messages envoyés:**
```json
// Ping
{"type": "ping"}

// S'abonner à des événements
{"type": "subscribe", "topics": ["analyses", "drone_status"]}
```

---

## Codes d'erreur

| Code | Description |
|------|-------------|
| 200 | Succès |
| 201 | Créé |
| 400 | Requête invalide |
| 401 | Non authentifié |
| 403 | Accès refusé |
| 404 | Non trouvé |
| 413 | Fichier trop volumineux |
| 429 | Trop de requêtes |
| 500 | Erreur serveur |
| 503 | Service indisponible |

**Format d'erreur:**
```json
{
  "error": "validation_error",
  "message": "Invalid file type. Please upload an image.",
  "details": {"field": "image", "allowed": ["image/jpeg", "image/png"]},
  "timestamp": "2024-01-15T10:30:00Z"
}
```

---

## Rate Limiting

- **Limite**: 100 requêtes par minute par IP
- **En-têtes de réponse**:
  - `X-RateLimit-Limit`: Limite totale
  - `X-RateLimit-Remaining`: Requêtes restantes
  - `X-RateLimit-Reset`: Timestamp de réinitialisation

---

## Exemples de code

### Python

```python
import requests

API_URL = "http://localhost:8000"
TOKEN = "votre_token"

# Analyser une image
with open("image.jpg", "rb") as f:
    response = requests.post(
        f"{API_URL}/api/v1/analyze",
        headers={"Authorization": f"Bearer {TOKEN}"},
        files={"image": f},
        data={"drone_id": "drone-001"}
    )
    result = response.json()
    print(f"Espèce: {result['species_identification']['species']}")
    print(f"Santé: {result['health_diagnosis']['status']}")
```

### JavaScript

```javascript
async function analyzeImage(file) {
    const formData = new FormData();
    formData.append('image', file);
    formData.append('drone_id', 'drone-001');

    const response = await fetch('http://localhost:8000/api/v1/analyze', {
        method: 'POST',
        headers: {
            'Authorization': 'Bearer ' + token
        },
        body: formData
    });

    const result = await response.json();
    console.log('Espèce:', result.species_identification.species);
    console.log('Santé:', result.health_diagnosis.status);
}
```

### cURL

```bash
# Analyse complète
curl -X POST "http://localhost:8000/api/v1/analyze" \
  -H "Authorization: Bearer $TOKEN" \
  -F "image=@field_photo.jpg" \
  -F "drone_id=drone-001" \
  -F "latitude=48.8566" \
  -F "longitude=2.3522" \
  -F "field_id=field-A1" | jq .
```