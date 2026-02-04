# 📖 Guide Utilisateur - Drone AI Agriculture

Bienvenue dans le guide utilisateur de Drone AI Agriculture, votre solution complète de surveillance agricole intelligente.

## Table des Matières

1. [Introduction](#introduction)
2. [Interface Web](#interface-web)
3. [Analyse d'Images](#analyse-dimages)
4. [Interprétation des Résultats](#interprétation-des-résultats)
5. [Historique et Dashboard](#historique-et-dashboard)
6. [Export des Données](#export-des-données)
7. [FAQ](#faq)

---

## Introduction

Drone AI Agriculture utilise l'intelligence artificielle pour analyser vos cultures et vous fournir:

- ✅ **Détection de plantes** avec haute confiance
- 🌿 **Identification des espèces** végétales
- 📈 **Évaluation du stade de croissance**
- 🏥 **Diagnostic de santé** (maladies, carences, stress)
- 💡 **Recommandations** d'actions prioritaires

---

## Interface Web

### Accès

Ouvrez l'interface web dans votre navigateur:
- **Local**: `http://localhost:8000/web/index.html`
- **Cloud**: L'URL fournie par votre administrateur

### Navigation

L'interface comporte 4 onglets principaux:

| Onglet | Fonction |
|--------|----------|
| **Analyser** | Upload et analyse d'images |
| **Webcam** | Capture en temps réel |
| **Historique** | Consulter les analyses passées |
| **Dashboard** | Statistiques globales |

### Configuration

1. Cliquez sur l'icône ⚙️ en haut à droite
2. Entrez l'URL de l'API (fournie par votre administrateur)
3. Entrez votre clé API si nécessaire
4. Cliquez "Enregistrer"

---

## Analyse d'Images

### Méthode 1: Upload d'image

1. Allez dans l'onglet **Analyser**
2. Glissez-déposez une image ou cliquez pour sélectionner
3. Formats acceptés: JPG, PNG (max 10 MB)
4. Cliquez sur **Analyser**
5. Attendez les résultats (~1-2 secondes)

### Méthode 2: Webcam

1. Allez dans l'onglet **Webcam**
2. Cliquez sur **Démarrer**
3. Autorisez l'accès à la caméra
4. Pointez vers la plante à analyser
5. Cliquez sur 📷 pour capturer
6. L'analyse démarre automatiquement

### Conseils pour de bonnes photos

| ✅ Faire | ❌ Éviter |
|---------|----------|
| Bonne luminosité | Photos floues |
| Plante au centre | Contre-jour |
| Distance 30-100cm | Trop proche/loin |
| Angle perpendiculaire | Angle rasant |
| Feuilles visibles | Obstructions |

---

## Interprétation des Résultats

### Détection de Plante

| Badge | Signification |
|-------|---------------|
| 🟢 Détectée | Plante identifiée avec succès |
| 🟡 Non détectée | Aucune plante trouvée dans l'image |

**Confiance**: Pourcentage de certitude (>95% = excellent)

### Espèce Identifiée

Le système reconnaît 16+ espèces courantes:
- Tomate, Pomme de terre, Maïs, Blé
- Riz, Soja, Coton, Tournesol
- Raisin, Pomme, Orange, Fraise
- Et plus...

### Stade de Croissance

| Stade | Description |
|-------|-------------|
| Germination | Emergence des premières pousses |
| Plantule | Développement des premières feuilles |
| Végétatif | Croissance active des feuilles/tiges |
| Floraison | Apparition des fleurs |
| Fructification | Développement des fruits |
| Maturité | Fruit/grain presque mûr |
| Prêt à récolter | Récolte recommandée |

### État de Santé

| Status | Couleur | Action |
|--------|---------|--------|
| Healthy (Sain) | 🟢 Vert | Surveillance normale |
| Nitrogen deficiency | 🟡 Jaune | Fertilisation azotée |
| Phosphorus deficiency | 🟡 Jaune | Fertilisation phosphatée |
| Potassium deficiency | 🟡 Jaune | Fertilisation potassique |
| Water stress | 🟠 Orange | Irrigation urgente |
| Pest damage | 🔴 Rouge | Traitement anti-nuisibles |
| Disease | 🔴 Rouge | Traitement fongicide/bactéricide |

### Recommandations

Les recommandations sont classées par priorité:

| Priorité | Couleur | Délai d'action |
|----------|---------|----------------|
| 🔴 Critique | Rouge | Immédiat |
| 🟠 Haute | Orange | 24-48 heures |
| 🟡 Moyenne | Jaune | Cette semaine |
| 🟢 Basse | Vert | Quand possible |

Chaque recommandation inclut:
- **Action**: Ce qu'il faut faire
- **Timing**: Quand le faire
- **Produits**: Produits suggérés (si applicable)
- **Coût estimé**: Budget approximatif

---

## Historique et Dashboard

### Historique

L'onglet **Historique** affiche toutes vos analyses passées:

- Triées par date (plus récentes en premier)
- Filtrable par espèce, santé, drone, période
- Cliquez sur 👁️ pour revoir une analyse

### Dashboard

L'onglet **Dashboard** présente des statistiques globales:

- **Analyses totales**: Nombre d'images analysées
- **Plantes détectées**: Images avec plantes
- **Taux santé**: Pourcentage de plantes saines
- **Temps moyen**: Durée moyenne d'analyse

#### Graphiques

- **Distribution des espèces**: Quelles plantes sont surveillées
- **État de santé**: Répartition sain/malade/carencé

---

## Export des Données

### Export JSON

```
GET /api/v1/history/export?format=json
```

Retourne toutes vos analyses au format JSON, idéal pour:
- Intégration avec d'autres outils
- Analyse personnalisée
- Archivage

### Export CSV

```
GET /api/v1/history/export?format=csv
```

Retourne un fichier CSV, idéal pour:
- Microsoft Excel
- Google Sheets
- Logiciels statistiques

### Filtrer l'export

Paramètres disponibles:
- `start_date`: Date de début
- `end_date`: Date de fin
- `field_id`: Filtrer par parcelle
- `limit`: Nombre max d'entrées

Exemple:
```
/api/v1/history/export?format=csv&start_date=2024-01-01&field_id=field-A1
```

---

## FAQ

### Questions générales

**Q: Combien de temps prend une analyse?**
R: En moyenne 200-500ms. Le temps total dépend de votre connexion internet.

**Q: Quelle est la précision du système?**
R: 
- Détection de plante: >98%
- Identification espèce: >92%
- Diagnostic santé: >85%

**Q: Mes images sont-elles stockées?**
R: Oui, les images sont stockées de manière sécurisée pour l'historique. Vous pouvez demander leur suppression (RGPD).

### Problèmes courants

**Q: L'analyse échoue avec "API unreachable"**
R: 
1. Vérifiez votre connexion internet
2. Vérifiez l'URL de l'API dans les paramètres
3. Contactez votre administrateur

**Q: La webcam ne fonctionne pas**
R:
1. Autorisez l'accès à la caméra dans votre navigateur
2. Vérifiez qu'aucune autre application n'utilise la caméra
3. Essayez avec Chrome ou Firefox

**Q: Les résultats semblent incorrects**
R:
1. Vérifiez la qualité de l'image (netteté, luminosité)
2. Assurez-vous que la plante est bien visible
3. Essayez avec une photo de meilleure qualité

### Données et confidentialité

**Q: Comment supprimer mes données?**
R: Utilisez l'API: `DELETE /api/v1/history/{analysis_id}` ou contactez votre administrateur.

**Q: Où sont stockées mes données?**
R: Sur le serveur cloud configuré par votre organisation. Toutes les communications sont chiffrées (TLS).

---

## Support

Pour toute question ou problème:

- 📧 Email: support@drone-ai-agriculture.com
- 📖 Documentation: [docs/](.)
- 🐛 Signaler un bug: GitHub Issues

---

*Drone AI Agriculture - Pour une agriculture plus intelligente* 🌱