#!/usr/bin/env python3
"""
Training Script for Agricultural Classification Model - Optimized Version
Compatible with: Google Colab, Kaggle, Local environments
"""

import os
import sys
import json
import argparse
import logging
import gc
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def detect_environment() -> Dict[str, Any]:
    """Detect the current execution environment and available resources."""
    env_info = {
        "environment": "local",
        "gpu_available": False,
        "gpu_name": None,
        "tpu_available": False,
        "memory_gb": 0
    }

    # Check for Colab
    try:
        import google.colab
        env_info["environment"] = "colab"
    except ImportError:
        pass

    # Check for Kaggle
    if os.environ.get("KAGGLE_KERNEL_RUN_TYPE"):
        env_info["environment"] = "kaggle"

    # Check for GPU
    try:
        import tensorflow as tf
        gpus = tf.config.list_physical_devices('GPU')
        if gpus:
            env_info["gpu_available"] = True
            env_info["gpu_name"] = gpus[0].name
            # Enable memory growth
            for gpu in gpus:
                tf.config.experimental.set_memory_growth(gpu, True)
    except Exception as e:
        logger.warning(f"GPU detection failed: {e}")

    # Check for TPU (Colab/Kaggle)
    try:
        import tensorflow as tf
        tpu = tf.distribute.cluster_resolver.TPUClusterResolver()
        env_info["tpu_available"] = True
    except Exception:
        pass

    # Get memory info
    try:
        import psutil
        env_info["memory_gb"] = round(psutil.virtual_memory().total / (1024**3), 1)
    except ImportError:
        pass

    return env_info


def setup_strategy(env_info: Dict[str, Any]):
    """Setup the appropriate distribution strategy."""
    import tensorflow as tf

    if env_info["tpu_available"]:
        logger.info("Using TPU strategy")
        resolver = tf.distribute.cluster_resolver.TPUClusterResolver()
        tf.config.experimental_connect_to_cluster(resolver)
        tf.tpu.experimental.initialize_tpu_system(resolver)
        strategy = tf.distribute.TPUStrategy(resolver)
    elif env_info["gpu_available"]:
        logger.info("Using GPU strategy")
        strategy = tf.distribute.MirroredStrategy()
    else:
        logger.info("Using CPU strategy")
        strategy = tf.distribute.get_strategy()

    logger.info(f"Number of replicas: {strategy.num_replicas_in_sync}")
    return strategy


def prepare_datasets(
    dataset_path: str,
    input_shape: Tuple[int, int] = (224, 224),
    batch_size: int = 32,
    validation_split: float = 0.2,
    use_cache: bool = True,
    use_augmentation: bool = True,
    ram_limit_gb: float = 4.0
):
    """Prepare training and validation datasets with memory optimization."""
    import tensorflow as tf
    
    logger.info(f"Loading dataset from {dataset_path}")
    
    # Utiliser tf.keras.preprocessing.image_dataset_from_directory
    train_ds = tf.keras.preprocessing.image_dataset_from_directory(
        dataset_path,
        validation_split=validation_split,
        subset="training",
        seed=123,
        image_size=input_shape,
        batch_size=batch_size,
        label_mode='categorical'
    )
    
    val_ds = tf.keras.preprocessing.image_dataset_from_directory(
        dataset_path,
        validation_split=validation_split,
        subset="validation",
        seed=123,
        image_size=input_shape,
        batch_size=batch_size,
        label_mode='categorical'
    )
    
    # Récupérer les noms de classes
    class_names = train_ds.class_names
    num_classes = len(class_names)
    
    logger.info(f"Found classes: {class_names}")
    
    # Simple normalisation
    normalization_layer = tf.keras.layers.Rescaling(1./255)
    
    def normalize_image(image, label):
        image = normalization_layer(image)
        return image, label
        
    # Appliquer la normalisation
    AUTOTUNE = tf.data.AUTOTUNE
    
    train_ds = train_ds.map(normalize_image, num_parallel_calls=AUTOTUNE)
    val_ds = val_ds.map(normalize_image, num_parallel_calls=AUTOTUNE)
    
    if use_cache:
        train_ds = train_ds.cache()
    
    train_ds = train_ds.prefetch(AUTOTUNE)
    val_ds = val_ds.prefetch(AUTOTUNE)
    
    return train_ds, val_ds, class_names


