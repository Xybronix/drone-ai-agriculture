# 🎓 Guide d'Entraînement du Modèle IA

Ce guide explique comment entraîner le modèle de classification agricole sur différents environnements.

## Prérequis

- Python 3.8+
- TensorFlow 2.15+
- GPU recommandé (NVIDIA CUDA) ou utiliser Colab/Kaggle

## Option 1 : Google Colab (Recommandé)

Google Colab offre un GPU gratuit, idéal pour l'entraînement.

### Étapes

1. **Ouvrir le notebook**

   [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/votre-repo/drone-ai-agriculture/blob/main/ml/notebooks/training_colab.ipynb)

2. **Activer le GPU**
   - Menu: `Runtime` → `Change runtime type`
   - Sélectionner: `T4 GPU`
   - Cliquer: `Save`

3. **Configurer Kaggle** (pour télécharger les datasets)
   - Aller sur https://www.kaggle.com/settings
   - Cliquer "Create New Token" → télécharge `kaggle.json`
   - Dans Colab, ajouter aux secrets (🔑) :
     - `KAGGLE_USERNAME`: votre username
     - `KAGGLE_KEY`: votre API key

4. **Exécuter toutes les cellules**
   - Menu: `Runtime` → `Run all`
   - Attendre la fin de l'entraînement (~1-2 heures)

5. **Télécharger le modèle**
   - Le notebook génère automatiquement un fichier zip
   - Télécharger et extraire pour obtenir le modèle `.h5`

### Configuration recommandée

```python
CONFIG = {
    'epochs': 30,
    'fine_tune_epochs': 15,
    'batch_size': 32,
    'learning_rate': 1e-4,
    'backbone': 'efficientnet'
}
```

---

## Option 2 : Kaggle Notebooks

Kaggle offre également un GPU gratuit avec 30h/semaine.

### Étapes

1. **Créer un notebook**
   - Aller sur https://www.kaggle.com/code
   - Cliquer "New Notebook"

2. **Importer le code**
   ```python
   !git clone https://github.com/votre-repo/drone-ai-agriculture.git
   %cd drone-ai-agriculture
   ```

3. **Activer le GPU**
   - Panneau droit → Settings → Accelerator → GPU T4 x2

4. **Télécharger le dataset**
   - Le dataset PlantVillage est disponible directement sur Kaggle
   - Ajouter le dataset: `Add Data` → rechercher "plant disease"

5. **Lancer l'entraînement**
   ```python
   !python ml/train_model.py \
       --dataset /kaggle/input/plantdisease/PlantVillage \
       --output /kaggle/working/output \
       --epochs 30
   ```

6. **Télécharger les résultats**
   - Les fichiers dans `/kaggle/working/` sont téléchargeables

---

## Option 3 : Entraînement Local

### Avec GPU NVIDIA

#### Prérequis
- NVIDIA GPU (GTX 1060 minimum, RTX recommandé)
- CUDA 11.8+
- cuDNN 8.6+

#### Installation

```bash
# Créer environnement
conda create -n drone-ai python=3.10
conda activate drone-ai

# Installer TensorFlow avec GPU
pip install tensorflow[and-cuda]

# Vérifier GPU
python -c "import tensorflow as tf; print(tf.config.list_physical_devices('GPU'))"
```

#### Entraînement

```bash
# Télécharger le dataset
python ml/download_datasets.py --download plantvillage

# Lancer l'entraînement
python ml/train_model.py \
    --dataset ./data/datasets/plantvillage \
    --output ./output \
    --epochs 50 \
    --batch-size 32 \
    --backbone efficientnet
```

### CPU Only (Plus lent)

```bash
# Forcer CPU
python ml/train_model.py \
    --dataset ./data/datasets/plantvillage \
    --output ./output \
    --epochs 30 \
    --batch-size 16 \
    --cpu
```

⚠️ **Attention**: L'entraînement sur CPU peut prendre 10-20x plus de temps.

---

## Configuration des Datasets

### PlantVillage (Recommandé)

- **Taille**: ~2.5 GB
- **Classes**: 38 (maladies de plantes)
- **Images**: 54,303
- **Résolution**: Variable

```bash
python ml/download_datasets.py --download plantvillage
```

### Dataset Minimal (Test rapide)

- **Taille**: ~10 MB
- **Classes**: 5
- **Images**: 100 (synthétiques)

```bash
python ml/download_datasets.py --download mini_dataset
```

### Dataset Personnalisé

Structure requise:
```
mon_dataset/
├── classe_1/
│   ├── image_001.jpg
│   ├── image_002.jpg
│   └── ...
├── classe_2/
│   ├── image_001.jpg
│   └── ...
└── classe_n/
    └── ...
```

