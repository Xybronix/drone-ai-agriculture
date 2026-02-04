#!/usr/bin/env python3
"""
🔧 Script de Configuration Automatique - Drone AI Agriculture

Ce script configure automatiquement l'environnement de développement/production
en détectant le système et en installant les dépendances nécessaires.
"""

import os
import sys
import subprocess
import platform
import shutil
import json
import secrets
from pathlib import Path
from typing import Optional, Dict, Any

# Couleurs pour le terminal
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_header(text: str):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(60)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")

def print_step(text: str):
    print(f"{Colors.CYAN}→ {text}{Colors.ENDC}")

def print_success(text: str):
    print(f"{Colors.GREEN}✓ {text}{Colors.ENDC}")

def print_warning(text: str):
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")

def print_error(text: str):
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")

def run_command(cmd: list, check: bool = True, capture: bool = False) -> Optional[str]:
    """Exécute une commande système."""
    try:
        result = subprocess.run(
            cmd,
            check=check,
            capture_output=capture,
            text=True
        )
        if capture:
            return result.stdout.strip()
        return None
    except subprocess.CalledProcessError as e:
        if capture:
            return None
        raise e

def detect_environment() -> Dict[str, Any]:
    """Détecte l'environnement d'exécution."""
    env = {
        "os": platform.system(),
        "os_version": platform.version(),
        "python_version": platform.python_version(),
        "architecture": platform.machine(),
        "is_raspberry_pi": False,
        "is_colab": False,
        "is_kaggle": False,
        "is_docker": False,
        "has_gpu": False,
        "gpu_type": None,
    }
    
    # Détecter Raspberry Pi
    if os.path.exists("/proc/cpuinfo"):
        with open("/proc/cpuinfo", "r") as f:
            cpuinfo = f.read()
            if "Raspberry Pi" in cpuinfo or "BCM" in cpuinfo:
                env["is_raspberry_pi"] = True
    
    # Détecter Google Colab
    if "COLAB_GPU" in os.environ or os.path.exists("/content"):
        env["is_colab"] = True
    
    # Détecter Kaggle
    if "KAGGLE_KERNEL_RUN_TYPE" in os.environ or os.path.exists("/kaggle"):
        env["is_kaggle"] = True
    
    # Détecter Docker
    if os.path.exists("/.dockerenv"):
        env["is_docker"] = True
    
    # Détecter GPU NVIDIA
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, check=True
        )
        if result.stdout.strip():
            env["has_gpu"] = True
            env["gpu_type"] = "nvidia"
            env["gpu_name"] = result.stdout.strip().split("\n")[0]
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    return env

def check_python_version():
    """Vérifie la version de Python."""
    print_step("Vérification de la version Python...")
    
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print_error(f"Python 3.8+ requis. Version actuelle: {version.major}.{version.minor}")
        sys.exit(1)
    
    print_success(f"Python {version.major}.{version.minor}.{version.micro}")

def install_system_dependencies(env: Dict[str, Any]):
    """Installe les dépendances système."""
    print_step("Installation des dépendances système...")
    
    if env["os"] == "Linux":
        if env["is_raspberry_pi"]:
            packages = [
                "python3-pip", "python3-venv", "python3-opencv",
                "libatlas-base-dev", "libhdf5-dev", "git", "sqlite3"
            ]
        else:
            packages = [
                "python3-pip", "python3-venv", "libgl1-mesa-glx",
                "libglib2.0-0", "git", "sqlite3"
            ]
        
        try:
            run_command(["sudo", "apt-get", "update"], check=False)
            run_command(["sudo", "apt-get", "install", "-y"] + packages, check=False)
            print_success("Dépendances système installées")
        except Exception as e:
            print_warning(f"Installation partielle: {e}")
    
    elif env["os"] == "Darwin":  # macOS
        try:
            run_command(["brew", "install", "sqlite3"], check=False)
            print_success("Dépendances macOS installées")
        except FileNotFoundError:
            print_warning("Homebrew non trouvé, installation manuelle requise")
    
    elif env["os"] == "Windows":
        print_warning("Sur Windows, installez manuellement: Git, SQLite3")

