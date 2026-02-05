# 🚀 Guide de Déploiement sur Render

Ce guide vous explique comment déployer le projet **Drone AI Agriculture** sur Render à partir de votre dépôt Git.

## 📋 Prérequis

- Un compte [Render](https://render.com) (gratuit ou payant)
- Votre code source sur GitHub, GitLab ou Bitbucket
- Une clé API Plant.id (optionnelle mais recommandée pour les fonctionnalités complètes)
- **Aucune base de données externe nécessaire** - SQLite est inclus et fonctionne immédiatement

## 🔧 Configuration sur Render

### Option 1 : Déploiement Automatique avec `render.yaml` (Recommandé)

1. **Connecter votre dépôt Git**
   - Connectez-vous à [Render Dashboard](https://dashboard.render.com)
   - Cliquez sur "New +" → "Blueprint"
   - Connectez votre dépôt Git (GitHub/GitLab/Bitbucket)
   - Render détectera automatiquement le fichier `render.yaml`

2. **Configurer les variables d'environnement**
   - Dans le dashboard Render, allez dans votre service
   - Section "Environment"
   - Ajoutez/modifiez les variables suivantes :
     ```
     PLANT_ID_API_KEY=votre_clé_plant_id_ici
     SECRET_KEY=une_clé_secrète_aléatoire_longue
     # CORS_ORIGINS reste à "*" pour accepter l'URL Render
     ```

3. **Déployer**
   - Render va automatiquement :
     - Installer les dépendances Python
     - Builder l'application
     - Démarrer le service
   - Le déploiement prend généralement 10-15 minutes (première fois avec TensorFlow)
   - Les déploiements suivants seront plus rapides (5-10 minutes)

### Option 2 : Déploiement Manuel

1. **Créer un nouveau service Web**
   - Dans Render Dashboard, cliquez sur "New +" → "Web Service"
   - Connectez votre dépôt Git

2. **Configuration du service**
   - **Name** : `drone-ai-agriculture-api` (ou votre nom préféré)
   - **Region** : Choisissez la région la plus proche de vos utilisateurs
   - **Branch** : `main` (ou votre branche principale)
   - **Root Directory** : `/` (racine du projet)
   - **Environment** : `Python 3`
   - **Build Command** : `pip install --upgrade pip && pip install -r requirements.txt && mkdir -p data/uploads data/cache logs`
   - **Start Command** : `python -m uvicorn api.main:app --host 0.0.0.0 --port $PORT --workers 1`

3. **Variables d'environnement**
   Ajoutez les variables suivantes dans la section "Environment" :
   
   ```bash
   # Configuration API
   API_HOST=0.0.0.0
   API_PORT=$PORT
   ENVIRONMENT=production
   DEBUG=false
   
   # Sécurité
   SECRET_KEY=<générer_une_clé_secrète_aléatoire>
   JWT_ALGORITHM=HS256
   JWT_EXPIRATION_HOURS=24
   
   # CORS
   CORS_ORIGINS=*
   
   # Base de données
   DATABASE_URL=sqlite+aiosqlite:///./data/agriculture.db
   
   # AI Backend
   AI_BACKEND=external
   PLANT_ID_API_KEY=<votre_clé_plant_id>
   EXTERNAL_AI_TIMEOUT=30
   EXTERNAL_AI_FALLBACK=true
   
   # Storage
   STORAGE_TYPE=local
   LOCAL_STORAGE_PATH=./data/uploads
   
   # Logging
   LOG_LEVEL=INFO
   LOG_FORMAT=json
   
   # Monitoring
   PROMETHEUS_ENABLED=true
   ```

4. **Plan de service**
   - **Free** : Pour tester (limitations : arrêt après 15 min d'inactivité)
   - **Starter** : $7/mois (recommandé pour la production)
   - **Standard** : $25/mois (pour plus de ressources)

5. **Déployer**
   - Cliquez sur "Create Web Service"
   - Render va builder et déployer votre application
   - Attendez la fin du déploiement (5-10 minutes)

## 🔑 Variables d'Environnement Importantes

### Obligatoires

- `SECRET_KEY` : Clé secrète pour JWT (générez-en une avec `openssl rand -hex 32`)
- `PLANT_ID_API_KEY` : Clé API Plant.id (obtenez-la sur [plant.id](https://plant.id/))

### Optionnelles

- `CORS_ORIGINS` : Reste à `"*"` pour accepter l'URL Render (déjà configuré)
- `DATABASE_URL` : SQLite est configuré par défaut (fonctionne immédiatement)

## 📊 Base de Données SQLite (Gratuit et Sans Configuration)

**SQLite est déjà configuré et fonctionne directement !**

### ✅ Avantages de SQLite sur Render

- ✅ **100% Gratuit** - Aucun coût supplémentaire
- ✅ **Aucune configuration** - Fonctionne immédiatement
- ✅ **Aucune carte bancaire** - Pas d'engagement
- ✅ **Aucun risque de blocage** - Fichier local, pas de service externe
- ✅ **Facile à utiliser** - Aucune installation ou configuration requise
- ✅ **Déjà configuré** - Le fichier `render.yaml` inclut déjà SQLite

### ⚠️ Limitations importantes

- **Données éphémères** : Les données peuvent être perdues lors des redéploiements ou si le service redémarre
- **Pas de persistance garantie** : Le système de fichiers sur Render peut être réinitialisé
- **Limité pour la production** : Recommandé pour le développement et les tests

### 💡 Recommandation

Pour un usage en production avec persistance des données, considérez PostgreSQL (payant sur Render). Mais pour commencer et tester, **SQLite est parfait** et fonctionne immédiatement sans aucune configuration supplémentaire.

## 🌐 Accès à l'Application

1. **URL Render (automatique)**
   - Votre service sera accessible sur : `https://drone-ai-agriculture-api.onrender.com`
   - L'API est disponible à : `https://drone-ai-agriculture-api.onrender.com/api/v1/`
   - **Le frontend est accessible à** : `https://drone-ai-agriculture-api.onrender.com/web`
   - Le frontend est servi directement par FastAPI (pas besoin de service séparé)

2. **Accès direct**
   - Ouvrez simplement `https://votre-service.onrender.com/web` dans votre navigateur
   - L'interface HTML complète sera disponible

## 🔒 Sécurité

### En Production

1. **Changez `SECRET_KEY`**
   ```bash
   openssl rand -hex 32
   ```

2. **CORS** (optionnel)
   - Pour l'URL Render, `CORS_ORIGINS="*"` fonctionne parfaitement
   - Si vous ajoutez un domaine personnalisé plus tard, vous pouvez le limiter

3. **HTTPS**
   - Render fournit HTTPS automatiquement sur toutes les URLs
   - Aucune configuration nécessaire

4. **Variables sensibles**
   - Ne commitez jamais les clés API dans Git
   - Utilisez les variables d'environnement Render

## 📝 Vérification du Déploiement

1. **Vérifier les logs**
   - Dans Render Dashboard → Votre service → "Logs"
   - Vérifiez qu'il n'y a pas d'erreurs

2. **Tester l'API**
   ```bash
   curl https://votre-service.onrender.com/health
   ```
   Devrait retourner : `{"status": "healthy", ...}`

3. **Tester l'interface web (Frontend)**
   - Ouvrez `https://votre-service.onrender.com/web` dans votre navigateur
   - L'interface HTML complète devrait s'afficher
   - Vous pouvez tester l'analyse d'images directement depuis cette interface

## 🔄 Mises à Jour

Render déploie automatiquement à chaque push sur la branche configurée.

Pour forcer un redéploiement :
- Render Dashboard → Votre service → "Manual Deploy" → "Deploy latest commit"

## 🐛 Dépannage

### L'application ne démarre pas

1. **Vérifiez les logs** dans Render Dashboard
2. **Vérifiez les variables d'environnement**
3. **Vérifiez que le port est `$PORT`** dans le start command

### Erreurs de dépendances

1. Vérifiez que `requirements.txt` est à jour
2. Vérifiez les versions Python (Render utilise Python 3.10+ par défaut)

### Erreurs de base de données

1. Vérifiez que le dossier `data/` existe et est accessible
2. Pour PostgreSQL, vérifiez l'URL de connexion

### Timeout lors du build

- Le build peut prendre 10-15 minutes avec TensorFlow
- Vérifiez les logs pour voir où ça bloque
- Considérez utiliser un plan avec plus de ressources

## 📚 Ressources

- [Documentation Render](https://render.com/docs)
- [Guide Python sur Render](https://render.com/docs/deploy-a-python-app)
- [Variables d'environnement Render](https://render.com/docs/environment-variables)

## 💡 Astuces

1. **Utilisez le plan Free pour tester** avant de passer en production
2. **Activez les notifications** pour être alerté des déploiements
3. **Configurez les health checks** pour surveiller votre service
4. **SQLite est parfait pour commencer** - Gratuit, sans configuration, fonctionne immédiatement
5. **Le frontend est accessible via `/web`** - Pas besoin de service séparé
6. **Pour la production avec persistance**, considérez PostgreSQL (payant) si vous avez besoin de données garanties

## 🆘 Support

En cas de problème :
1. Consultez les logs dans Render Dashboard
2. Vérifiez la [documentation Render](https://render.com/docs)
3. Contactez le support Render si nécessaire

---

**Note** : Le premier déploiement peut prendre 10-15 minutes à cause de l'installation de TensorFlow et des dépendances ML. Les déploiements suivants seront plus rapides.
