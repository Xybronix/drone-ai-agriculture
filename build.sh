#!/bin/bash
# Script de build pour Render
# Ce script est optionnel - Render peut builder directement depuis requirements.txt

set -e  # Arrêter en cas d'erreur

echo "🚀 Démarrage du build..."

# Mettre à jour pip
pip install --upgrade pip

# Installer les dépendances
echo "📦 Installation des dépendances..."
pip install -r requirements.txt

# Créer les dossiers nécessaires
echo "📁 Création des dossiers..."
mkdir -p data/uploads
mkdir -p data/cache
mkdir -p logs

echo "✅ Build terminé avec succès!"
