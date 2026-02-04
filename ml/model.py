"""
Multi-Task Agricultural Classification Model
Supports: Plant Detection, Species ID, Growth Stage, Health Diagnosis
"""

import os
import logging
from typing import Dict, List, Optional, Tuple, Any

import numpy as np

# TensorFlow imports with error handling
try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers, Model
    from tensorflow.keras.applications import (
        MobileNetV3Small,
        MobileNetV3Large,
        EfficientNetB0,
        EfficientNetB1,
        ResNet50V2
    )
    from tensorflow.keras.callbacks import (
        ModelCheckpoint,
        EarlyStopping,
        ReduceLROnPlateau,
        TensorBoard,
        CSVLogger
    )
    TF_AVAILABLE = True
except ImportError:
    TF_AVAILABLE = False
    logging.warning("TensorFlow not available. Model training will not work.")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# Model Configuration
# ============================================================================

MODEL_CONFIGS = {
    "mobilenet_v3_small": {
        "backbone": "MobileNetV3Small",
        "input_shape": (224, 224, 3),
        "weights": "imagenet",
        "trainable_layers": 50,  # Fine-tune last N layers
        "description": "Lightweight model for fast inference"
    },
    "mobilenet_v3_large": {
        "backbone": "MobileNetV3Large",
        "input_shape": (224, 224, 3),
        "weights": "imagenet",
        "trainable_layers": 100,
        "description": "Better accuracy, still efficient"
    },
    "efficientnet_b0": {
        "backbone": "EfficientNetB0",
        "input_shape": (224, 224, 3),
        "weights": "imagenet",
        "trainable_layers": 100,
        "description": "Best accuracy/efficiency trade-off"
    },
    "efficientnet_b1": {
        "backbone": "EfficientNetB1",
        "input_shape": (240, 240, 3),
        "weights": "imagenet",
        "trainable_layers": 150,
        "description": "Higher accuracy, more compute"
    }
}

# Task configurations
TASK_CONFIGS = {
    "plant_detection": {
        "num_classes": 2,  # plant / no_plant
        "activation": "softmax",
        "loss": "categorical_crossentropy",
        "metrics": ["accuracy"],
        "weight": 1.0
    },
    "species": {
        "num_classes": 16,  # Configurable
        "activation": "softmax",
        "loss": "categorical_crossentropy",
        "metrics": ["accuracy", "top_k_categorical_accuracy"],
        "weight": 1.0
    },
    "growth_stage": {
        "num_classes": 8,
        "activation": "softmax",
        "loss": "categorical_crossentropy",
        "metrics": ["accuracy"],
        "weight": 0.8
    },
    "health": {
        "num_classes": 9,
        "activation": "softmax",
        "loss": "categorical_crossentropy",
        "metrics": ["accuracy"],
        "weight": 1.2  # Higher weight for health detection
    }
}