---

## Paramètres d'Entraînement

### Backbone

| Modèle | Précision | Vitesse | Taille |
|--------|-----------|---------|--------|
| MobileNetV3-Small | ★★★ | ★★★★★ | 4 MB |
| MobileNetV3-Large | ★★★★ | ★★★★ | 12 MB |
| **EfficientNet-B0** | ★★★★★ | ★★★★ | 20 MB |
| EfficientNet-B1 | ★★★★★ | ★★★ | 30 MB |

**Recommandation**: `efficientnet` pour le meilleur rapport qualité/performance.

### Hyperparamètres

```python
# Configuration standard
epochs = 50              # Époques initiales
fine_tune_epochs = 20    # Époques de fine-tuning
batch_size = 32          # Taille de batch (réduire si OOM)
learning_rate = 1e-4     # Taux d'apprentissage
validation_split = 0.2   # 20% pour validation
```

### Ajustements selon le matériel

| GPU VRAM | batch_size recommandé |
|----------|----------------------|
| 4 GB | 8-16 |
| 8 GB | 16-32 |
| 12 GB+ | 32-64 |
| CPU | 8-16 |

---

## Monitoring de l'Entraînement

### TensorBoard

```bash
# Lancer TensorBoard
tensorboard --logdir ./output/logs

# Ouvrir http://localhost:6006
```

### Métriques surveillées

- **loss**: Perte totale (doit diminuer)
- **val_loss**: Perte validation (attention au overfitting)
- **accuracy**: Précision entraînement
- **val_accuracy**: Précision validation (métrique principale)

### Signes de problèmes

| Symptôme | Cause probable | Solution |
|----------|---------------|----------|
| val_loss augmente | Overfitting | Plus de dropout, early stopping |
| Loss stagne | Learning rate trop bas | Augmenter LR |
| Loss oscille | Learning rate trop haut | Réduire LR |
| OOM Error | Batch trop grand | Réduire batch_size |

---

## Export du Modèle

### Formats disponibles

```bash
# Le script génère automatiquement:
output/
├── models/
│   ├── agriculture_model.h5       # Keras/TensorFlow
│   ├── agriculture_model.onnx     # ONNX (déploiement)
│   ├── agriculture_model_savedmodel/  # TensorFlow SavedModel
│   └── class_names.json           # Labels des classes
├── logs/
│   └── training_log.csv           # Historique
└── training_summary.json          # Résumé
```

### Conversion ONNX manuelle

```python
import tf2onnx
import tensorflow as tf

model = tf.keras.models.load_model('agriculture_model.h5')

spec = (tf.TensorSpec((None, 224, 224, 3), tf.float32, name="input"),)
tf2onnx.convert.from_keras(model, input_signature=spec, output_path="model.onnx")
```

---

## Validation du Modèle

### Métriques attendues

| Métrique | Minimum | Idéal |
|----------|---------|-------|
| Précision globale | 85% | 92%+ |
| Détection plante | 95% | 98%+ |
| Identification espèce | 88% | 92%+ |
| Diagnostic santé | 82% | 88%+ |

### Test rapide

```python
import tensorflow as tf
from PIL import Image
import numpy as np

model = tf.keras.models.load_model('agriculture_model.h5')

# Charger et prétraiter image
img = Image.open('test_image.jpg').resize((224, 224))
img_array = np.array(img) / 255.0
img_array = np.expand_dims(img_array, 0)

# Prédiction
predictions = model.predict(img_array)
print(f"Prédiction: {predictions}")
```

---

## Troubleshooting

### Erreur CUDA

```
Could not load dynamic library 'libcudart.so.11.0'
```

**Solution**:
```bash
conda install -c conda-forge cudatoolkit=11.8
```

### Out of Memory (OOM)

```
ResourceExhaustedError: OOM when allocating tensor
```

**Solutions**:
1. Réduire `batch_size`
2. Utiliser `mixed_precision`:
   ```python
   tf.keras.mixed_precision.set_global_policy('mixed_float16')
   ```

### Dataset introuvable

```
FileNotFoundError: [Errno 2] No such file or directory
```

**Solution**:
```bash
python ml/download_datasets.py --download plantvillage
python ml/download_datasets.py --verify plantvillage
```

---

## Prochaines étapes

1. **Déployer le modèle**: Copier `agriculture_model.h5` vers `./models/`
2. **Lancer l'API**: `python -m api.main`
3. **Tester**: Utiliser l'interface web ou l'API directement