def create_virtual_environment(project_root: Path, env: Dict[str, Any]):
    """Crée l'environnement virtuel Python."""
    print_step("Création de l'environnement virtuel...")
    
    venv_path = project_root / "venv"
    
    if venv_path.exists():
        print_warning("Environnement virtuel existant trouvé")
        response = input("Recréer l'environnement? [y/N]: ").strip().lower()
        if response == "y":
            shutil.rmtree(venv_path)
        else:
            print_success("Utilisation de l'environnement existant")
            return
    
    run_command([sys.executable, "-m", "venv", str(venv_path)])
    print_success(f"Environnement virtuel créé: {venv_path}")

def get_pip_path(project_root: Path, env: Dict[str, Any]) -> str:
    """Retourne le chemin vers pip dans l'environnement virtuel."""
    if env["os"] == "Windows":
        return str(project_root / "venv" / "Scripts" / "pip")
    return str(project_root / "venv" / "bin" / "pip")

def get_python_path(project_root: Path, env: Dict[str, Any]) -> str:
    """Retourne le chemin vers Python dans l'environnement virtuel."""
    if env["os"] == "Windows":
        return str(project_root / "venv" / "Scripts" / "python")
    return str(project_root / "venv" / "bin" / "python")

def install_python_dependencies(project_root: Path, env: Dict[str, Any], mode: str = "full"):
    """Installe les dépendances Python."""
    print_step(f"Installation des dépendances Python (mode: {mode})...")
    
    pip = get_pip_path(project_root, env)
    
    # Mise à jour de pip
    run_command([pip, "install", "--upgrade", "pip"])
    
    # Sélection du fichier requirements
    if mode == "pi" or env["is_raspberry_pi"]:
        req_file = project_root / "requirements-pi.txt"
        if not req_file.exists():
            # Créer requirements-pi.txt
            create_pi_requirements(project_root)
    elif mode == "ml" or env["is_colab"] or env["is_kaggle"]:
        req_file = project_root / "requirements-ml.txt"
        if not req_file.exists():
            create_ml_requirements(project_root)
    else:
        req_file = project_root / "requirements.txt"
    
    if not req_file.exists():
        print_error(f"Fichier {req_file} non trouvé!")
        return
    
    # Installer les dépendances
    try:
        run_command([pip, "install", "-r", str(req_file)])
        print_success(f"Dépendances installées depuis {req_file.name}")
    except subprocess.CalledProcessError as e:
        print_error(f"Erreur lors de l'installation: {e}")
    
    # Installer TensorFlow avec GPU si disponible
    if env["has_gpu"] and env["gpu_type"] == "nvidia":
        print_step("Installation de TensorFlow avec support GPU...")
        try:
            run_command([pip, "install", "tensorflow[and-cuda]"])
            print_success("TensorFlow GPU installé")
        except subprocess.CalledProcessError:
            print_warning("Installation TensorFlow GPU échouée, utilisation CPU")

def create_pi_requirements(project_root: Path):
    """Crée le fichier requirements pour Raspberry Pi."""
    content = """# Requirements pour Raspberry Pi
requests>=2.31.0
httpx>=0.25.0
picamera2>=0.3.12
pymavlink>=2.4.40
aiosqlite>=0.19.0
python-dotenv>=1.0.0
Pillow>=10.0.0
numpy>=1.24.0
"""
    (project_root / "requirements-pi.txt").write_text(content)
    print_success("Créé: requirements-pi.txt")

def create_ml_requirements(project_root: Path):
    """Crée le fichier requirements pour ML/Training."""
    content = """# Requirements pour entraînement ML
tensorflow>=2.15.0
numpy>=1.24.0
Pillow>=10.0.0
albumentations>=1.3.0
matplotlib>=3.7.0
scikit-learn>=1.3.0
pandas>=2.0.0
tqdm>=4.65.0
kaggle>=1.5.16
tf2onnx>=1.15.0
tensorboard>=2.15.0
python-dotenv>=1.0.0
"""
    (project_root / "requirements-ml.txt").write_text(content)
    print_success("Créé: requirements-ml.txt")

