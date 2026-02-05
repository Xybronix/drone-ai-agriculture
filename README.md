# 🚁 Drone AI Agriculture - Surveillance Agricole Intelligente

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com/)
[![TensorFlow](https://img.shields.io/badge/TensorFlow-2.15+-orange.svg)](https://tensorflow.org/)
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/votre-repo/drone-ai-agriculture/blob/main/ml/notebooks/training_colab.ipynb)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Solution complète de surveillance agricole par drone avec **IA hébergée dans le cloud** permettant l'analyse en temps réel de l'état des cultures, la génération automatique de recommandations agricoles, et l'historisation centralisée des analyses.

## 🌟 Fonctionnalités

### 🤖 Intelligence Artificielle Cloud
- **Classification multi-tâches** : Détection plante, identification espèce, stade de croissance, diagnostic santé
- **Précision élevée** : ≥85% sur toutes les tâches
- **Recommandations automatiques** : Actions prioritaires au format JSON
- **API RESTful** : Documentée OpenAPI avec WebSocket temps réel

### 🚁 Système Drone (Raspberry Pi)
- **Acquisition vidéo** : 1080p @ 30fps
- **Transmission sécurisée** : TLS 1.3
- **Mode offline** : File d'attente locale (1000+ images)
- **Intégration Pixhawk** : Contrôle de vol basique

### 🖥️ Interface Web
- **Test du modèle** : Upload image ou webcam temps réel
- **Dashboard** : Visualisation historique des analyses
- **Responsive** : Mobile, tablette, desktop
- **Thème clair/sombre** : Adaptatif

## 🚀 Déploiement

### Déploiement sur Render (Recommandé)

Pour déployer rapidement sur Render, consultez le [Guide de Déploiement](DEPLOY.md).

**Déploiement en 3 étapes :**
1. Connectez votre dépôt Git à Render
2. Render détecte automatiquement `render.yaml`
3. Configurez `PLANT_ID_API_KEY` dans les variables d'environnement

Votre application sera accessible en quelques minutes !

### Installation Locale

## 🚀 Quick Start (5 minutes)

### Prérequis
- Python 3.8+
- pip ou conda
- Git

### Installation rapide

```bash
# 1. Cloner le repository
git clone https://github.com/votre-repo/drone-ai-agriculture.git
cd drone-ai-agriculture

# 2. Créer l'environnement virtuel
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou: venv\Scripts\activate  # Windows

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Configuration automatique (télécharge les datasets)
python scripts/setup_environment.py

# 5. Lancer l'API
python -m api.main

# 6. Ouvrir l'interface web
# Ouvrir web/index.html dans votre navigateur
```

L'API sera disponible sur `http://localhost:8000`
Documentation Swagger : `http://localhost:8000/docs`

## 📁 Structure du Projet

```
drone-ai-agriculture/
├── api/                      # API Cloud FastAPI
│   ├── main.py              # Point d'entrée API
│   ├── models.py            # Modèles Pydantic
│   ├── config.py            # Configuration
│   ├── database.py          # Database
│   ├── routes/              # Endpoints API
│   │   ├── auth.py          # Authentification
│   │   ├── analyze.py       # Analyse d'images
│   │   └── history.py       # Historique
│   └── services/            # Services métier
│       ├── ai_service.py    # Service IA
│       ├── storage_service.py
│       └── recommendation_service.py
├── ml/                       # Machine Learning
│   ├── train_model.py       # Script d'entraînement
│   ├── model.py             # Architecture modèle
│   ├── download_datasets.py # Téléchargement datasets
│   ├── data_augmentation.py # Augmentation données
│   └── notebooks/           # Notebooks Jupyter
│       └── training_colab.ipynb
├── drone/                    # Code Raspberry Pi
│   ├── main.py              # Script principal drone
│   ├── camera.py            # Gestion caméra
│   ├── pixhawk.py           # Communication Pixhawk
│   ├── cloud_client.py      # Client API cloud
│   └── offline_queue.py     # File d'attente SQLite
├── web/                      # Interface Web
│   └── index.html           # Application web complète
├── scripts/                  # Scripts utilitaires
│   ├── setup_environment.py # Configuration auto
│   └── deploy.sh            # Déploiement
├── docs/                     # Documentation
│   ├── API.md               # Documentation API
│   ├── TRAINING_GUIDE.md    # Guide entraînement
│   ├── DRONE_SETUP.md       # Configuration drone
│   └── USER_GUIDE.md        # Guide utilisateur
├── tests/                    # Tests unitaires
├── requirements.txt          # Dépendances Python
├── environment.yml           # Environnement Conda
├── docker-compose.yml        # Docker Compose
├── Dockerfile               # Image Docker
└── .env.example             # Variables d'environnement
```

## 🎓 Entraînement du Modèle

### Option 1 : Google Colab (Recommandé - GPU gratuit)

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/votre-repo/drone-ai-agriculture/blob/main/ml/notebooks/training_colab.ipynb)

