#!/bin/bash
# ========================================================
# 🚀 Script de Déploiement - Drone AI Agriculture
# ========================================================
# 
# Usage:
#   ./scripts/deploy.sh [OPTION]
#
# Options:
#   local       Déploiement local pour développement
#   docker      Déploiement avec Docker Compose
#   production  Déploiement production (avec SSL)
#   pi          Déploiement sur Raspberry Pi
#   update      Mise à jour du déploiement existant
#   stop        Arrêter les services
#   logs        Afficher les logs
#   status      Vérifier le statut des services
#   clean       Nettoyer les fichiers temporaires
#
# ========================================================

set -e

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.yml"
ENV_FILE="$PROJECT_ROOT/.env"

# Fonctions utilitaires
print_header() {
    echo -e "\n${CYAN}============================================${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}============================================${NC}\n"
}

print_step() {
    echo -e "${BLUE}→ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

check_requirements() {
    print_step "Vérification des prérequis..."
    
    local missing=()
    
    if ! command -v python3 &> /dev/null; then
        missing+=("python3")
    fi
    
    if ! command -v pip3 &> /dev/null; then
        missing+=("pip3")
    fi
    
    if [ ${#missing[@]} -ne 0 ]; then
        print_error "Dépendances manquantes: ${missing[*]}"
        exit 1
    fi
    
    print_success "Prérequis OK"
}

check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker n'est pas installé"
        echo "Installez Docker: https://docs.docker.com/get-docker/"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        print_error "Docker Compose n'est pas installé"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        print_error "Docker n'est pas en cours d'exécution"
        exit 1
    fi
    
    print_success "Docker OK"
}

setup_env() {
    print_step "Configuration de l'environnement..."
    
    if [ ! -f "$ENV_FILE" ]; then
        if [ -f "$PROJECT_ROOT/.env.example" ]; then
            cp "$PROJECT_ROOT/.env.example" "$ENV_FILE"
            
            # Générer une clé secrète
            SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
            if [[ "$OSTYPE" == "darwin"* ]]; then
                sed -i '' "s/your-secret-key-change-me-in-production/$SECRET_KEY/" "$ENV_FILE"
            else
                sed -i "s/your-secret-key-change-me-in-production/$SECRET_KEY/" "$ENV_FILE"
            fi
            
            print_success "Fichier .env créé avec une nouvelle clé secrète"
        else
            print_error "Fichier .env.example non trouvé"
            exit 1
        fi
    else
        print_success "Fichier .env existant"
    fi
}

create_directories() {
    print_step "Création des répertoires..."
    
    mkdir -p "$PROJECT_ROOT/data"
    mkdir -p "$PROJECT_ROOT/logs"
    mkdir -p "$PROJECT_ROOT/models"
    mkdir -p "$PROJECT_ROOT/uploads/thumbnails"
    mkdir -p "$PROJECT_ROOT/output/models"
    mkdir -p "$PROJECT_ROOT/output/logs"
    
    print_success "Répertoires créés"
}

# ========================================================
# Déploiement Local
# ========================================================
deploy_local() {
    print_header "Déploiement Local"
    
    check_requirements
    setup_env
    create_directories
    
    cd "$PROJECT_ROOT"
    
    # Créer environnement virtuel si nécessaire
    if [ ! -d "venv" ]; then
        print_step "Création de l'environnement virtuel..."
        python3 -m venv venv
        print_success "Environnement virtuel créé"
    fi
    
    # Activer et installer les dépendances
    print_step "Installation des dépendances..."
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    print_success "Dépendances installées"
    
    # Initialiser la base de données
    print_step "Initialisation de la base de données..."
    python -c "
import asyncio
import sys
sys.path.insert(0, '.')
from api.database import init_db, create_default_users
async def main():
    await init_db()
    await create_default_users()
asyncio.run(main())
"
    print_success "Base de données initialisée"
    
    # Lancer l'API
    print_header "Démarrage de l'API"
    echo -e "${GREEN}API disponible sur: http://localhost:8000${NC}"
    echo -e "${GREEN}Interface Web: http://localhost:8000/web/index.html${NC}"
    echo -e "${GREEN}Documentation: http://localhost:8000/docs${NC}"
    echo ""
    echo -e "${YELLOW}Appuyez sur Ctrl+C pour arrêter${NC}"
    echo ""
    
    python -m api.main
}

# ========================================================
# Déploiement Docker
# ========================================================
deploy_docker() {
    print_header "Déploiement Docker"
    
    check_docker
    setup_env
    create_directories
    
    cd "$PROJECT_ROOT"
    
    print_step "Construction des images Docker..."
    
    # Utiliser docker compose v2 ou docker-compose v1
    if docker compose version &> /dev/null; then
        DOCKER_COMPOSE="docker compose"
    else
        DOCKER_COMPOSE="docker-compose"
    fi
    
    $DOCKER_COMPOSE build
    print_success "Images construites"
    
    print_step "Démarrage des conteneurs..."
    $DOCKER_COMPOSE up -d
    print_success "Conteneurs démarrés"
    
    # Attendre que l'API soit prête
    print_step "Attente du démarrage de l'API..."
    sleep 5
    
    for i in {1..30}; do
        if curl -s http://localhost:8000/health > /dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        print_success "API prête"
    else
        print_warning "L'API met du temps à démarrer, vérifiez les logs"
    fi
    
    print_header "Déploiement Terminé"
    echo -e "${GREEN}Services disponibles:${NC}"
    echo "  - API: http://localhost:8000"
    echo "  - Web: http://localhost:8000/web/index.html"
    echo "  - Docs: http://localhost:8000/docs"
    echo "  - Prometheus: http://localhost:9090"
    echo "  - Grafana: http://localhost:3000 (admin/admin)"
    echo ""
    echo -e "${BLUE}Commandes utiles:${NC}"
    echo "  - Logs: $0 logs"
    echo "  - Status: $0 status"
    echo "  - Stop: $0 stop"
}

# ========================================================
# Déploiement Production
# ========================================================
deploy_production() {
    print_header "Déploiement Production"
    
    check_docker
    
    # Vérifications de sécurité
    print_step "Vérifications de sécurité..."
    
    if [ ! -f "$ENV_FILE" ]; then
        print_error "Fichier .env requis pour la production"
        exit 1
    fi
    
    # Vérifier que DEBUG=false
    if grep -q "DEBUG=true" "$ENV_FILE"; then
        print_warning "DEBUG=true détecté, passage à DEBUG=false"
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' 's/DEBUG=true/DEBUG=false/' "$ENV_FILE"
        else
            sed -i 's/DEBUG=true/DEBUG=false/' "$ENV_FILE"
        fi
    fi
    
    # Vérifier la clé secrète
    if grep -q "your-secret-key-change-me" "$ENV_FILE"; then
        print_error "Changez la SECRET_KEY dans .env!"
        exit 1
    fi
    
    print_success "Vérifications OK"
    
    cd "$PROJECT_ROOT"
    
    # Construction en mode production
    print_step "Construction des images (production)..."
    
    if docker compose version &> /dev/null; then
        DOCKER_COMPOSE="docker compose"
    else
        DOCKER_COMPOSE="docker-compose"
    fi
    
    $DOCKER_COMPOSE -f docker-compose.yml build --no-cache
    print_success "Images construites"
    
    # Backup de la base de données existante
    if [ -f "$PROJECT_ROOT/data/agriculture.db" ]; then
        print_step "Backup de la base de données..."
        cp "$PROJECT_ROOT/data/agriculture.db" "$PROJECT_ROOT/data/agriculture.db.backup.$(date +%Y%m%d_%H%M%S)"
        print_success "Backup créé"
    fi
    
    # Déploiement
    print_step "Déploiement..."
    $DOCKER_COMPOSE up -d
    print_success "Services déployés"
    
    print_header "Production Déployée"
    echo -e "${GREEN}L'API est en cours de démarrage...${NC}"
    echo ""
    echo -e "${YELLOW}Prochaines étapes recommandées:${NC}"
    echo "  1. Configurer un reverse proxy (nginx) avec SSL"
    echo "  2. Configurer les backups automatiques"
    echo "  3. Configurer la surveillance (Prometheus/Grafana)"
    echo "  4. Configurer les alertes"
}

# ========================================================
# Déploiement Raspberry Pi
# ========================================================
deploy_pi() {
    print_header "Déploiement Raspberry Pi"
    
    # Vérifier si on est sur un Pi
    if [ ! -f /proc/cpuinfo ] || ! grep -q "Raspberry Pi\|BCM" /proc/cpuinfo 2>/dev/null; then
        print_warning "Ce script est conçu pour Raspberry Pi"
        read -p "Continuer quand même? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
    
    check_requirements
    setup_env
    
    cd "$PROJECT_ROOT"
    
    # Installer les dépendances système
    print_step "Installation des dépendances système..."
    sudo apt-get update
    sudo apt-get install -y \
        python3-pip \
        python3-venv \
        python3-opencv \
        libatlas-base-dev \
        libhdf5-dev \
        git \
        sqlite3
    print_success "Dépendances système installées"
    
    # Créer environnement virtuel
    if [ ! -d "venv" ]; then
        print_step "Création de l'environnement virtuel..."
        python3 -m venv venv
    fi
    
    # Installer les dépendances Python
    print_step "Installation des dépendances Python..."
    source venv/bin/activate
    pip install --upgrade pip
    
    # Utiliser requirements-pi.txt si disponible
    if [ -f "requirements-pi.txt" ]; then
        pip install -r requirements-pi.txt
    else
        # Créer requirements-pi.txt
        cat > requirements-pi.txt << 'EOF'
requests>=2.31.0
httpx>=0.25.0
picamera2>=0.3.12
pymavlink>=2.4.40
aiosqlite>=0.19.0
python-dotenv>=1.0.0
Pillow>=10.0.0
numpy>=1.24.0
EOF
        pip install -r requirements-pi.txt
    fi
    print_success "Dépendances installées"
    
    # Créer les répertoires
    print_step "Configuration des répertoires..."
    sudo mkdir -p /var/lib/drone-ai
    sudo mkdir -p /var/log/drone-ai
    sudo chown -R $USER:$USER /var/lib/drone-ai
    sudo chown -R $USER:$USER /var/log/drone-ai
    print_success "Répertoires créés"
    
    # Créer le service systemd
    print_step "Configuration du service systemd..."
    
    cat > /tmp/drone-ai.service << EOF
[Unit]
Description=Drone AI Agriculture Service
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_ROOT
Environment=PATH=$PROJECT_ROOT/venv/bin
EnvironmentFile=$ENV_FILE
ExecStart=$PROJECT_ROOT/venv/bin/python drone/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    sudo mv /tmp/drone-ai.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable drone-ai
    
    print_success "Service configuré"
    
    print_header "Déploiement Pi Terminé"
    echo -e "${GREEN}Commandes disponibles:${NC}"
    echo "  - Démarrer: sudo systemctl start drone-ai"
    echo "  - Arrêter: sudo systemctl stop drone-ai"
    echo "  - Status: sudo systemctl status drone-ai"
    echo "  - Logs: sudo journalctl -u drone-ai -f"
    echo ""
    echo -e "${YELLOW}Configuration requise:${NC}"
    echo "  1. Éditez .env pour configurer l'URL de l'API cloud"
    echo "  2. Activez la caméra: sudo raspi-config"
    echo "  3. Redémarrez le Pi si nécessaire"
}

# ========================================================
# Mise à jour
# ========================================================
deploy_update() {
    print_header "Mise à jour du Déploiement"
    
    cd "$PROJECT_ROOT"
    
    # Backup
    print_step "Création d'un backup..."
    if [ -f "data/agriculture.db" ]; then
        cp data/agriculture.db "data/agriculture.db.backup.$(date +%Y%m%d_%H%M%S)"
        print_success "Backup créé"
    fi
    
    # Pull des dernières modifications
    print_step "Récupération des mises à jour..."
    if [ -d ".git" ]; then
        git pull origin main || git pull origin master
        print_success "Code mis à jour"
    else
        print_warning "Pas de repository Git, mise à jour manuelle requise"
    fi
    
    # Mise à jour des dépendances
    if [ -f "docker-compose.yml" ]; then
        print_step "Mise à jour Docker..."
        check_docker
        
        if docker compose version &> /dev/null; then
            DOCKER_COMPOSE="docker compose"
        else
            DOCKER_COMPOSE="docker-compose"
        fi
        
        $DOCKER_COMPOSE pull
        $DOCKER_COMPOSE build --no-cache
        $DOCKER_COMPOSE up -d
        print_success "Conteneurs mis à jour"
    elif [ -d "venv" ]; then
        print_step "Mise à jour des dépendances Python..."
        source venv/bin/activate
        pip install --upgrade pip
        pip install -r requirements.txt --upgrade
        print_success "Dépendances mises à jour"
    fi
    
    print_success "Mise à jour terminée"
}

# ========================================================
# Arrêt des services
# ========================================================
stop_services() {
    print_header "Arrêt des Services"
    
    cd "$PROJECT_ROOT"
    
    if [ -f "docker-compose.yml" ]; then
        if docker compose version &> /dev/null; then
            DOCKER_COMPOSE="docker compose"
        else
            DOCKER_COMPOSE="docker-compose"
        fi
        
        print_step "Arrêt des conteneurs Docker..."
        $DOCKER_COMPOSE down
        print_success "Conteneurs arrêtés"
    fi
    
    # Arrêter le service systemd si présent
    if systemctl is-active --quiet drone-ai 2>/dev/null; then
        print_step "Arrêt du service drone-ai..."
        sudo systemctl stop drone-ai
        print_success "Service arrêté"
    fi
    
    print_success "Tous les services sont arrêtés"
}

# ========================================================
# Afficher les logs
# ========================================================
show_logs() {
    print_header "Logs des Services"
    
    cd "$PROJECT_ROOT"
    
    if [ -f "docker-compose.yml" ]; then
        if docker compose version &> /dev/null; then
            DOCKER_COMPOSE="docker compose"
        else
            DOCKER_COMPOSE="docker-compose"
        fi
        
        $DOCKER_COMPOSE logs -f
    elif systemctl is-active --quiet drone-ai 2>/dev/null; then
        sudo journalctl -u drone-ai -f
    else
        if [ -f "logs/api.log" ]; then
            tail -f logs/api.log
        else
            print_warning "Aucun log trouvé"
        fi
    fi
}

# ========================================================
# Statut des services
# ========================================================
show_status() {
    print_header "Statut des Services"
    
    cd "$PROJECT_ROOT"
    
    # Docker
    if [ -f "docker-compose.yml" ]; then
        echo -e "${BLUE}Conteneurs Docker:${NC}"
        if docker compose version &> /dev/null; then
            docker compose ps
        else
            docker-compose ps
        fi
        echo ""
    fi
    
    # Service systemd
    if systemctl list-unit-files | grep -q drone-ai; then
        echo -e "${BLUE}Service Drone AI:${NC}"
        systemctl status drone-ai --no-pager || true
        echo ""
    fi
    
    # API Health
    echo -e "${BLUE}Santé de l'API:${NC}"
    if curl -s http://localhost:8000/health 2>/dev/null; then
        echo ""
    else
        echo -e "${YELLOW}API non accessible sur localhost:8000${NC}"
    fi
}

# ========================================================
# Nettoyage
# ========================================================
clean() {
    print_header "Nettoyage"
    
    cd "$PROJECT_ROOT"
    
    read -p "Cette action va supprimer les fichiers temporaires. Continuer? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi
    
    print_step "Nettoyage des fichiers Python..."
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    find . -type f -name "*.pyo" -delete 2>/dev/null || true
    
    print_step "Nettoyage des fichiers temporaires..."
    rm -rf .pytest_cache 2>/dev/null || true
    rm -rf .mypy_cache 2>/dev/null || true
    rm -rf htmlcov 2>/dev/null || true
    rm -f .coverage 2>/dev/null || true
    
    print_step "Nettoyage des logs anciens..."
    find logs -name "*.log" -mtime +30 -delete 2>/dev/null || true
    
    # Option pour nettoyer Docker
    read -p "Nettoyer également les images Docker non utilisées? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker system prune -f
    fi
    
    print_success "Nettoyage terminé"
}

# ========================================================
# Afficher l'aide
# ========================================================
show_help() {
    echo -e "${CYAN}🌱 Drone AI Agriculture - Script de Déploiement${NC}"
    echo ""
    echo "Usage: $0 [OPTION]"
    echo ""
    echo "Options:"
    echo "  local       Déploiement local pour développement"
    echo "  docker      Déploiement avec Docker Compose"
    echo "  production  Déploiement production (avec SSL)"
    echo "  pi          Déploiement sur Raspberry Pi"
    echo "  update      Mise à jour du déploiement existant"
    echo "  stop        Arrêter les services"
    echo "  logs        Afficher les logs"
    echo "  status      Vérifier le statut des services"
    echo "  clean       Nettoyer les fichiers temporaires"
    echo "  help        Afficher cette aide"
    echo ""
    echo "Exemples:"
    echo "  $0 local      # Lance l'API en mode développement"
    echo "  $0 docker     # Déploie avec Docker Compose"
    echo "  $0 logs       # Affiche les logs en temps réel"
}

# ========================================================
# Point d'entrée
# ========================================================
case "${1:-}" in
    local)
        deploy_local
        ;;
    docker)
        deploy_docker
        ;;
    production)
        deploy_production
        ;;
    pi)
        deploy_pi
        ;;
    update)
        deploy_update
        ;;
    stop)
        stop_services
        ;;
    logs)
        show_logs
        ;;
    status)
        show_status
        ;;
    clean)
        clean
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        if [ -n "${1:-}" ]; then
            print_error "Option inconnue: $1"
            echo ""
        fi
        show_help
        exit 1
        ;;
esac