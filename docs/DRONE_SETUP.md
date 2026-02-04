# 🚁 Guide de Configuration du Drone (Raspberry Pi)

Ce guide explique comment configurer un Raspberry Pi pour le système de drone agricole intelligent.

## Matériel Requis

### Composants principaux

| Composant | Spécification | Notes |
|-----------|--------------|-------|
| Raspberry Pi | 4B 4GB+ | 8GB recommandé |
| Caméra | Pi Camera Module 3 | ou HQ Camera |
| Carte SD | 32GB+ Class 10 | A2 recommandé |
| Alimentation | 5V 3A USB-C | Qualité importante |
| Pixhawk | 4/5/6 | Optionnel pour GPS |

### Câblage

```
Raspberry Pi 4
├── GPIO 14 (TX) ──→ Pixhawk TELEM2 RX
├── GPIO 15 (RX) ──→ Pixhawk TELEM2 TX
├── GND ──────────→ Pixhawk GND
└── CSI Port ─────→ Pi Camera
```

---

## Installation du Système

### 1. Préparer la carte SD

```bash
# Télécharger Raspberry Pi OS Lite (64-bit)
# https://www.raspberrypi.com/software/

# Utiliser Raspberry Pi Imager
# Configurer:
# - Hostname: drone-ai-001
# - SSH activé
# - WiFi configuré
# - Username: pi
# - Password: [votre mot de passe]
```

### 2. Premier démarrage

```bash
# Connexion SSH
ssh pi@drone-ai-001.local

# Mise à jour système
sudo apt update && sudo apt upgrade -y

# Installer les dépendances système
sudo apt install -y \
    python3-pip \
    python3-venv \
    python3-opencv \
    libatlas-base-dev \
    libhdf5-dev \
    git \
    sqlite3
```

### 3. Activer la caméra

```bash
# Éditer la configuration
sudo raspi-config

# Naviguer vers:
# Interface Options → Camera → Enable

# Redémarrer
sudo reboot
```

### 4. Configurer le port série (pour Pixhawk)

```bash
# Désactiver le serial console
sudo raspi-config
# Interface Options → Serial Port
# - Login shell: No
# - Serial hardware: Yes

# Ajouter l'utilisateur au groupe dialout
sudo usermod -a -G dialout pi

# Redémarrer
sudo reboot
```

---

## Installation du Logiciel Drone

### 1. Cloner le repository

```bash
cd /home/pi
git clone https://github.com/votre-repo/drone-ai-agriculture.git
cd drone-ai-agriculture
```

### 2. Créer l'environnement virtuel

```bash
python3 -m venv venv
source venv/bin/activate

# Installer les dépendances (version allégée pour Pi)
pip install --upgrade pip
pip install -r requirements-pi.txt
```

### 3. Créer le fichier requirements-pi.txt

```bash
cat > requirements-pi.txt << 'EOF'
# Core
requests>=2.31.0
httpx>=0.25.0

# Camera
picamera2>=0.3.12

# Pixhawk
pymavlink>=2.4.40

# Database
aiosqlite>=0.19.0

# Utilities
python-dotenv>=1.0.0
Pillow>=10.0.0
numpy>=1.24.0
EOF
```

### 4. Configuration

```bash
# Copier le fichier de configuration
cp .env.example .env

# Éditer la configuration
nano .env
```

Contenu de `.env`:
```env
# API Cloud
API_URL=https://votre-api.onrender.com
API_KEY=votre-api-key-ici

# Drone
DRONE_ID=drone-001
FIELD_ID=field-A1

# Capture
CAPTURE_INTERVAL=5.0

# Pixhawk
PIXHAWK_PORT=/dev/ttyAMA0
PIXHAWK_BAUD=57600

# Queue
OFFLINE_QUEUE_PATH=/var/lib/drone-ai/queue.db
MAX_QUEUE_SIZE=1000
```

### 5. Créer les répertoires

```bash
sudo mkdir -p /var/lib/drone-ai
sudo mkdir -p /var/log/drone-ai
sudo chown -R pi:pi /var/lib/drone-ai
sudo chown -R pi:pi /var/log/drone-ai
```

---

## Lancement du Drone

### Mode manuel

```bash
cd /home/pi/drone-ai-agriculture
source venv/bin/activate

# Lancer avec les options
python drone/main.py \
    --api-url https://votre-api.onrender.com \
    --api-key votre-api-key \
    --drone-id drone-001 \
    --interval 5
```

### Mode simulation (sans hardware)

```bash
python drone/main.py --simulate
```

### Service systemd (démarrage automatique)

```bash
# Créer le fichier service
sudo nano /etc/systemd/system/drone-ai.service
```