1. Cliquez sur le badge ci-dessus
2. Exécutez toutes les cellules
3. Le modèle sera téléchargé automatiquement

### Option 2 : Kaggle Notebooks

1. Importez le notebook `ml/notebooks/training_colab.ipynb`
2. Activez le GPU dans les paramètres
3. Exécutez toutes les cellules

### Option 3 : Local

```bash
# Avec GPU NVIDIA (recommandé)
python ml/train_model.py --epochs 50 --batch-size 32 --gpu

# CPU seulement (plus lent)
python ml/train_model.py --epochs 50 --batch-size 16 --cpu
```

## 🌐 Déploiement

### Déploiement Cloud (Render.com)

```bash
# 1. Créer un compte sur render.com
# 2. Connecter votre repository GitHub
# 3. Créer un nouveau Web Service
# 4. Configurer les variables d'environnement (voir .env.example)
```

### Déploiement Docker

```bash
# Build et lancement
docker-compose up -d

# Vérifier les logs
docker-compose logs -f
```

### Configuration Raspberry Pi

Voir le guide détaillé : [docs/DRONE_SETUP.md](docs/DRONE_SETUP.md)

```bash
# Sur le Raspberry Pi
cd drone/
python main.py --api-url https://votre-api.onrender.com
```

## 📡 API Reference

### Endpoints principaux

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | `/api/v1/analyze` | Analyser une image |
| GET | `/api/v1/history` | Historique des analyses |
| GET | `/api/v1/health` | Statut de l'API |
| WS | `/ws/stream` | Streaming temps réel |

### Exemple d'utilisation

```python
import requests

# Analyser une image
with open("image.jpg", "rb") as f:
    response = requests.post(
        "http://localhost:8000/api/v1/analyze",
        files={"image": f},
        headers={"Authorization": "Bearer YOUR_TOKEN"}
    )
    result = response.json()
    print(result)
```

Documentation complète : [docs/API.md](docs/API.md)

## 📊 Métriques de Performance

| Métrique | Objectif | Actuel |
|----------|----------|--------|
| Précision globale | ≥85% | - |
| Détection plante | ≥98% | - |
| Identification espèce | ≥92% | - |
| Stade croissance | ≥88% | - |
| Diagnostic santé | ≥85% | - |
| Latence API | <500ms | - |
| Disponibilité | >99% | - |

## 🔧 Configuration

Copiez `.env.example` vers `.env` et configurez :

```env
# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
SECRET_KEY=your-secret-key-here

# Database
DATABASE_URL=sqlite:///./data/agriculture.db

# AI Model
MODEL_PATH=./models/agriculture_model.h5
CONFIDENCE_THRESHOLD=0.85

# Storage
STORAGE_TYPE=local  # ou s3
S3_BUCKET=your-bucket
AWS_ACCESS_KEY=xxx
AWS_SECRET_KEY=xxx

# Security
JWT_EXPIRATION=3600
RATE_LIMIT=100
```

## 🧪 Tests

```bash
# Lancer tous les tests
pytest tests/ -v

# Avec couverture
pytest tests/ --cov=api --cov=ml --cov-report=html
```

## 🤝 Contribution

1. Fork le projet
2. Créer une branche (`git checkout -b feature/amazing-feature`)
3. Commit les changements (`git commit -m 'Add amazing feature'`)
4. Push sur la branche (`git push origin feature/amazing-feature`)
5. Ouvrir une Pull Request

## 📄 License

Ce projet est sous licence MIT. Voir le fichier [LICENSE](LICENSE) pour plus de détails.

## 📞 Support

- 📧 Email : support@drone-ai-agriculture.com
- 📖 Documentation : [docs/](docs/)
- 🐛 Issues : [GitHub Issues](https://github.com/votre-repo/drone-ai-agriculture/issues)

---

**Développé avec ❤️ pour l'agriculture de demain**