def create_advanced_model(
    num_classes: int,
    input_shape: Tuple[int, int, int] = (224, 224, 3),
    backbone: str = "efficientnet",
    use_attention: bool = False,
    dropout_rate: float = 0.2,
    use_mixed_precision: bool = True
):
    """Create an advanced classification model with optimizations."""
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers
    
    # Sélectionner le backbone
    if backbone == "efficientnet":
        base_model = tf.keras.applications.EfficientNetB0(
            include_top=False,
            weights='imagenet',
            input_shape=input_shape,
            pooling='avg'
        )
        base_model.trainable = False
    elif backbone == "efficientnet_b1":
        base_model = tf.keras.applications.EfficientNetB1(
            include_top=False,
            weights='imagenet',
            input_shape=(240, 240, 3),  # EfficientNetB1 requires 240x240
            pooling='avg'
        )
        base_model.trainable = False
    elif backbone == "mobilenet":
        base_model = tf.keras.applications.MobileNetV3Small(
            include_top=False,
            weights='imagenet',
            input_shape=input_shape,
            pooling='avg'
        )
        base_model.trainable = False
    elif backbone == "resnet50":
        base_model = tf.keras.applications.ResNet50V2(
            include_top=False,
            weights='imagenet',
            input_shape=input_shape,
            pooling='avg'
        )
        base_model.trainable = False
    else:
        raise ValueError(f"Unknown backbone: {backbone}")
    
    # Construction du modèle
    inputs = keras.Input(shape=input_shape)
    
    # Augmentation des données (uniquement pendant l'entraînement)
    x = layers.RandomFlip("horizontal")(inputs)
    x = layers.RandomRotation(0.05)(x)
    x = layers.RandomZoom(0.05)(x)
    x = layers.RandomBrightness(0.05)(x)
    x = layers.RandomContrast(0.05)(x)
    
    # Resize si nécessaire pour EfficientNetB1
    if backbone == "efficientnet_b1":
        x = layers.Resizing(240, 240)(x)
    
    # Backbone
    x = base_model(x, training=False)

    # Utilisation de GlobalAveragePooling2D pour plus de stabilité
    x = layers.GlobalAveragePooling2D()(x) if backbone != "efficientnet" else x
    
    # Régularisation
    x = layers.Dropout(dropout_rate)(x)
    
    # Couches supplémentaires avec normalisation
    x = layers.Dense(512, activation='relu')(x)
    x = layers.BatchNormalization()(x)
    x = layers.Dropout(dropout_rate)(x)
    
    x = layers.Dense(256, activation='relu')(x)
    x = layers.BatchNormalization()(x)
    x = layers.Dropout(dropout_rate * 0.5)(x)
    
    # Attention si activé
    if use_attention:
        attention = layers.Dense(256, activation='sigmoid')(x)
        x = layers.Multiply()([x, attention])
        x = layers.Dropout(dropout_rate * 0.5)(x)
    
    # Couche de sortie
    if use_mixed_precision:
        outputs = layers.Dense(num_classes, activation='linear', dtype='float32')(x)
        outputs = layers.Activation('softmax', dtype='float32')(outputs)
    else:
        outputs = layers.Dense(num_classes, activation='softmax')(x)
    
    model = keras.Model(inputs, outputs)
    
    return model, base_model