def setup_environment_file(project_root: Path, env: Dict[str, Any]):
    """Configure le fichier .env."""
    print_step("Configuration du fichier .env...")
    
    env_file = project_root / ".env"
    example_file = project_root / ".env.example"
    
    if env_file.exists():
        print_warning("Fichier .env existant trouvé")
        response = input("Écraser le fichier .env? [y/N]: ").strip().lower()
        if response != "y":
            print_success("Conservation du fichier .env existant")
            return
    
    # Lire le template
    if example_file.exists():
        template = example_file.read_text()
    else:
        template = """# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=false

# Security
SECRET_KEY={secret_key}
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_DAYS=30

# Database
DATABASE_URL=sqlite+aiosqlite:///./data/agriculture.db

# Storage
STORAGE_TYPE=local
UPLOADS_DIR=./uploads

# Model
MODEL_PATH=./models/agriculture_model.h5
USE_MOCK_MODEL=true

# Drone (optionnel)
DRONE_ID=drone-001
FIELD_ID=field-A1
CAPTURE_INTERVAL=5.0
"""
    
    # Générer une clé secrète
    secret_key = secrets.token_urlsafe(32)
    content = template.replace("{secret_key}", secret_key)
    
    # Remplacer les placeholders
    if "your-secret-key-change-me-in-production" in content:
        content = content.replace(
            "your-secret-key-change-me-in-production",
            secret_key
        )
    
    env_file.write_text(content)
    print_success(f"Fichier .env créé avec une nouvelle clé secrète")

def create_directories(project_root: Path):
    """Crée les répertoires nécessaires."""
    print_step("Création des répertoires...")
    
    directories = [
        "data",
        "data/datasets",
        "logs",
        "models",
        "uploads",
        "uploads/thumbnails",
        "output",
        "output/models",
        "output/logs",
    ]
    
    for dir_name in directories:
        dir_path = project_root / dir_name
        dir_path.mkdir(parents=True, exist_ok=True)
    
    # Créer les fichiers .gitkeep
    for dir_name in directories:
        gitkeep = project_root / dir_name / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()
    
    print_success(f"Créé {len(directories)} répertoires")

