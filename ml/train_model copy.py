#!/usr/bin/env python3
"""
Training Script for Agricultural Classification Model
Compatible with: Google Colab, Kaggle, Local environments
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

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
    validation_split: float = 0.2
):
    """Prepare training and validation datasets."""
    import tensorflow as tf

    logger.info(f"Loading dataset from {dataset_path}")

    # Create datasets using image_dataset_from_directory
    train_ds = tf.keras.utils.image_dataset_from_directory(
        dataset_path,
        validation_split=validation_split,
        subset="training",
        seed=42,
        image_size=input_shape,
        batch_size=batch_size,
        label_mode='categorical'
    )

    val_ds = tf.keras.utils.image_dataset_from_directory(
        dataset_path,
        validation_split=validation_split,
        subset="validation",
        seed=42,
        image_size=input_shape,
        batch_size=batch_size,
        label_mode='categorical'
    )

    # Get class names
    class_names = train_ds.class_names
    num_classes = len(class_names)
    logger.info(f"Found {num_classes} classes: {class_names}")

    # Normalize and prefetch
    normalization_layer = tf.keras.layers.Rescaling(1./255)

    train_ds = train_ds.map(lambda x, y: (normalization_layer(x), y))
    val_ds = val_ds.map(lambda x, y: (normalization_layer(x), y))

    # Performance optimization
    AUTOTUNE = tf.data.AUTOTUNE
    train_ds = train_ds.cache().shuffle(1000).prefetch(buffer_size=AUTOTUNE)
    val_ds = val_ds.cache().prefetch(buffer_size=AUTOTUNE)

    return train_ds, val_ds, class_names


def create_simple_model(
    num_classes: int,
    input_shape: Tuple[int, int, int] = (224, 224, 3),
    backbone: str = "efficientnet"
):
    """Create a simple single-task classification model."""
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers

    # Choose backbone
    if backbone == "efficientnet":
        base_model = tf.keras.applications.EfficientNetB0(
            include_top=False,
            weights='imagenet',
            input_shape=input_shape,
            pooling='avg'
        )
    elif backbone == "mobilenet":
        base_model = tf.keras.applications.MobileNetV3Small(
            include_top=False,
            weights='imagenet',
            input_shape=input_shape,
            pooling='avg'
        )
    else:
        raise ValueError(f"Unknown backbone: {backbone}")

    # Freeze base model initially
    base_model.trainable = False

    # Build model
    inputs = keras.Input(shape=input_shape)

    # Data augmentation
    x = layers.RandomFlip("horizontal")(inputs)
    x = layers.RandomRotation(0.1)(x)
    x = layers.RandomZoom(0.1)(x)

    # Base model
    x = base_model(x, training=False)

    # Classification head
    x = layers.Dropout(0.3)(x)
    x = layers.Dense(256, activation='relu')(x)
    x = layers.BatchNormalization()(x)
    x = layers.Dropout(0.2)(x)
    outputs = layers.Dense(num_classes, activation='softmax')(x)

    model = keras.Model(inputs, outputs)

    return model, base_model


def train_model(
    dataset_path: str,
    output_dir: str = "./output",
    model_name: str = "agriculture_model",
    backbone: str = "efficientnet",
    epochs: int = 50,
    batch_size: int = 32,
    learning_rate: float = 1e-4,
    fine_tune_epochs: int = 20,
    fine_tune_layers: int = 50
) -> Dict[str, Any]:
    """
    Train the agricultural classification model.

    Args:
        dataset_path: Path to the training dataset
        output_dir: Output directory for models and logs
        model_name: Name for the saved model
        backbone: Backbone architecture
        epochs: Number of initial training epochs
        batch_size: Training batch size
        learning_rate: Initial learning rate
        fine_tune_epochs: Additional epochs for fine-tuning
        fine_tune_layers: Number of layers to unfreeze for fine-tuning

    Returns:
        Dictionary with training results and metrics
    """
    import tensorflow as tf
    from tensorflow import keras

    # Detect environment
    env_info = detect_environment()
    logger.info(f"Environment: {json.dumps(env_info, indent=2)}")

    # Setup strategy
    strategy = setup_strategy(env_info)

    # Create output directories
    output_path = Path(output_dir)
    models_path = output_path / "models"
    logs_path = output_path / "logs"
    checkpoints_path = output_path / "checkpoints"

    for path in [models_path, logs_path, checkpoints_path]:
        path.mkdir(parents=True, exist_ok=True)

    # Adjust batch size for distributed training
    global_batch_size = batch_size * strategy.num_replicas_in_sync

    # Prepare datasets
    train_ds, val_ds, class_names = prepare_datasets(
        dataset_path,
        input_shape=(224, 224),
        batch_size=global_batch_size
    )

    num_classes = len(class_names)

    # Save class names
    with open(models_path / "class_names.json", "w") as f:
        json.dump(class_names, f, indent=2)

    # Build and compile model within strategy scope
    with strategy.scope():
        model, base_model = create_simple_model(
            num_classes=num_classes,
            backbone=backbone
        )

        model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=learning_rate),
            loss='categorical_crossentropy',
            metrics=[
                'accuracy',
                keras.metrics.TopKCategoricalAccuracy(k=3, name='top3_accuracy'),
                keras.metrics.AUC(name='auc')
            ]
        )

    model.summary()

    # Callbacks
    callbacks = [
        keras.callbacks.ModelCheckpoint(
            filepath=str(checkpoints_path / "best_model.h5"),
            monitor='val_accuracy',
            save_best_only=True,
            verbose=1
        ),
        keras.callbacks.EarlyStopping(
            monitor='val_loss',
            patience=10,
            restore_best_weights=True,
            verbose=1
        ),
        keras.callbacks.ReduceLROnPlateau(
            monitor='val_loss',
            factor=0.5,
            patience=5,
            min_lr=1e-7,
            verbose=1
        ),
        keras.callbacks.TensorBoard(
            log_dir=str(logs_path),
            histogram_freq=1
        ),
        keras.callbacks.CSVLogger(
            str(logs_path / "training_log.csv")
        )
    ]

    # Phase 1: Train with frozen base
    logger.info("=" * 60)
    logger.info("Phase 1: Training with frozen backbone")
    logger.info("=" * 60)

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

        # Unfreeze the base model
        base_model.trainable = True

        # Freeze early layers
        for layer in base_model.layers[:-fine_tune_layers]:
            layer.trainable = False

        # Recompile with lower learning rate
        with strategy.scope():
            model.compile(
                optimizer=keras.optimizers.Adam(learning_rate=learning_rate / 10),
                loss='categorical_crossentropy',
                metrics=[
                    'accuracy',
                    keras.metrics.TopKCategoricalAccuracy(k=3, name='top3_accuracy'),
                    keras.metrics.AUC(name='auc')
                ]
            )

        history2 = model.fit(
            train_ds,
            validation_data=val_ds,
            epochs=fine_tune_epochs,
            callbacks=callbacks,
            verbose=1
        )

    # Evaluate final model
    logger.info("=" * 60)
    logger.info("Final Evaluation")
    logger.info("=" * 60)

    eval_results = model.evaluate(val_ds, verbose=1)
    metrics_dict = dict(zip(model.metrics_names, eval_results))

    logger.info(f"Final metrics: {json.dumps(metrics_dict, indent=2)}")

    # Save final model (.h5)
    final_model_path = models_path / f"{model_name}.h5"
    model.save(str(final_model_path))
    logger.info(f"Model saved to {final_model_path}")

    # Save as Keras v3 format (.keras)
    keras_v3_path = models_path / f"{model_name}.keras"
    model.save(str(keras_v3_path))
    logger.info(f"Keras v3 model saved to {keras_v3_path}")

    # Save as SavedModel format
    try:
        savedmodel_path = models_path / f"{model_name}_savedmodel"
        
        # Vérifier si la méthode export existe (Keras 3)
        if hasattr(model, 'export'):
            model.export(str(savedmodel_path))
            logger.info(f"SavedModel exported to {savedmodel_path}")
        else:
            # Fallback pour Keras 2/TF
            model.save(str(savedmodel_path), save_format='tf')
            logger.info(f"SavedModel saved to {savedmodel_path}")
            
    except Exception as e:
        logger.warning(f"Could not save SavedModel: {e}")
        logger.info("Using only .keras and .h5 formats")

    # Export to ONNX if possible
    try:
        import tf2onnx
        onnx_path = models_path / f"{model_name}.onnx"

        spec = (tf.TensorSpec((None, 224, 224, 3), tf.float32, name="input"),)
        model_proto, _ = tf2onnx.convert.from_keras(
            model,
            input_signature=spec,
            output_path=str(onnx_path)
        )
        logger.info(f"ONNX model saved to {onnx_path}")
    except ImportError:
        logger.warning("tf2onnx not available. Skipping ONNX export.")

    # Save training summary
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
            "learning_rate": learning_rate
        },
        "final_metrics": metrics_dict,
        "environment": env_info,
        "timestamp": datetime.now().isoformat()
    }

    with open(output_path / "training_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    logger.info("=" * 60)
    logger.info("Training Complete!")
    logger.info(f"Model: {final_model_path}")
    logger.info(f"Accuracy: {metrics_dict.get('accuracy', 0):.4f}")
    logger.info("=" * 60)

    return summary


def main():
    """Main entry point for training script."""
    parser = argparse.ArgumentParser(
        description="Train Agricultural Classification Model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Train with default settings
  python train_model.py --dataset ./data/datasets/plantvillage

  # Train with custom settings
  python train_model.py --dataset ./data/datasets/plantvillage \\
      --backbone mobilenet --epochs 30 --batch-size 64

  # Quick test with mini dataset
  python train_model.py --dataset ./data/datasets/mini_dataset --epochs 5
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
        choices=['efficientnet', 'mobilenet'],
        default='efficientnet',
        help='Backbone architecture'
    )
    parser.add_argument(
        '--epochs', '-e',
        type=int,
        default=50,
        help='Number of training epochs'
    )
    parser.add_argument(
        '--fine-tune-epochs',
        type=int,
        default=20,
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
        logger.info("Run 'python ml/download_datasets.py --download mini_dataset' to create a test dataset")
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
            fine_tune_epochs=args.fine_tune_epochs
        )

        # Print summary
        print("\n" + "=" * 60)
        print("TRAINING SUMMARY")
        print("=" * 60)
        print(f"Model: {summary['model_name']}")
        print(f"Classes: {summary['num_classes']}")
        print(f"Final Accuracy: {summary['final_metrics'].get('accuracy', 0):.4f}")
        print(f"Files saved to: {args.output}")
        print("=" * 60)

    except Exception as e:
        logger.error(f"Training failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()