def train_model(
    dataset_path: str,
    output_dir: str = "./output",
    model_name: str = "agriculture_model",
    backbone: str = "efficientnet",
    epochs: int = 50,
    batch_size: int = 16,
    learning_rate: float = 1e-4,
    fine_tune_epochs: int = 30,
    fine_tune_layers: int = 100,
    use_mixed_precision: bool = False,
    use_early_stopping: bool = True,
    patience: int = 15
) -> Dict[str, Any]:
    """
    Train the agricultural classification model with optimizations.
    """
    import tensorflow as tf
    from tensorflow import keras
    
    # Activer la précision mixte pour plus de vitesse (GPU)
    if use_mixed_precision and tf.config.list_physical_devices('GPU'):
        policy = tf.keras.mixed_precision.Policy('mixed_float16')
        tf.keras.mixed_precision.set_global_policy(policy)
        logger.info("Mixed precision enabled")
        logger.info(f"Compute dtype: {policy.compute_dtype}")
        logger.info(f"Variable dtype: {policy.variable_dtype}")
    else:
        tf.keras.mixed_precision.set_global_policy('float32')
        logger.info("Using float32 precision")
    
    # Détecter l'environnement
    env_info = detect_environment()
    logger.info(f"Environment: {json.dumps(env_info, indent=2)}")
    
    # Configurer la stratégie
    strategy = setup_strategy(env_info)
    
    # Créer les répertoires de sortie
    output_path = Path(output_dir)
    models_path = output_path / "models"
    logs_path = output_path / "logs"
    checkpoints_path = output_path / "checkpoints"
    
    for path in [models_path, logs_path, checkpoints_path]:
        path.mkdir(parents=True, exist_ok=True)
    
    # Adapter la batch size pour l'entraînement distribué
    global_batch_size = batch_size * strategy.num_replicas_in_sync
    
    # Préparer les datasets avec optimisation mémoire
    logger.info("Preparing datasets with memory optimization...")
    train_ds, val_ds, class_names = prepare_datasets(
        dataset_path,
        input_shape=(224, 224),
        batch_size=global_batch_size,
        validation_split=0.2,
        use_cache=True,
        use_augmentation=True,
        ram_limit_gb=env_info.get("memory_gb", 12) * 0.3  # Utiliser 30% de la RAM
    )
    
    num_classes = len(class_names)
    
    # Sauvegarder les noms de classes
    with open(models_path / "class_names.json", "w") as f:
        json.dump(class_names, f, indent=2)
    
    # Construire et compiler le modèle dans le scope de la stratégie
    with strategy.scope():
        model, base_model = create_advanced_model(
            num_classes=num_classes,
            backbone=backbone,
            use_attention=True,
            dropout_rate=0.2
        )
        
        # Optimiseur avec weight decay
        if backbone == "efficientnet_b1":
            # Learning rate plus bas pour B1
            optimizer = keras.optimizers.AdamW(
                learning_rate=learning_rate * 0.3,
                weight_decay=1e-4
            )
        else:
            optimizer = keras.optimizers.AdamW(
                learning_rate=learning_rate * 0.5,
                weight_decay=1e-4
            )
        
        if use_mixed_precision:
            metrics = [
                keras.metrics.CategoricalAccuracy(name='accuracy'),
                keras.metrics.TopKCategoricalAccuracy(k=3, name='top3_accuracy', dtype=tf.float32),
                keras.metrics.AUC(name='auc', dtype=tf.float32),
                keras.metrics.Precision(name='precision', dtype=tf.float32),
                keras.metrics.Recall(name='recall', dtype=tf.float32)
            ]
        else:
            metrics = [
                'accuracy',
                keras.metrics.TopKCategoricalAccuracy(k=3, name='top3_accuracy'),
                keras.metrics.AUC(name='auc', multi_label=True),
                keras.metrics.Precision(name='precision'),
                keras.metrics.Recall(name='recall')
            ]
        
        # Compiler le modèle
        model.compile(
            optimizer=optimizer,
            loss='categorical_crossentropy',
            metrics=metrics
        )
    
    model.summary()
    
    # Callbacks améliorés
    callbacks = [
        keras.callbacks.ModelCheckpoint(
            filepath=str(checkpoints_path / "best_model.keras"),
            monitor='val_accuracy',
            save_best_only=True,
            mode='max',
            verbose=1
        ),
        keras.callbacks.ModelCheckpoint(
            filepath=str(checkpoints_path / "best_loss_model.keras"),
            monitor='val_loss',
            save_best_only=True,
            mode='min',
            verbose=0
        ),
        keras.callbacks.CSVLogger(
            str(logs_path / "training_log.csv"),
            separator=",",
            append=False
        )
    ]
    
    # Ajouter early stopping si activé
    if use_early_stopping:
        callbacks.append(
            keras.callbacks.EarlyStopping(
                monitor='val_accuracy',
                patience=patience,
                restore_best_weights=True,
                verbose=1,
                mode='max'
            )
        )
    
    # Ajouter réduction du learning rate
    callbacks.append(
        keras.callbacks.ReduceLROnPlateau(
            monitor='val_loss',
            factor=0.5,
            patience=max(3, patience // 3),
            min_lr=1e-7,
            verbose=1
        )
    )
    
    # Ajouter TensorBoard si disponible
    try:
        callbacks.append(
            keras.callbacks.TensorBoard(
                log_dir=str(logs_path),
                histogram_freq=1,
                write_graph=True,
                write_images=False,
                update_freq='epoch'
            )
        )
    except:
        pass
    
    # Phase 1: Entraîner avec backbone gelé
    logger.info("=" * 60)
    logger.info("Phase 1: Training with frozen backbone")
    logger.info("=" * 60)
    
    # Version corrigée sans paramètres obsolètes
    history1 = model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=epochs,
        callbacks=callbacks,
        verbose=1
    )
    
    # Phase 2: Fine-tuning
    if fine_tune_epochs > 0:
        logger.info("=" * 60)
        logger.info(f"Phase 2: Fine-tuning last {fine_tune_layers} layers")
        logger.info("=" * 60)
        
        # Déverrouiller le backbone
        base_model.trainable = True
        
        # Geler les premières couches
        trainable_count = 0
        total_layers = len(base_model.layers)

        # Dégeler seulement les dernières couches
        layers_to_unfreeze = min(fine_tune_layers, total_layers)
        for i, layer in enumerate(base_model.layers):
            # Dégeler les X dernières couches
            if i >= total_layers - layers_to_unfreeze:
                layer.trainable = True
                trainable_count += 1
            else:
                layer.trainable = False
        
        # Afficher les couches entraînables
        logger.info(f"Fine-tuning {trainable_count}/{total_layers} layers of backbone")

        # Fine-tuning avec patience réduite
        fine_tune_callbacks = [
            keras.callbacks.ModelCheckpoint(
                filepath=str(checkpoints_path / "best_finetuned_model.keras"),
                monitor='val_accuracy',
                save_best_only=True,
                mode='max',
                verbose=1
            ),
            keras.callbacks.EarlyStopping(
                monitor='val_accuracy',
                patience=5,
                restore_best_weights=True,
                verbose=1
            ),
            keras.callbacks.ReduceLROnPlateau(
                monitor='val_loss',
                factor=0.5,
                patience=3,
                min_lr=1e-7,
                verbose=1
            ),
            keras.callbacks.CSVLogger(
                str(logs_path / "fine_tuning_log.csv"),
                separator=",",
                append=True 
            )
        ]

        if use_early_stopping:
            fine_tune_callbacks.append(
                keras.callbacks.EarlyStopping(
                    monitor='val_accuracy',
                    patience=max(5, patience // 2),  # Patience différente
                    restore_best_weights=True,
                    verbose=1,
                    mode='max'
                )
            )
        
        # Recompiler avec un learning rate très bas pour le fine-tuning
        with strategy.scope():
            model.compile(
                optimizer=keras.optimizers.Adam(
                    learning_rate=learning_rate / 50,
                    weight_decay=1e-6
                ),
                loss='categorical_crossentropy',
                metrics=[
                    'accuracy',
                    keras.metrics.TopKCategoricalAccuracy(k=3, name='top3_accuracy'),
                    keras.metrics.AUC(name='auc', multi_label=True)
                ]
            )
        
        # Réinitialiser le meilleur score pour le fine-tuning
        logger.info("Starting fine-tuning phase...")
        
        try:
            history2 = model.fit(
                train_ds,
                validation_data=val_ds,
                epochs=epochs + fine_tune_epochs,
                initial_epoch=epochs,
                callbacks=fine_tune_callbacks,
                verbose=1
            )
            
            # Combiner les historiques
            combined_history = {}
            for key in history1.history.keys():
                if key in history2.history:
                    combined_history[key] = history1.history[key] + history2.history[key]
                else:
                    combined_history[key] = history1.history[key]
            
            # Mettre à jour pour utiliser l'historique combiné
            history_for_report = type('obj', (object,), {'history': combined_history})()
            
        except Exception as e:
            logger.warning(f"Fine-tuning failed: {e}. Using phase 1 results only.")
            history_for_report = history1
    
    # Nettoyer la mémoire
    gc.collect()
    
    # Évaluation finale
    logger.info("=" * 60)
    logger.info("Final Evaluation")
    logger.info("=" * 60)
    
    try:
        # Essayer avec return_dict=True
        eval_results = model.evaluate(val_ds, verbose=1, return_dict=True)
        metrics_dict = eval_results
    except:
        # Fallback pour anciennes versions
        eval_results = model.evaluate(val_ds, verbose=1)
        if isinstance(eval_results, dict):
            metrics_dict = eval_results
        elif isinstance(eval_results, list):
            # Essayer de mapper avec les noms de métriques
            metric_names = model.metrics_names if hasattr(model, 'metrics_names') else []
            metrics_dict = {}
            for i, name in enumerate(metric_names):
                if i < len(eval_results):
                    metrics_dict[name] = float(eval_results[i])
        else:
            metrics_dict = {"compile_metrics": float(eval_results)}
    
    logger.info(f"Final metrics: {json.dumps(metrics_dict, indent=2)}")

    accuracy = metrics_dict.get('accuracy', metrics_dict.get('compile_metrics', 0))
    auc_score = metrics_dict.get('auc', 0)
    top3_acc = metrics_dict.get('top3_accuracy', 0)
    
    # Sauvegarder le modèle final dans différents formats
    logger.info("Saving model in multiple formats...")
    
    # Format Keras 3 (.keras)
    keras_v3_path = models_path / f"{model_name}.keras"
    model.save(str(keras_v3_path))
    logger.info(f"✓ Keras v3 model saved to {keras_v3_path}")
    
    # Format H5 pour compatibilité
    try:
        h5_path = models_path / f"{model_name}.h5"
        model.save(str(h5_path))
        logger.info(f"✓ H5 model saved to {h5_path}")
    except Exception as e:
        logger.warning(f"Could not save H5 format: {e}")
    
    # Format SavedModel
    try:
        savedmodel_path = models_path / f"{model_name}_savedmodel"
        model.save(str(savedmodel_path), save_format='tf')
        logger.info(f"✓ SavedModel saved to {savedmodel_path}")
    except Exception as e:
        logger.warning(f"Could not save SavedModel: {e}")
    
    # Exporter en ONNX si possible
    try:
        import tf2onnx
        onnx_path = models_path / f"{model_name}.onnx"
        
        spec = (tf.TensorSpec((None, 224, 224, 3), tf.float32, name="input"),)
        model_proto, _ = tf2onnx.convert.from_keras(
            model,
            input_signature=spec,
            opset=14,
            output_path=str(onnx_path)
        )
        logger.info(f"✓ ONNX model saved to {onnx_path}")
    except ImportError:
        logger.warning("tf2onnx not available. Skipping ONNX export.")
    except Exception as e:
        logger.warning(f"Could not export to ONNX: {e}")
    
    # Sauvegarder un résumé de l'entraînement
    summary = {
        "model_name": model_name,
        "backbone": backbone,
        "num_classes": num_classes,
        "class_names": class_names,
        "input_shape": [224, 224, 3],
        "training_config": {
            "epochs": epochs,
            "fine_tune_epochs": fine_tune_epochs,
            "batch_size": batch_size,
            "learning_rate": learning_rate,
            "fine_tune_layers": fine_tune_layers
        },
        "final_metrics": metrics_dict,
        "final_accuracy": float(accuracy),
        "final_auc": float(auc_score),
        "final_top3_accuracy": float(top3_acc),
        "best_accuracy": float(max(history1.history['val_accuracy'])),
        "best_loss": float(min(history1.history['val_loss'])),
        "environment": env_info,
        "timestamp": datetime.now().isoformat()
    }
    
    with open(output_path / "training_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    
    # Générer un rapport de performance
    generate_performance_report(summary, output_path, history1)
    
    logger.info("=" * 60)
    logger.info("Training Complete!")
    logger.info(f"Model: {keras_v3_path}")
    logger.info(f"Accuracy: {accuracy:.4f}")
    logger.info(f"AUC: {auc_score:.4f}")
    logger.info(f"Top-3 Accuracy: {top3_acc:.4f}")
    logger.info("=" * 60)
    
    return summary


def debug_training(dataset_path: str):
    """Debug function to check dataset and model issues."""
    import tensorflow as tf
    import numpy as np
    
    print("=" * 60)
    print("DEBUG MODE - Checking dataset and model")
    print("=" * 60)
    
    # 1. Vérifier le dataset
    train_ds, val_ds, class_names = prepare_datasets(
        dataset_path,
        input_shape=(224, 224),
        batch_size=32,
        validation_split=0.2,
        use_cache=False,
        use_augmentation=False
    )
    
    print(f"\n1. Dataset Info:")
    print(f"   Classes: {len(class_names)}")
    print(f"   Class names: {class_names}")
    
    # Vérifier un batch
    for images, labels in train_ds.take(1):
        print(f"\n2. Batch Info:")
        print(f"   Images shape: {images.shape}")
        print(f"   Labels shape: {labels.shape}")
        print(f"   Images dtype: {images.dtype}")
        print(f"   Labels dtype: {labels.dtype}")
        print(f"   Images range: [{tf.reduce_min(images):.3f}, {tf.reduce_max(images):.3f}]")
        
        # Vérifier les labels
        print(f"\n3. Labels check:")
        print(f"   Sample label: {labels[0].numpy()}")
        print(f"   Label sum (should be 1): {tf.reduce_sum(labels[0]).numpy():.3f}")
        print(f"   Unique labels in batch: {tf.argmax(labels, axis=1).numpy()[:10]}...")
    
    # 2. Vérifier le modèle
    print(f"\n4. Model test:")
    test_model, _ = create_advanced_model(
        num_classes=len(class_names),
        backbone="efficientnet",
        use_attention=False,
        dropout_rate=0.0  # Pas de dropout pour le test
    )
    
    # Test forward pass
    test_batch = tf.random.normal((2, 224, 224, 3))
    predictions = test_model(test_batch, training=False)
    print(f"   Test prediction shape: {predictions.shape}")
    print(f"   Test prediction dtype: {predictions.dtype}")
    print(f"   Prediction sum (should be ~1): {tf.reduce_sum(predictions[0]).numpy():.3f}")
    
    # 3. Vérifier la distribution des classes
    print(f"\n5. Class distribution:")
    class_counts = {name: 0 for name in class_names}
    
    # Compter les échantillons (limité pour la vitesse)
    total_samples = 0
    for _, labels in train_ds.take(10):  # 10 batches seulement
        batch_labels = tf.argmax(labels, axis=1).numpy()
        for label_idx in batch_labels:
            class_counts[class_names[label_idx]] += 1
            total_samples += 1
    
    print(f"   Total samples checked: {total_samples}")
    for class_name, count in class_counts.items():
        if count > 0:
            percentage = (count / total_samples) * 100
            print(f"   {class_name}: {count} samples ({percentage:.1f}%)")
    
    print("\n" + "=" * 60)
    print("DEBUG COMPLETE")
    print("=" * 60)
    
    return train_ds, val_ds, class_names


def analyze_training_problems(train_ds, val_ds, class_names):
    """Analyze potential training problems."""
    import tensorflow as tf
    import numpy as np
    
    print("\n" + "="*60)
    print("TRAINING PROBLEM ANALYSIS")
    print("="*60)
    
    # 1. Vérifier la distribution des classes
    print("\n1. Class Distribution Analysis:")
    
    train_class_counts = {name: 0 for name in class_names}
    val_class_counts = {name: 0 for name in class_names}
    
    # Compter les échantillons d'entraînement
    train_samples = 0
    for _, labels in train_ds.take(20):  # 20 batches
        batch_labels = tf.argmax(labels, axis=1).numpy()
        for label_idx in batch_labels:
            train_class_counts[class_names[label_idx]] += 1
            train_samples += 1
    
    # Compter les échantillons de validation
    val_samples = 0
    for _, labels in val_ds.take(10):  # 10 batches
        batch_labels = tf.argmax(labels, axis=1).numpy()
        for label_idx in batch_labels:
            val_class_counts[class_names[label_idx]] += 1
            val_samples += 1
    
    print(f"   Training samples analyzed: {train_samples}")
    print(f"   Validation samples analyzed: {val_samples}")
    
    # Trouver les classes déséquilibrées
    print("\n   Classes with potential issues:")
    issues_found = False
    for class_name in class_names:
        train_count = train_class_counts[class_name]
        val_count = val_class_counts[class_name]
        
        if train_count == 0:
            print(f"   ⚠️  {class_name}: No training samples!")
            issues_found = True
        elif val_count == 0:
            print(f"   ⚠️  {class_name}: No validation samples!")
            issues_found = True
        elif train_count < 10:
            print(f"   ⚠️  {class_name}: Only {train_count} training samples")
            issues_found = True
    
    if not issues_found:
        print("   ✓ All classes have sufficient samples")
    
    # 2. Vérifier les données
    print("\n2. Data Quality Check:")
    
    # Prendre un batch
    for images, labels in train_ds.take(1):
        # Vérifier les valeurs des pixels
        min_val = tf.reduce_min(images).numpy()
        max_val = tf.reduce_max(images).numpy()
        mean_val = tf.reduce_mean(images).numpy()
        
        print(f"   Image value range: [{min_val:.3f}, {max_val:.3f}]")
        print(f"   Image mean: {mean_val:.3f}")
        
        if min_val < 0 or max_val > 1:
            print("   ⚠️  Images not properly normalized!")
        else:
            print("   ✓ Images properly normalized [0, 1]")
        
        # Vérifier les labels
        label_sums = tf.reduce_sum(labels, axis=1).numpy()
        if np.allclose(label_sums, 1.0):
            print("   ✓ Labels properly one-hot encoded (sum to ~1)")
        else:
            print(f"   ⚠️  Label sums: {label_sums[:5]}... (should be 1)")
    
    # 3. Recommandations
    print("\n3. Recommendations:")
    print("   • Increase patience to 15-20 epochs")
    print("   • Reduce dropout to 0.2-0.3")
    print("   • Use smaller batch size (16)")
    print("   • Disable mixed precision for debugging")
    print("   • Consider class weighting if imbalance > 10:1")
    
    print("\n" + "="*60)
    
    return issues_found


def generate_performance_report(summary: Dict[str, Any], output_path: Path, history):
    """Generate a performance report HTML file."""
    try:
        import matplotlib.pyplot as plt
        import pandas as pd
        
        report_path = output_path / "performance_report.html"
        
        # Utiliser l'historique directement
        if hasattr(history, 'history'):
            history_dict = history.history
        else:
            history_dict = history
        
        # Créer des graphiques
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        
        # Accuracy
        if 'accuracy' in history_dict and 'val_accuracy' in history_dict:
            axes[0, 0].plot(history_dict['accuracy'], label='Train')
            axes[0, 0].plot(history_dict['val_accuracy'], label='Validation')
            axes[0, 0].set_title('Accuracy')
            axes[0, 0].set_xlabel('Epoch')
            axes[0, 0].set_ylabel('Accuracy')
            axes[0, 0].legend()
            axes[0, 0].grid(True, alpha=0.3)
        
        # Loss
        if 'loss' in history_dict and 'val_loss' in history_dict:
            axes[0, 1].plot(history_dict['loss'], label='Train')
            axes[0, 1].plot(history_dict['val_loss'], label='Validation')
            axes[0, 1].set_title('Loss')
            axes[0, 1].set_xlabel('Epoch')
            axes[0, 1].set_ylabel('Loss')
            axes[0, 1].legend()
            axes[0, 1].grid(True, alpha=0.3)
        
        # Learning Rate (si disponible)
        if hasattr(history, 'history') and 'lr' in history.history:
            axes[1, 0].plot(history.history['lr'], label='Learning Rate')
            axes[1, 0].set_title('Learning Rate')
            axes[1, 0].set_xlabel('Epoch')
            axes[1, 0].set_ylabel('LR')
            axes[1, 0].legend()
            axes[1, 0].grid(True, alpha=0.3)
            axes[1, 0].set_yscale('log')
        else:
            # Plot vide si pas de LR
            axes[1, 0].text(0.5, 0.5, 'Learning Rate not tracked', 
                           ha='center', va='center', transform=axes[1, 0].transAxes)
            axes[1, 0].set_title('Learning Rate')
        
        # Top-3 Accuracy
        if 'top3_accuracy' in history_dict and 'val_top3_accuracy' in history_dict:
            axes[1, 1].plot(history_dict['top3_accuracy'], label='Train')
            axes[1, 1].plot(history_dict['val_top3_accuracy'], label='Validation')
            axes[1, 1].set_title('Top-3 Accuracy')
            axes[1, 1].set_xlabel('Epoch')
            axes[1, 1].set_ylabel('Top-3 Accuracy')
            axes[1, 1].legend()
            axes[1, 1].grid(True, alpha=0.3)
        else:
            # Plot vide si pas de top3
            axes[1, 1].text(0.5, 0.5, 'Top-3 Accuracy not tracked', 
                           ha='center', va='center', transform=axes[1, 1].transAxes)
            axes[1, 1].set_title('Top-3 Accuracy')
        
        plt.tight_layout()
        plot_path = output_path / "training_plots.png"
        plt.savefig(plot_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        # Créer le rapport HTML
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Training Performance Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .container {{ max-width: 1200px; margin: 0 auto; }}
                .header {{ background: #4CAF50; color: white; padding: 20px; border-radius: 5px; }}
                .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 30px 0; }}
                .metric-card {{ background: #f5f5f5; padding: 20px; border-radius: 5px; text-align: center; }}
                .metric-value {{ font-size: 2em; font-weight: bold; color: #4CAF50; }}
                .plot {{ margin: 30px 0; text-align: center; }}
                img {{ max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 5px; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background-color: #4CAF50; color: white; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Agricultural Model Training Report</h1>
                    <p>Generated on {summary.get('timestamp', 'N/A')}</p>
                </div>
                
                <div class="metrics">
                    <div class="metric-card">
                        <div class="metric-name">Final Accuracy</div>
                        <div class="metric-value">{summary['final_metrics'].get('accuracy', 0):.4f}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-name">Best Accuracy</div>
                        <div class="metric-value">{summary.get('best_accuracy', 0):.4f}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-name">AUC Score</div>
                        <div class="metric-value">{summary['final_metrics'].get('auc', 0):.4f}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-name">Top-3 Accuracy</div>
                        <div class="metric-value">{summary['final_metrics'].get('top3_accuracy', 0):.4f}</div>
                    </div>
                </div>
                
                <div class="plot">
                    <h2>Training Progress</h2>
                    <img src="training_plots.png" alt="Training Plots">
                </div>
                
                <h2>Model Configuration</h2>
                <table>
                    <tr><th>Parameter</th><th>Value</th></tr>
                    <tr><td>Model Name</td><td>{summary['model_name']}</td></tr>
                    <tr><td>Backbone</td><td>{summary['backbone']}</td></tr>
                    <tr><td>Number of Classes</td><td>{summary['num_classes']}</td></tr>
                    <tr><td>Epochs</td><td>{summary['training_config']['epochs']}</td></tr>
                    <tr><td>Batch Size</td><td>{summary['training_config']['batch_size']}</td></tr>
                    <tr><td>Learning Rate</td><td>{summary['training_config']['learning_rate']}</td></tr>
                </table>
                
                <h2>Classes</h2>
                <ul>
                    {''.join(f'<li>{cls}</li>' for cls in summary['class_names'])}
                </ul>
                
                <h2>Environment</h2>
                <table>
                    <tr><th>Resource</th><th>Value</th></tr>
                    <tr><td>Environment</td><td>{summary['environment'].get('environment', 'N/A')}</td></tr>
                    <tr><td>GPU Available</td><td>{summary['environment'].get('gpu_available', False)}</td></tr>
                    <tr><td>GPU Name</td><td>{summary['environment'].get('gpu_name', 'N/A')}</td></tr>
                    <tr><td>Memory (GB)</td><td>{summary['environment'].get('memory_gb', 'N/A')}</td></tr>
                </table>
            </div>
        </body>
        </html>
        """
        
        with open(report_path, 'w') as f:
            f.write(html_content)
        
        logger.info(f"Performance report saved to {report_path}")
        
    except Exception as e:
        logger.warning(f"Could not generate performance report: {e}")


def main():
    """Main entry point for training script."""
    # DÉSACTIVER MKL POUR ÉVITER LES PROBLÈMES DE MÉMOIRE
    os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
    
    parser = argparse.ArgumentParser(
        description="Train Agricultural Classification Model - Optimized",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
            Examples:
            # Train with default settings
            python train_model.py --dataset ./data/datasets/plantvillage

            # Train with combined dataset for better generalization
            python train_model.py --dataset ./data/datasets/combined_dataset

            # Train with custom settings
            python train_model.py --dataset ./data/datasets/plantvillage \\
                --backbone efficientnet_b1 --epochs 30 --batch-size 64

            # Quick test with mini dataset
            python train_model.py --dataset ./data/datasets/mini_dataset --epochs 10
        """
    )

    parser.add_argument(
        '--dataset', '-d',
        type=str,
        required=True,
        help='Path to training dataset'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='./output',
        help='Output directory'
    )
    parser.add_argument(
        '--model-name', '-n',
        type=str,
        default='agriculture_model',
        help='Name for the saved model'
    )
    parser.add_argument(
        '--backbone', '-b',
        type=str,
        choices=['efficientnet', 'efficientnet_b1', 'mobilenet', 'resnet50'],
        default='efficientnet',
        help='Backbone architecture'
    )
    parser.add_argument(
        '--epochs', '-e',
        type=int,
        default=30,
        help='Number of training epochs'
    )
    parser.add_argument(
        '--fine-tune-epochs',
        type=int,
        default=15,
        help='Number of fine-tuning epochs'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=32,
        help='Training batch size'
    )
    parser.add_argument(
        '--learning-rate', '-lr',
        type=float,
        default=1e-4,
        help='Initial learning rate'
    )
    parser.add_argument(
        '--fine-tune-layers',
        type=int,
        default=50,
        help='Number of layers to unfreeze for fine-tuning'
    )
    parser.add_argument(
        '--no-mixed-precision',
        action='store_true',
        help='Disable mixed precision training'
    )
    parser.add_argument(
        '--no-early-stopping',
        action='store_true',
        help='Disable early stopping'
    )
    parser.add_argument(
        '--patience',
        type=int,
        default=10,
        help='Patience for early stopping'
    )
    parser.add_argument(
        '--gpu',
        action='store_true',
        help='Force GPU usage (fail if not available)'
    )
    parser.add_argument(
        '--cpu',
        action='store_true',
        help='Force CPU usage'
    )

    args = parser.parse_args()

    # Validate dataset path
    if not os.path.exists(args.dataset):
        logger.error(f"Dataset not found: {args.dataset}")
        logger.info("Run 'python ml/download_datasets.py --download-all' to create datasets")
        sys.exit(1)

    # Force CPU if requested
    if args.cpu:
        os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
        logger.info("Forcing CPU usage")

    # Check GPU if required
    if args.gpu:
        import tensorflow as tf
        if not tf.config.list_physical_devices('GPU'):
            logger.error("GPU requested but not available")
            sys.exit(1)

    # Préparer les datasets pour analyse
    logger.info("Preparing datasets for analysis...")
    train_ds, val_ds, class_names = prepare_datasets(
        args.dataset,
        input_shape=(224, 224),
        batch_size=32,
        validation_split=0.2,
        use_cache=False,
        use_augmentation=False
    )
    
    # Analyser les problèmes potentiels
    analyze_training_problems(train_ds, val_ds, class_names)

    # Run training
    try:
        summary = train_model(
            dataset_path=args.dataset,
            output_dir=args.output,
            model_name=args.model_name,
            backbone=args.backbone,
            epochs=args.epochs,
            batch_size=args.batch_size,
            learning_rate=args.learning_rate,
            fine_tune_epochs=args.fine_tune_epochs,
            fine_tune_layers=args.fine_tune_layers,
            use_mixed_precision=not args.no_mixed_precision,
            use_early_stopping=not args.no_early_stopping,
            patience=args.patience
        )

        # Print summary
        print("\n" + "=" * 60)
        print("TRAINING SUMMARY")
        print("=" * 60)
        print(f"Model: {summary['model_name']}")
        print(f"Backbone: {summary['backbone']}")
        print(f"Classes: {summary['num_classes']}")
        print(f"Final Accuracy: {summary['final_metrics'].get('accuracy', 0):.4f}")
        print(f"AUC: {summary['final_metrics'].get('auc', 0):.4f}")
        print(f"Top-3 Accuracy: {summary['final_metrics'].get('top3_accuracy', 0):.4f}")
        print(f"Best Accuracy: {summary.get('best_accuracy', 0):.4f}")
        print(f"Files saved to: {args.output}")
        print("=" * 60)

    except Exception as e:
        logger.error(f"Training failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()