class AgricultureModel:
    """
    Multi-task deep learning model for agricultural image analysis.

    Features:
    - Transfer learning with pretrained backbones
    - Multi-task learning with shared features
    - Task-specific heads for different classifications
    - Support for multiple model architectures
    """

    def __init__(
        self,
        model_type: str = "efficientnet_b0",
        tasks: Optional[List[str]] = None,
        custom_num_classes: Optional[Dict[str, int]] = None
    ):
        """
        Initialize the agriculture model.

        Args:
            model_type: Type of backbone model
            tasks: List of tasks to train for
            custom_num_classes: Override default number of classes per task
        """
        if not TF_AVAILABLE:
            raise RuntimeError("TensorFlow is required for model training")

        self.model_type = model_type
        self.config = MODEL_CONFIGS.get(model_type)

        if not self.config:
            raise ValueError(f"Unknown model type: {model_type}")

        self.tasks = tasks or list(TASK_CONFIGS.keys())
        self.task_configs = {t: TASK_CONFIGS[t].copy() for t in self.tasks}

        # Apply custom num_classes if provided
        if custom_num_classes:
            for task, num_classes in custom_num_classes.items():
                if task in self.task_configs:
                    self.task_configs[task]["num_classes"] = num_classes

        self.model: Optional[Model] = None
        self.input_shape = self.config["input_shape"]

        logger.info(f"AgricultureModel initialized")
        logger.info(f"Model type: {model_type}")
        logger.info(f"Input shape: {self.input_shape}")
        logger.info(f"Tasks: {self.tasks}")

    def _get_backbone(self) -> Model:
        """Get the pretrained backbone model."""
        backbone_name = self.config["backbone"]
        input_shape = self.config["input_shape"]
        weights = self.config["weights"]

        backbone_map = {
            "MobileNetV3Small": MobileNetV3Small,
            "MobileNetV3Large": MobileNetV3Large,
            "EfficientNetB0": EfficientNetB0,
            "EfficientNetB1": EfficientNetB1,
            "ResNet50V2": ResNet50V2
        }

        if backbone_name not in backbone_map:
            raise ValueError(f"Unknown backbone: {backbone_name}")

        backbone = backbone_map[backbone_name](
            input_shape=input_shape,
            include_top=False,
            weights=weights,
            pooling=None
        )

        # Freeze early layers, fine-tune later layers
        trainable_layers = self.config["trainable_layers"]
        for layer in backbone.layers[:-trainable_layers]:
            layer.trainable = False

        return backbone

    def _build_task_head(
        self,
        shared_features: layers.Layer,
        task_name: str,
        config: Dict
    ) -> layers.Layer:
        """Build a task-specific classification head."""
        x = layers.GlobalAveragePooling2D(name=f"{task_name}_gap")(shared_features)

        # Dropout for regularization
        x = layers.Dropout(0.3, name=f"{task_name}_dropout1")(x)

        # Dense layers
        x = layers.Dense(256, activation="relu", name=f"{task_name}_dense1")(x)
        x = layers.BatchNormalization(name=f"{task_name}_bn")(x)
        x = layers.Dropout(0.2, name=f"{task_name}_dropout2")(x)

        # Output layer
        output = layers.Dense(
            config["num_classes"],
            activation=config["activation"],
            name=f"{task_name}_output"
        )(x)

        return output

    def build(self) -> Model:
        """Build the complete multi-task model."""
        logger.info("Building model...")

        # Input layer
        inputs = layers.Input(shape=self.input_shape, name="input_image")

        # Data augmentation (applied during training only)
        x = layers.RandomFlip("horizontal", name="augment_flip")(inputs)
        x = layers.RandomRotation(0.15, name="augment_rotation")(x)
        x = layers.RandomZoom(0.1, name="augment_zoom")(x)
        x = layers.RandomBrightness(0.2, name="augment_brightness")(x)

        # Backbone
        backbone = self._get_backbone()
        shared_features = backbone(x)

        # Build task-specific heads
        outputs = {}
        for task_name in self.tasks:
            config = self.task_configs[task_name]
            outputs[task_name] = self._build_task_head(
                shared_features, task_name, config
            )

        # Create model
        self.model = Model(
            inputs=inputs,
            outputs=list(outputs.values()),
            name="agriculture_multitask_model"
        )

        logger.info(f"Model built successfully")
        logger.info(f"Total parameters: {self.model.count_params():,}")

        return self.model

    def compile(
        self,
        learning_rate: float = 1e-4,
        optimizer: str = "adam"
    ) -> None:
        """Compile the model with appropriate losses and metrics."""
        if self.model is None:
            raise RuntimeError("Model not built. Call build() first.")

        # Create optimizer
        if optimizer == "adam":
            opt = keras.optimizers.Adam(learning_rate=learning_rate)
        elif optimizer == "sgd":
            opt = keras.optimizers.SGD(learning_rate=learning_rate, momentum=0.9)
        elif optimizer == "adamw":
            opt = keras.optimizers.AdamW(learning_rate=learning_rate)
        else:
            raise ValueError(f"Unknown optimizer: {optimizer}")

        # Prepare losses and metrics for each task
        losses = {}
        metrics = {}
        loss_weights = {}

        for i, task_name in enumerate(self.tasks):
            config = self.task_configs[task_name]
            output_name = f"{task_name}_output"
            losses[output_name] = config["loss"]
            metrics[output_name] = config["metrics"]
            loss_weights[output_name] = config["weight"]

        self.model.compile(
            optimizer=opt,
            loss=losses,
            metrics=metrics,
            loss_weights=loss_weights
        )

        logger.info("Model compiled successfully")

    def get_callbacks(
        self,
        checkpoint_path: str = "./checkpoints",
        log_dir: str = "./logs",
        patience: int = 10
    ) -> List[keras.callbacks.Callback]:
        """Get training callbacks."""
        os.makedirs(checkpoint_path, exist_ok=True)
        os.makedirs(log_dir, exist_ok=True)

        callbacks = [
            # Save best model
            ModelCheckpoint(
                filepath=os.path.join(checkpoint_path, "best_model.h5"),
                monitor="val_loss",
                save_best_only=True,
                save_weights_only=False,
                verbose=1
            ),

            # Save checkpoints periodically
            ModelCheckpoint(
                filepath=os.path.join(checkpoint_path, "model_epoch_{epoch:02d}.h5"),
                save_freq="epoch",
                save_best_only=False,
                verbose=0
            ),

            # Early stopping
            EarlyStopping(
                monitor="val_loss",
                patience=patience,
                restore_best_weights=True,
                verbose=1
            ),

            # Learning rate reduction
            ReduceLROnPlateau(
                monitor="val_loss",
                factor=0.5,
                patience=5,
                min_lr=1e-7,
                verbose=1
            ),

            # TensorBoard logging
            TensorBoard(
                log_dir=log_dir,
                histogram_freq=1,
                update_freq="epoch"
            ),

            # CSV logging
            CSVLogger(
                os.path.join(log_dir, "training_log.csv"),
                separator=",",
                append=True
            )
        ]

        return callbacks

    def train(
        self,
        train_data,
        val_data,
        epochs: int = 50,
        batch_size: int = 32,
        callbacks: Optional[List] = None
    ) -> keras.callbacks.History:
        """
        Train the model.

        Args:
            train_data: Training data (tf.data.Dataset or generator)
            val_data: Validation data
            epochs: Number of training epochs
            batch_size: Batch size
            callbacks: Optional list of callbacks

        Returns:
            Training history
        """
        if self.model is None:
            raise RuntimeError("Model not built/compiled. Call build() and compile() first.")

        if callbacks is None:
            callbacks = self.get_callbacks()

        logger.info(f"Starting training for {epochs} epochs...")

        history = self.model.fit(
            train_data,
            validation_data=val_data,
            epochs=epochs,
            batch_size=batch_size,
            callbacks=callbacks,
            verbose=1
        )

        logger.info("Training completed")
        return history

    def evaluate(self, test_data) -> Dict[str, float]:
        """Evaluate the model on test data."""
        if self.model is None:
            raise RuntimeError("Model not built")

        results = self.model.evaluate(test_data, verbose=1)

        # Parse results
        metrics_dict = {}
        for metric_name, value in zip(self.model.metrics_names, results):
            metrics_dict[metric_name] = float(value)

        return metrics_dict

    def predict(self, image: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Make predictions on a single image or batch.

        Args:
            image: Image array of shape (H, W, 3) or (B, H, W, 3)

        Returns:
            Dictionary of predictions for each task
        """
        if self.model is None:
            raise RuntimeError("Model not built")

        # Add batch dimension if needed
        if image.ndim == 3:
            image = np.expand_dims(image, axis=0)

        # Normalize
        image = image.astype(np.float32) / 255.0

        # Predict
        predictions = self.model.predict(image, verbose=0)

        # Parse predictions
        results = {}
        if isinstance(predictions, list):
            for task_name, pred in zip(self.tasks, predictions):
                results[task_name] = pred
        else:
            results[self.tasks[0]] = predictions

        return results

    def save(self, path: str, format: str = "h5") -> None:
        """
        Save the model.

        Args:
            path: Save path
            format: Format ('h5', 'savedmodel', 'onnx')
        """
        if self.model is None:
            raise RuntimeError("Model not built")

        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)

        if format == "h5":
            self.model.save(path)
            logger.info(f"Model saved to {path}")

        elif format == "savedmodel":
            self.model.save(path, save_format="tf")
            logger.info(f"SavedModel saved to {path}")

        elif format == "onnx":
            self._save_onnx(path)

        else:
            raise ValueError(f"Unknown format: {format}")

    def _save_onnx(self, path: str) -> None:
        """Export model to ONNX format."""
        try:
            import tf2onnx
            import onnx

            # Convert to ONNX
            spec = (tf.TensorSpec(
                (None,) + self.input_shape,
                tf.float32,
                name="input_image"
            ),)

            onnx_model, _ = tf2onnx.convert.from_keras(
                self.model,
                input_signature=spec,
                output_path=path
            )

            logger.info(f"ONNX model saved to {path}")

        except ImportError:
            logger.error("tf2onnx not installed. Run: pip install tf2onnx")
            raise

    def load(self, path: str) -> None:
        """Load a saved model."""
        self.model = keras.models.load_model(path)
        logger.info(f"Model loaded from {path}")

    def summary(self) -> None:
        """Print model summary."""
        if self.model:
            self.model.summary()
        else:
            logger.warning("Model not built yet")


def create_data_generators(
    dataset_path: str,
    input_shape: Tuple[int, int] = (224, 224),
    batch_size: int = 32,
    validation_split: float = 0.2
) -> Tuple[Any, Any]:
    """
    Create data generators for training.

    Args:
        dataset_path: Path to dataset directory
        input_shape: Target image size
        batch_size: Batch size
        validation_split: Validation split ratio

    Returns:
        Tuple of (train_generator, validation_generator)
    """
    from tensorflow.keras.preprocessing.image import ImageDataGenerator

    # Training data augmentation
    train_datagen = ImageDataGenerator(
        rescale=1./255,
        rotation_range=20,
        width_shift_range=0.2,
        height_shift_range=0.2,
        shear_range=0.2,
        zoom_range=0.2,
        horizontal_flip=True,
        fill_mode='nearest',
        validation_split=validation_split
    )

    # Validation data (no augmentation except rescaling)
    val_datagen = ImageDataGenerator(
        rescale=1./255,
        validation_split=validation_split
    )

    train_generator = train_datagen.flow_from_directory(
        dataset_path,
        target_size=input_shape,
        batch_size=batch_size,
        class_mode='categorical',
        subset='training',
        shuffle=True
    )

    val_generator = val_datagen.flow_from_directory(
        dataset_path,
        target_size=input_shape,
        batch_size=batch_size,
        class_mode='categorical',
        subset='validation',
        shuffle=False
    )

    return train_generator, val_generator


# For direct usage
if __name__ == "__main__":
    # Example usage
    model = AgricultureModel(
        model_type="efficientnet_b0",
        tasks=["plant_detection", "species", "health"]
    )
    model.build()
    model.compile(learning_rate=1e-4)
    model.summary()