def setup_database(project_root: Path, env: Dict[str, Any]):
    """Initialise la base de données."""
    print_step("Initialisation de la base de données...")
    
    python = get_python_path(project_root, env)
    
    # Script d'initialisation
    init_script = """
import sys
sys.path.insert(0, '.')
import asyncio
from api.database import init_db, create_default_users

async def main():
    await init_db()
    await create_default_users()
    print("Base de données initialisée")

asyncio.run(main())
"""
    
    init_file = project_root / "init_db_temp.py"
    init_file.write_text(init_script)
    
    try:
        result = subprocess.run(
            [python, str(init_file)],
            cwd=str(project_root),
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print_success("Base de données initialisée")
        else:
            print_warning(f"Initialisation partielle: {result.stderr}")
    except Exception as e:
        print_warning(f"Initialisation DB reportée: {e}")
    finally:
        if init_file.exists():
            init_file.unlink()

def verify_installation(project_root: Path, env: Dict[str, Any]):
    """Vérifie l'installation."""
    print_step("Vérification de l'installation...")
    
    python = get_python_path(project_root, env)
    
    checks = {
        "FastAPI": "import fastapi; print(fastapi.__version__)",
        "TensorFlow": "import tensorflow as tf; print(tf.__version__)",
        "Pillow": "from PIL import Image; print('OK')",
        "NumPy": "import numpy; print(numpy.__version__)",
    }
    
    results = {}
    for name, cmd in checks.items():
        try:
            result = subprocess.run(
                [python, "-c", cmd],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                results[name] = ("✓", result.stdout.strip())
            else:
                results[name] = ("✗", "Non installé")
        except Exception:
            results[name] = ("✗", "Erreur")
    
    print("\nRésumé des dépendances:")
    print("-" * 40)
    for name, (status, version) in results.items():
        if status == "✓":
            print(f"  {Colors.GREEN}{status}{Colors.ENDC} {name}: {version}")
        else:
            print(f"  {Colors.FAIL}{status}{Colors.ENDC} {name}: {version}")
    print("-" * 40)

def print_next_steps(project_root: Path, env: Dict[str, Any]):
    """Affiche les prochaines étapes."""
    print_header("Configuration Terminée!")
    
    if env["os"] == "Windows":
        activate = "venv\\Scripts\\activate"
    else:
        activate = "source venv/bin/activate"
    
    print(f"""
{Colors.GREEN}Prochaines étapes:{Colors.ENDC}

1. Activer l'environnement virtuel:
   {Colors.CYAN}cd {project_root}{Colors.ENDC}
   {Colors.CYAN}{activate}{Colors.ENDC}

2. Lancer l'API en mode développement:
   {Colors.CYAN}python -m api.main{Colors.ENDC}

3. Accéder à l'interface web:
   {Colors.CYAN}http://localhost:8000/web/index.html{Colors.ENDC}

4. Documentation API:
   {Colors.CYAN}http://localhost:8000/docs{Colors.ENDC}

{Colors.BLUE}Pour l'entraînement du modèle:{Colors.ENDC}
   - Google Colab: Ouvrir ml/notebooks/training_colab.ipynb
   - Local: python ml/train_model.py --help

{Colors.BLUE}Pour le drone Raspberry Pi:{Colors.ENDC}
   - Voir docs/DRONE_SETUP.md

{Colors.WARNING}Note: Le modèle IA utilise actuellement le mode simulation.
Pour utiliser un vrai modèle, entraînez-le ou téléchargez-en un.{Colors.ENDC}
""")

def main():
    """Point d'entrée principal."""
    print_header("🌱 Drone AI Agriculture - Configuration")
    
    # Déterminer le répertoire du projet
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent
    
    print(f"Répertoire du projet: {project_root}")
    
    # Détecter l'environnement
    print_step("Détection de l'environnement...")
    env = detect_environment()
    
    print(f"""
  OS: {env['os']} ({env['architecture']})
  Python: {env['python_version']}
  Raspberry Pi: {'Oui' if env['is_raspberry_pi'] else 'Non'}
  Google Colab: {'Oui' if env['is_colab'] else 'Non'}
  Kaggle: {'Oui' if env['is_kaggle'] else 'Non'}
  Docker: {'Oui' if env['is_docker'] else 'Non'}
  GPU: {'Oui (' + env.get('gpu_name', 'N/A') + ')' if env['has_gpu'] else 'Non'}
""")
    
    # Vérifier Python
    check_python_version()
    
    # Demander le mode d'installation
    print(f"""
{Colors.BLUE}Modes d'installation disponibles:{Colors.ENDC}
  1. full    - Installation complète (API + ML + Web)
  2. api     - API uniquement
  3. ml      - Entraînement ML uniquement
  4. pi      - Drone Raspberry Pi
""")
    
    mode = input("Choisir le mode [1/2/3/4] (défaut: 1): ").strip()
    mode_map = {"1": "full", "2": "api", "3": "ml", "4": "pi", "": "full"}
    mode = mode_map.get(mode, "full")
    
    print(f"\nMode sélectionné: {mode}")
    
    # Exécuter les étapes
    try:
        if not env["is_colab"] and not env["is_kaggle"]:
            install_system_dependencies(env)
            create_virtual_environment(project_root, env)
        
        install_python_dependencies(project_root, env, mode)
        create_directories(project_root)
        setup_environment_file(project_root, env)
        
        if mode in ["full", "api"]:
            setup_database(project_root, env)
        
        verify_installation(project_root, env)
        print_next_steps(project_root, env)
        
    except KeyboardInterrupt:
        print("\n\nInstallation annulée par l'utilisateur.")
        sys.exit(1)
    except Exception as e:
        print_error(f"Erreur: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()