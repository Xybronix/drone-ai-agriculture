"""
Data Augmentation utilities for agricultural image training.
Provides robust augmentation strategies for different scenarios.
"""

import random
from typing import Tuple, List, Optional
import numpy as np

try:
    import albumentations as A
    ALBUMENTATIONS_AVAILABLE = True
except ImportError:
    ALBUMENTATIONS_AVAILABLE = False

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


def get_training_augmentation(
    image_size: Tuple[int, int] = (224, 224),
    intensity: str = "medium"
) -> Optional[A.Compose]:
    """
    Get training augmentation pipeline.

    Args:
        image_size: Target image size (height, width)
        intensity: Augmentation intensity ('light', 'medium', 'heavy')

    Returns:
        Albumentations Compose pipeline
    """
    if not ALBUMENTATIONS_AVAILABLE:
        return None

    height, width = image_size

    base_transforms = [
        A.Resize(height, width),
        A.HorizontalFlip(p=0.5),
    ]

    if intensity == "light":
        augmentation_transforms = [
            A.RandomBrightnessContrast(brightness_limit=0.1, contrast_limit=0.1, p=0.3),
            A.GaussNoise(var_limit=(5.0, 20.0), p=0.2),
        ]
    elif intensity == "medium":
        augmentation_transforms = [
            A.ShiftScaleRotate(shift_limit=0.1, scale_limit=0.15, rotate_limit=15, p=0.5),
            A.RandomBrightnessContrast(brightness_limit=0.2, contrast_limit=0.2, p=0.5),
            A.HueSaturationValue(hue_shift_limit=10, sat_shift_limit=20, val_shift_limit=20, p=0.3),
            A.GaussNoise(var_limit=(10.0, 50.0), p=0.3),
            A.GaussianBlur(blur_limit=(3, 5), p=0.2),
        ]
    else:
        augmentation_transforms = [
            A.ShiftScaleRotate(shift_limit=0.15, scale_limit=0.2, rotate_limit=30, p=0.7),
            A.RandomBrightnessContrast(brightness_limit=0.3, contrast_limit=0.3, p=0.6),
            A.HueSaturationValue(hue_shift_limit=20, sat_shift_limit=30, val_shift_limit=30, p=0.5),
            A.OneOf([
                A.GaussNoise(var_limit=(10.0, 80.0)),
                A.ISONoise(color_shift=(0.01, 0.05), intensity=(0.1, 0.5)),
            ], p=0.4),
            A.OneOf([
                A.GaussianBlur(blur_limit=(3, 7)),
                A.MotionBlur(blur_limit=7),
            ], p=0.3),
            A.CLAHE(clip_limit=4.0, p=0.2),
            A.RandomShadow(shadow_roi=(0, 0.5, 1, 1), p=0.2),
        ]

    normalize_transforms = [
        A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225], max_pixel_value=255.0),
    ]

    return A.Compose(base_transforms + augmentation_transforms + normalize_transforms)


def get_validation_augmentation(image_size: Tuple[int, int] = (224, 224)) -> Optional[A.Compose]:
    """Get validation augmentation (resize and normalize only)."""
    if not ALBUMENTATIONS_AVAILABLE:
        return None

    height, width = image_size
    return A.Compose([
        A.Resize(height, width),
        A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225], max_pixel_value=255.0),
    ])


def get_agricultural_augmentation(image_size: Tuple[int, int] = (224, 224)) -> Optional[A.Compose]:
    """Agricultural-specific augmentation simulating real conditions."""
    if not ALBUMENTATIONS_AVAILABLE:
        return None

    height, width = image_size

    return A.Compose([
        A.Resize(height, width),
        A.HorizontalFlip(p=0.5),
        A.VerticalFlip(p=0.2),
        A.ShiftScaleRotate(shift_limit=0.1, scale_limit=0.15, rotate_limit=20, p=0.5),
        A.OneOf([
            A.HueSaturationValue(hue_shift_limit=15, sat_shift_limit=25, val_shift_limit=20, p=1.0),
            A.RGBShift(r_shift_limit=15, g_shift_limit=15, b_shift_limit=15, p=1.0),
        ], p=0.5),
        A.RandomBrightnessContrast(brightness_limit=0.25, contrast_limit=0.25, p=0.5),
        A.RandomShadow(shadow_roi=(0, 0.2, 1, 1), num_shadows_lower=1, num_shadows_upper=3, p=0.3),
        A.OneOf([
            A.GaussNoise(var_limit=(10.0, 40.0), p=1.0),
            A.ISONoise(color_shift=(0.01, 0.03), intensity=(0.1, 0.3), p=1.0),
        ], p=0.3),
        A.GaussianBlur(blur_limit=(3, 5), p=0.2),
        A.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225], max_pixel_value=255.0),
    ])


def mixup(image1: np.ndarray, label1: np.ndarray, image2: np.ndarray, label2: np.ndarray, alpha: float = 0.2):
    """Apply Mixup augmentation."""
    lam = np.random.beta(alpha, alpha)
    mixed_image = lam * image1 + (1 - lam) * image2
    mixed_label = lam * label1 + (1 - lam) * label2
    return mixed_image, mixed_label


def cutmix(image1: np.ndarray, label1: np.ndarray, image2: np.ndarray, label2: np.ndarray, alpha: float = 1.0):
    """Apply CutMix augmentation."""
    lam = np.random.beta(alpha, alpha)
    H, W, _ = image1.shape

    cut_rat = np.sqrt(1. - lam)
    cut_w = int(W * cut_rat)
    cut_h = int(H * cut_rat)

    cx = np.random.randint(W)
    cy = np.random.randint(H)

    bbx1 = np.clip(cx - cut_w // 2, 0, W)
    bby1 = np.clip(cy - cut_h // 2, 0, H)
    bbx2 = np.clip(cx + cut_w // 2, 0, W)
    bby2 = np.clip(cy + cut_h // 2, 0, H)

    mixed_image = image1.copy()
    mixed_image[bby1:bby2, bbx1:bbx2, :] = image2[bby1:bby2, bbx1:bbx2, :]

    lam = 1 - ((bbx2 - bbx1) * (bby2 - bby1) / (W * H))
    mixed_label = lam * label1 + (1 - lam) * label2

    return mixed_image, mixed_label


def create_tf_augmentation_layer(intensity: str = "medium"):
    """Create TensorFlow-native augmentation layer."""
    try:
        import tensorflow as tf
        from tensorflow.keras import layers

        if intensity == "light":
            return tf.keras.Sequential([
                layers.RandomFlip("horizontal"),
                layers.RandomBrightness(0.1),
            ])
        elif intensity == "medium":
            return tf.keras.Sequential([
                layers.RandomFlip("horizontal"),
                layers.RandomRotation(0.1),
                layers.RandomZoom(0.1),
                layers.RandomBrightness(0.2),
                layers.RandomContrast(0.2),
            ])
        else:
            return tf.keras.Sequential([
                layers.RandomFlip("horizontal"),
                layers.RandomFlip("vertical"),
                layers.RandomRotation(0.2),
                layers.RandomZoom(0.15),
                layers.RandomBrightness(0.3),
                layers.RandomContrast(0.3),
            ])
    except ImportError:
        return None