Contenu:
```ini
[Unit]
Description=Drone AI Agriculture Service
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/drone-ai-agriculture
Environment=PATH=/home/pi/drone-ai-agriculture/venv/bin
EnvironmentFile=/home/pi/drone-ai-agriculture/.env
ExecStart=/home/pi/drone-ai-agriculture/venv/bin/python drone/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Activer et démarrer le service
sudo systemctl daemon-reload
sudo systemctl enable drone-ai
sudo systemctl start drone-ai

# Vérifier le statut
sudo systemctl status drone-ai

# Voir les logs
sudo journalctl -u drone-ai -f
```

---

## Configuration Pixhawk

### Paramètres recommandés

Dans QGroundControl ou Mission Planner:

```
# Port série
SERIAL2_PROTOCOL = 2 (MAVLink 2)
SERIAL2_BAUD = 57600

# Telemetry rate
SR2_POSITION = 4
SR2_EXTRA1 = 4
SR2_EXTRA2 = 4
SR2_RAW_SENS = 2
```

### Vérifier la connexion

```bash
# Test de connexion MAVLink
python -c "
from pymavlink import mavutil
conn = mavutil.mavlink_connection('/dev/ttyAMA0', baud=57600)
msg = conn.wait_heartbeat(timeout=10)
if msg:
    print(f'Connected to system {conn.target_system}')
else:
    print('No heartbeat received')
"
```

---

## Test de la Caméra

### Test basique

```bash
# Capturer une image test
python -c "
from picamera2 import Picamera2
import time

cam = Picamera2()
cam.configure(cam.create_still_configuration())
cam.start()
time.sleep(2)
cam.capture_file('/tmp/test.jpg')
cam.close()
print('Image saved to /tmp/test.jpg')
"
```

### Vérifier la qualité

```bash
# Afficher les infos de l'image
python -c "
from PIL import Image
img = Image.open('/tmp/test.jpg')
print(f'Size: {img.size}')
print(f'Mode: {img.mode}')
print(f'Format: {img.format}')
"
```

---

## Monitoring

### Dashboard système

```bash
# Installer htop
sudo apt install htop

# Monitorer le système
htop
```

### Logs en temps réel

```bash
# Logs du service
sudo journalctl -u drone-ai -f

# Logs applicatifs
tail -f /var/log/drone-ai/drone.log
```

### Statistiques de la queue

```bash
# Vérifier la queue offline
python -c "
import sqlite3
conn = sqlite3.connect('/var/lib/drone-ai/queue.db')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM queue')
print(f'Images en queue: {cursor.fetchone()[0]}')
conn.close()
"
```

---

## Optimisations

### Performance

```bash
# Désactiver le swap (préserve la SD)
sudo dphys-swapfile swapoff
sudo systemctl disable dphys-swapfile

# Réduire les logs
sudo nano /etc/rsyslog.conf
# Commenter les lignes inutiles

# Overclock léger (optionnel)
sudo nano /boot/config.txt
# arm_freq=1800
# over_voltage=2
```

### Économie d'énergie

```bash
# Désactiver le WiFi si ethernet utilisé
sudo rfkill block wifi

# Désactiver le Bluetooth si non utilisé
sudo rfkill block bluetooth

# Désactiver HDMI
/usr/bin/tvservice -o
```

---

## Troubleshooting

### La caméra ne fonctionne pas

```bash
# Vérifier la détection
vcgencmd get_camera
# Devrait afficher: supported=1 detected=1

# Vérifier le câble nappe
# Le côté bleu vers le port Ethernet
```

### Pas de connexion Pixhawk

```bash
# Vérifier le port série
ls -la /dev/ttyAMA0

# Tester avec minicom
sudo apt install minicom
minicom -D /dev/ttyAMA0 -b 57600
```

### Queue pleine

```bash
# Vider la queue manuellement
python -c "
import sqlite3
conn = sqlite3.connect('/var/lib/drone-ai/queue.db')
conn.execute('DELETE FROM queue')
conn.commit()
print('Queue cleared')
"
```

### Problèmes réseau

```bash
# Tester la connexion API
curl -I https://votre-api.onrender.com/health

# Vérifier DNS
nslookup votre-api.onrender.com

# Tester avec ping
ping -c 3 8.8.8.8
```

---

## Maintenance

### Sauvegarde

```bash
# Sauvegarder la configuration
tar -czvf drone-backup.tar.gz \
    /home/pi/drone-ai-agriculture/.env \
    /var/lib/drone-ai/queue.db

# Copier vers PC
scp pi@drone-ai-001.local:drone-backup.tar.gz .
```

### Mise à jour

```bash
cd /home/pi/drone-ai-agriculture
git pull origin main
source venv/bin/activate
pip install -r requirements-pi.txt --upgrade
sudo systemctl restart drone-ai
```

### Nettoyage

```bash
# Nettoyer les logs anciens
sudo journalctl --vacuum-time=7d

# Nettoyer le cache pip
pip cache purge
```