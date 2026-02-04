#!/usr/bin/env python3
"""
Dataset Download Script - Universal Dataset Manager
Downloads and prepares datasets for training from multiple sources.
Compatible with: Google Colab, Kaggle, Local (Windows/Mac/Linux)
"""

import os
import sys
import json
import hashlib
import zipfile
import tarfile
import shutil
import logging
import random
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from urllib.request import urlretrieve
from urllib.error import URLError
import argparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# Dataset Configuration
# ============================================================================

DATASETS = {
    "plantvillage": {
        "name": "PlantVillage Dataset",
        "description": "38 classes of plant diseases",
        "source": "kaggle",
        "kaggle_dataset": "emmarex/plantdisease",
        "size_mb": 2500,
        "classes": 38,
        "images": 54303,
        "expected_structure": "PlantVillage/",
        "structure_variants": ["PlantVillage/", "Plant_Village/", "PlantVillage", "Plant_Village"],
        "use_for": ["health", "species"],
        "recommended_classes": [
            "Tomato___healthy", "Tomato___Late_blight", 
            "Tomato___Early_blight", "Potato___healthy",
            "Potato___Late_blight", "Corn___healthy",
            "Corn___Northern_Leaf_Blight", "Grape___healthy",
            "Grape___Black_rot", "Apple___healthy",
            "Apple___Apple_scab"
        ]
    },
    "plant_seedlings": {
        "name": "Plant Seedlings Dataset",
        "description": "12 species of plant seedlings",
        "source": "kaggle",
        "kaggle_dataset": "vbookshelf/v2-plant-seedlings-dataset",
        "size_mb": 800,
        "classes": 12,
        "images": 5539,
        "expected_structure": "nonsegmentedv2/",
        "structure_variants": ["nonsegmentedv2/", "nonsegmentedv2", "plant-seedlings-dataset/"],
        "use_for": ["species", "growth_stage"],
        "recommended_classes": [
            "Black-grass", "Charlock", "Cleavers", "Common Chickweed",
            "Common wheat", "Fat Hen", "Loose Silky-bent", "Maize",
            "Scentless Mayweed", "Shepherds Purse", "Small-flowered Cranesbill", "Sugar beet"
        ]
    },
    "crop_diseases": {
        "name": "Crop Disease Dataset",
        "description": "Multiple crop diseases",
        "source": "kaggle",
        "kaggle_dataset": "vipoooool/new-plant-diseases-dataset",
        "size_mb": 3000,
        "classes": 38,
        "images": 87000,
        "expected_structure": "New Plant Diseases Dataset(Augmented)/",
        "structure_variants": [
            "New Plant Diseases Dataset(Augmented)/", 
            "new-plant-diseases-dataset/",
            "New_Plant_Diseases_Dataset/",
            "dataset/"
        ],
        "use_for": ["health", "species"],
        "recommended_classes": [
            "Apple___Apple_scab", "Apple___Black_rot", "Apple___Cedar_apple_rust",
            "Apple___healthy", "Background_without_leaves", "Blueberry___healthy",
            "Cherry___healthy", "Cherry___Powdery_mildew", "Corn___Cercospora_leaf_spot",
            "Corn___Common_rust", "Corn___healthy", "Corn___Northern_Leaf_Blight",
            "Grape___Black_rot", "Grape___Esca_(Black_Measles)", "Grape___healthy",
            "Grape___Leaf_blight_(Isariopsis_Leaf_Spot)", "Orange___Haunglongbing_(Citrus_greening)",
            "Peach___Bacterial_spot", "Peach___healthy", "Pepper,_bell___Bacterial_spot",
            "Pepper,_bell___healthy", "Potato___Early_blight", "Potato___healthy",
            "Potato___Late_blight", "Raspberry___healthy", "Soybean___healthy",
            "Squash___Powdery_mildew", "Strawberry___healthy", "Strawberry___Leaf_scorch",
            "Tomato___Bacterial_spot", "Tomato___Early_blight", "Tomato___healthy",
            "Tomato___Late_blight", "Tomato___Leaf_Mold", "Tomato___Septoria_leaf_spot",
            "Tomato___Spider_mites Two-spotted_spider_mite", "Tomato___Target_Spot",
            "Tomato___Tomato_mosaic_virus", "Tomato___Tomato_Yellow_Leaf_Curl_Virus"
        ]
    },
    "combined_dataset": {
        "name": "Combined Agriculture Dataset",
        "description": "Combined dataset from multiple sources for general model",
        "source": "combined",
        "size_mb": 5000,
        "classes": 25,
        "images": 50000,
        "use_for": ["all"]
    }
}


class DatasetManager:
    """
    Universal dataset manager with improved structure detection.
    """

    def __init__(self, base_path: Optional[str] = None, cache_path: Optional[str] = None):
        """
        Initialize dataset manager.
        """
        self.base_path = Path(base_path or "./data/datasets")
        self.cache_path = Path(cache_path or "./data/cache")
        self.environment = self._detect_environment()

        # Create directories
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.cache_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Dataset Manager initialized")
        logger.info(f"Environment: {self.environment}")
        logger.info(f"Dataset path: {self.base_path}")
        logger.info(f"Cache path: {self.cache_path}")

    def _detect_environment(self) -> str:
        """Detect the current execution environment."""
        try:
            import google.colab
            return "colab"
        except ImportError:
            pass

        if os.environ.get("KAGGLE_KERNEL_RUN_TYPE"):
            return "kaggle"

        if os.environ.get("CODESPACES"):
            return "codespaces"

        return "local"

    def _setup_kaggle_credentials(self) -> bool:
        """Setup Kaggle API credentials."""
        kaggle_dir = Path.home() / ".kaggle"
        kaggle_json = kaggle_dir / "kaggle.json"

        if kaggle_json.exists():
            logger.info("Kaggle credentials found")
            return True

        kaggle_username = os.environ.get("KAGGLE_USERNAME")
        kaggle_key = os.environ.get("KAGGLE_KEY")

        if kaggle_username and kaggle_key:
            kaggle_dir.mkdir(parents=True, exist_ok=True)
            with open(kaggle_json, 'w') as f:
                json.dump({
                    "username": kaggle_username,
                    "key": kaggle_key
                }, f)
            os.chmod(kaggle_json, 0o600)
            logger.info("Kaggle credentials configured from environment")
            return True

        # Colab-specific
        if self.environment == "colab":
            try:
                from google.colab import userdata
                kaggle_username = userdata.get('KAGGLE_USERNAME')
                kaggle_key = userdata.get('KAGGLE_KEY')
                if kaggle_username and kaggle_key:
                    kaggle_dir.mkdir(parents=True, exist_ok=True)
                    with open(kaggle_json, 'w') as f:
                        json.dump({
                            "username": kaggle_username,
                            "key": kaggle_key
                        }, f)
                    os.chmod(kaggle_json, 0o600)
                    logger.info("Kaggle credentials configured from Colab secrets")
                    return True
            except Exception:
                pass

        logger.warning("Kaggle credentials not found.")
        return False

    def _count_images_in_dir(self, directory: Path) -> Tuple[int, Dict[str, int]]:
        """
        Count images in a directory using multiple methods.
        
        Returns:
            Tuple: (total_images, class_counts)
        """
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.JPG', '.PNG', '.JPEG', '.tiff', '.tif'}
        total_images = 0
        class_counts = {}
        
        # Method 1: Check subdirectories for classes
        for item in directory.iterdir():
            if item.is_dir():
                # Count images in this class directory
                class_images = []
                for ext in image_extensions:
                    class_images.extend(list(item.glob(f"*{ext}")))
                    class_images.extend(list(item.glob(f"*{ext.upper()}")))
                
                if class_images:
                    class_counts[item.name] = len(class_images)
                    total_images += len(class_images)
        
        # Method 2: If no images found, search recursively
        if total_images == 0:
            for root, dirs, files in os.walk(directory):
                root_path = Path(root)
                # Count images in the current directory
                current_images = []
                for ext in image_extensions:
                    current_images.extend(list(root_path.glob(f"*{ext}")))
                    current_images.extend(list(root_path.glob(f"*{ext.upper()}")))
                
                if current_images:
                    # Use the last part of the path as class name
                    class_name = root_path.name
                    if class_name not in class_counts:
                        class_counts[class_name] = 0
                    class_counts[class_name] += len(current_images)
                    total_images += len(current_images)
        
        return total_images, class_counts

    def _find_dataset_structure(self, directory: Path, expected_name: str) -> Optional[Path]:
        """
        Find the main dataset structure using multiple methods.
        
        Args:
            directory: Répertoire à scanner
            expected_name: Nom attendu du dataset
            
        Returns:
            Road to the main dataset structure or None
        """
        logger.info(f"Finding dataset structure in: {directory}")
        
        # Méthode 1: Chercher le nom attendu
        if expected_name:
            expected_path = directory / expected_name
            if expected_path.exists():
                logger.info(f"Structure found (method 1): {expected_path}")
                return expected_path
        
        # MMethod 2: Search in subdirectories
        for item in directory.iterdir():
            if item.is_dir():
                # Verify if this directory contains images or subdirectories with images
                has_images = False
                has_subdirs = False
                
                for subitem in item.iterdir():
                    if subitem.is_dir():
                        has_subdirs = True
                    elif subitem.suffix.lower() in {'.jpg', '.jpeg', '.png', '.bmp', '.gif'}:
                        has_images = True
                
                if has_images or has_subdirs:
                    logger.info(f"Structure found (method 2): {item}")
                    return item
        
        # Method 3: Check if images are directly in the root
        has_images_in_root = any(
            item.suffix.lower() in {'.jpg', '.jpeg', '.png', '.bmp', '.gif'}
            for item in directory.iterdir()
            if item.is_file()
        )
        
        if has_images_in_root:
            logger.info(f"Structure found (method 3): root of dataset")
            return directory
        
        # MMethod 4: Recursive search to find the first directory containing images
        for root, dirs, files in os.walk(directory):
            root_path = Path(root)
            if any(f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.gif')) for f in files):
                logger.info(f"Structure found (method 4): {root_path}")
                return root_path

        logger.warning("No dataset structure found")
        return None

    def download_kaggle_dataset(self, dataset_name: str, config: Dict) -> bool:
        """Download dataset from Kaggle with improved structure handling."""
        if not self._setup_kaggle_credentials():
            logger.error("Kaggle credentials required for this dataset")
            return False

        try:
            from kaggle.api.kaggle_api_extended import KaggleApi

            api = KaggleApi()
            api.authenticate()

            kaggle_dataset = config["kaggle_dataset"]
            download_path = self.cache_path / dataset_name
            final_path = self.base_path / dataset_name

            logger.info(f"Downloading {config['name']} from Kaggle...")
            logger.info(f"Dataset: {kaggle_dataset}")
            logger.info(f"Expected size: ~{config['size_mb']} MB")

            # Clean existing
            if download_path.exists():
                shutil.rmtree(download_path)
            if final_path.exists():
                shutil.rmtree(final_path)

            # Download and extract
            api.dataset_download_files(
                kaggle_dataset,
                path=str(download_path),
                unzip=True
            )

            # Try to find the correct structure
            success = False

            # MMethod 1: Expected structure specified in config
            expected_structure = config.get("expected_structure", "")
            if expected_structure:
                # Try different variants
                structure_variants = config.get("structure_variants", [expected_structure])
                structure_variants.append("")  # Add an empty string for the case where
            
                for variant in structure_variants:
                    if variant:
                        potential_path = download_path / variant.rstrip('/')
                        if potential_path.exists():
                            logger.info(f"Structure found with variant: {variant}")
                            shutil.move(str(potential_path), str(final_path))
                            success = True
                            break

            # MMethod 2: If method 1 fails, search automatically
            if not success:
                found_structure = self._find_dataset_structure(download_path, expected_structure)
                if found_structure and found_structure != download_path:
                    logger.info(f"Structure found automatically: {found_structure}")
                    shutil.move(str(found_structure), str(final_path))
                    success = True

            # MMethod 3: Use all content from the download directory
            if not success:
                logger.info("Using the complete download directory")
                shutil.move(str(download_path), str(final_path))
                success = True

            # Cleanup
            if download_path.exists():
                shutil.rmtree(download_path)

            if success:
                logger.info(f"Dataset saved to {final_path}")
                
                # Verify if dataset content images
                total_images, class_counts = self._count_images_in_dir(final_path)
                if total_images > 0:
                    logger.info(f"Dataset verification: {total_images} images found in {len(class_counts)} classes")
                else:
                    logger.warning(f"Dataset verification: No images found in {final_path}")
                    # Try to find images recursively
                    logger.info("Falling back to recursive search for images...")
                    
                    # Find and extract any archives
                    for item in final_path.rglob("*"):
                        if item.suffix.lower() in {'.zip', '.tar', '.gz', '.tgz'}:
                            logger.info(f"Archive found: {item}, attempting extraction...")
                            try:
                                if item.suffix == '.zip':
                                    with zipfile.ZipFile(item, 'r') as zip_ref:
                                        extract_dir = item.parent / f"{item.stem}_extracted"
                                        zip_ref.extractall(extract_dir)
                                        logger.info(f"Archive extraite dans: {extract_dir}")
                                elif item.suffix in {'.tar', '.gz', '.tgz'}:
                                    with tarfile.open(item, 'r:*') as tar_ref:
                                        extract_dir = item.parent / f"{item.stem}_extracted"
                                        tar_ref.extractall(extract_dir)
                                        logger.info(f"Archive extraite dans: {extract_dir}")
                                
                                # Verify if extraction yielded images
                                total_images, class_counts = self._count_images_in_dir(final_path)
                                if total_images > 0:
                                    logger.info(f"After extraction: {total_images} images found")
                            except Exception as e:
                                logger.error(f"Error during extraction: {e}")

            return success

        except ImportError:
            logger.error("Kaggle package not installed. Run: pip install kaggle")
            return False
        except Exception as e:
            logger.error(f"Kaggle download failed: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def create_balanced_mini_dataset(
        self, 
        dataset_name: str,
        images_per_class: int = 2000,
        max_total_images: int = 10000
    ) -> bool:
        """
        Creates a balanced mini dataset from downloaded datasets.
        
        Args:
            dataset_name: Name of the dataset to create (mini_dataset or combined_dataset)
            images_per_class: Number of images per class (if specified)
            max_total_images: Maximum total number of images
        """
        logger.info(f"Creating balanced mini dataset: {dataset_name}")
        
        mini_path = self.base_path / dataset_name
        if mini_path.exists():
            shutil.rmtree(mini_path)
        mini_path.mkdir(parents=True, exist_ok=True)
        
        # Determine source datasets
        source_datasets = []
        if dataset_name == "mini_dataset":
            # For mini_dataset, prioritize PlantVillage
            plantvillage_path = self.base_path / "plantvillage"
            if plantvillage_path.exists():
                source_datasets.append(("plantvillage", plantvillage_path))
            else:
                logger.warning("plantvillage dataset not found. Trying other datasets...")
                # Try other datasets
                for ds_name in ["crop_diseases", "plant_seedlings"]:
                    ds_path = self.base_path / ds_name
                    if ds_path.exists():
                        source_datasets.append((ds_name, ds_path))
                        break
        else:
            # For combined_dataset, use all available datasets
            for ds_name, config in DATASETS.items():
                if ds_name not in ["mini_dataset", "combined_dataset"]:
                    ds_path = self.base_path / ds_name
                    if ds_path.exists():
                        source_datasets.append((ds_name, ds_path))
        
        if not source_datasets:
            logger.error("No source datasets found. Please download datasets first.")
            return False
        
        # Collect all classes from source datasets
        all_classes = {}
        for ds_name, ds_path in source_datasets:
            total_images, class_counts = self._count_images_in_dir(ds_path)
            if total_images > 0:
                logger.info(f"Found {total_images} images in {len(class_counts)} classes in {ds_name}")
                for class_name, count in class_counts.items():
                    if class_name not in all_classes:
                        all_classes[class_name] = []
                    # Store the source dataset path
                    all_classes[class_name].append((ds_name, ds_path))
            else:
                logger.warning(f"No images found in {ds_name}")
        
        # Select the best classes
        if dataset_name == "mini_dataset":
            # For mini_dataset, select up to 5 classes prioritizing diseases and healthy
            selected_classes = []
            # Prioritize healthy and disease classes
            for class_name in all_classes.keys():
                if "healthy" in class_name.lower():
                    selected_classes.append(class_name)
                elif any(disease in class_name.lower() for disease in ["blight", "rot", "spot", "mildew"]):
                    selected_classes.append(class_name)
            
            # Take only up to 5 classes
            selected_classes = selected_classes[:5]
            if len(selected_classes) < 5:
                # Add more classes if needed
                for class_name in all_classes.keys():
                    if class_name not in selected_classes:
                        selected_classes.append(class_name)
                    if len(selected_classes) >= 5:
                        break
        else:
            # For combined_dataset, select up to 25 classes
            selected_classes = list(all_classes.keys())[:25]
        
        logger.info(f"Selected {len(selected_classes)} classes: {selected_classes}")
        
        # Calculate the number of images per class
        if dataset_name == "mini_dataset":
            images_per_class = min(2000, max_total_images // len(selected_classes))
        else:
            images_per_class = min(2000, max_total_images // len(selected_classes))
        
        # Copy the images for each selected class
        total_copied = 0
        try:
            from PIL import Image
            PIL_AVAILABLE = True
        except ImportError:
            PIL_AVAILABLE = False
            logger.warning("PIL not available. Cannot verify images.")
        
        for class_name in selected_classes:
            class_path = mini_path / class_name
            class_path.mkdir(parents=True, exist_ok=True)
            
            # Find source datasets for this class
            source_info = all_classes.get(class_name, [])
            images_copied = 0
            
            for ds_name, ds_path in source_info:
                if images_copied >= images_per_class:
                    break
                
                # Find images in this dataset for the class
                for root, dirs, files in os.walk(ds_path):
                    root_path = Path(root)
                    if root_path.name == class_name or class_name in root_path.parts:
                        # This directory contains the class
                        image_files = []
                        for ext in ['.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG']:
                            image_files.extend(list(root_path.glob(f"*{ext}")))
                            image_files.extend(list(root_path.glob(f"*{ext.upper()}")))
                        
                        # Shuffle and take a subset
                        random.shuffle(image_files)
                        for img_path in image_files[:images_per_class - images_copied]:
                            try:
                                # Verify image validity
                                if PIL_AVAILABLE:
                                    with Image.open(img_path) as img:
                                        img.verify()
                                
                                # Copy the image
                                dest_path = class_path / f"{ds_name}_{img_path.name}"
                                shutil.copy2(img_path, dest_path)
                                images_copied += 1
                                total_copied += 1
                                
                                if images_copied >= images_per_class:
                                    break
                            except Exception as e:
                                logger.debug(f"Invalid image {img_path}: {e}")
                                continue
                
                if images_copied >= images_per_class:
                    break
            
            logger.info(f"Class {class_name}: copied {images_copied} images")
        
        logger.info(f"Balanced mini dataset created at {mini_path}")
        logger.info(f"Total images: {total_copied}")
        logger.info(f"Classes: {len(selected_classes)}")
        
        return True

    def verify_dataset(self, dataset_name: str, verbose: bool = True) -> Dict[str, Any]:
        """
        Verify dataset integrity and structure with multiple methods.
        
        Returns:
            Dictionary with verification results
        """
        dataset_path = self.base_path / dataset_name

        if not dataset_path.exists():
            logger.error(f"Dataset not found: {dataset_path}")
            return {"exists": False, "total_images": 0, "num_classes": 0}

        # Use the improved counting method
        total_images, class_counts = self._count_images_in_dir(dataset_path)
        
        # Obtain a list of all image files
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.JPG', '.PNG', '.JPEG'}
        all_files = []
        for ext in image_extensions:
            all_files.extend(list(dataset_path.rglob(f"*{ext}")))
            all_files.extend(list(dataset_path.rglob(f"*{ext.upper()}")))
        
        # Limit at 100 files for display
        display_files = [str(f) for f in all_files[:100]]

        result = {
            "exists": True,
            "path": str(dataset_path),
            "total_images": total_images,
            "num_classes": len(class_counts),
            "classes": class_counts,
            "files": display_files,
            "all_files_count": len(all_files)
        }

        if verbose:
            logger.info(f"Dataset: {dataset_name}")
            logger.info(f"Path: {dataset_path}")
            logger.info(f"Total images: {total_images}")
            logger.info(f"Classes: {len(class_counts)}")
            
            if class_counts:
                for class_name, count in sorted(class_counts.items()):
                    logger.info(f"  {class_name}: {count} images")
            else:
                logger.warning("No classes found!")
            
            # Display directory structure if no images found
            if total_images == 0:
                logger.info("\nDirectory structure (top 3 levels):")
                for i, item in enumerate(dataset_path.rglob("*")):
                    if i < 20:  # Limit display to first 20 items
                        rel_path = item.relative_to(dataset_path)
                        if item.is_dir():
                            logger.info(f"  DIR: {rel_path}")
                        else:
                            logger.info(f"  FILE: {rel_path}")
                
                # Check if there are any archive files
                archives = list(dataset_path.rglob("*.zip")) + list(dataset_path.rglob("*.tar")) + \
                          list(dataset_path.rglob("*.gz")) + list(dataset_path.rglob("*.tgz"))
                if archives:
                    logger.info(f"\nFound {len(archives)} archive files. You may need to extract them manually.")
                    for archive in archives[:5]:
                        logger.info(f"  Archive: {archive.relative_to(dataset_path)}")
            
            # Display sample files
            if all_files:
                logger.info("\nSample files (first 10):")
                for i, file_path in enumerate(all_files[:10]):
                    rel_path = Path(file_path).relative_to(dataset_path)
                    logger.info(f"  {i+1}. {rel_path}")
                if len(all_files) > 10:
                    logger.info(f"  ... and {len(all_files) - 10} more")

        return result

    def download_dataset(self, dataset_name: str, force: bool = False) -> bool:
        """
        Download a dataset by name.
        """
        if dataset_name not in DATASETS:
            logger.error(f"Unknown dataset: {dataset_name}")
            logger.info(f"Available datasets: {list(DATASETS.keys())}")
            return False

        config = DATASETS[dataset_name]
        dataset_path = self.base_path / dataset_name

        if dataset_path.exists() and not force:
            logger.info(f"Dataset {dataset_name} already exists at {dataset_path}")
            logger.info("Use --force to re-download")

            # Check if the dataset contains images
            verification = self.verify_dataset(dataset_name, verbose=False)
            if verification["total_images"] == 0:
                logger.warning("Dataset exists but contains 0 images. Consider using --force to re-download.")
            return True

        logger.info(f"\n{'=' * 60}")
        logger.info(f"Downloading: {config['name']}")
        logger.info(f"Description: {config['description']}")
        logger.info(f"Source: {config['source']}")
        logger.info(f"{'=' * 60}")

        source = config["source"]

        if source == "kaggle":
            success = self.download_kaggle_dataset(dataset_name, config)
        elif source == "combined":
            # For combined datasets, create balanced mini dataset
            success = self.create_balanced_mini_dataset(dataset_name, max_total_images=50000)
        else:
            logger.error(f"Unknown source type: {source}")
            return False

        # Verify after download
        if success:
            logger.info("Download completed. Verifying dataset...")
            verification = self.verify_dataset(dataset_name, verbose=True)
            
            if verification["total_images"] == 0:
                logger.warning("Dataset downloaded but no images found!")
                logger.info("Try extracting any zip/tar files in the dataset directory manually.")
                return False
            else:
                logger.info(f"✓ Dataset verified successfully with {verification['total_images']} images")
        
        return success

    def list_datasets(self, check_existing: bool = True) -> None:
        """List all available datasets with verification."""
        print("\n" + "=" * 70)
        print("Available Datasets")
        print("=" * 70)

        for name, config in DATASETS.items():
            dataset_path = self.base_path / name
            exists = dataset_path.exists()
            
            if exists and check_existing:
                # Verify the existing dataset
                verification = self.verify_dataset(name, verbose=False)
                actual_images = verification["total_images"]
                actual_classes = verification["num_classes"]
                status = "✓ Downloaded"
                details = f" ({actual_images} images, {actual_classes} classes)"
            elif exists:
                status = "✓ Downloaded"
                details = ""
            else:
                status = "○ Not downloaded"
                details = ""
            
            print(f"\n{name}")
            print(f"  Name: {config['name']}")
            print(f"  Description: {config['description']}")
            print(f"  Source: {config['source']}")
            print(f"  Size: ~{config['size_mb']} MB")
            print(f"  Expected Classes: {config.get('classes', 'N/A')}")
            print(f"  Expected Images: {config.get('images', 'N/A')}")
            print(f"  Status: {status}{details}")
            print(f"  Use for: {', '.join(config.get('use_for', []))}")

        print("\n" + "=" * 70)

    def download_all(self, exclude: Optional[List[str]] = None, 
                    create_mini_dataset: bool = True) -> Dict[str, bool]:
        """
        Download all datasets.
        
        Args:
            exclude: List of datasets to exclude
            create_mini_dataset: Whether to create mini dataset at the end
        """
        exclude = exclude or []
        results = {}
        
        logger.info("Starting download of all datasets...")

        # Download before first three datasets
        for name in ["plantvillage", "crop_diseases", "plant_seedlings"]:
            if name in exclude:
                logger.info(f"Skipping {name} (excluded)")
                continue
                
            logger.info(f"\n{'='*40}")
            logger.info(f"Processing: {name}")
            logger.info(f"{'='*40}")
            
            results[name] = self.download_dataset(name)
            
            if not results[name]:
                logger.error(f"Failed to download {name}")
        
        # Create combined dataset
        logger.info("\nCreating combined dataset...")
        results["combined_dataset"] = self.create_balanced_mini_dataset(
            "combined_dataset", 
            max_total_images=50000
        )
        
        # Create mini dataset
        if create_mini_dataset and "mini_dataset" not in exclude:
            logger.info("\nCreating mini dataset for testing...")
            results["mini_dataset"] = self.create_balanced_mini_dataset(
                "mini_dataset", 
                images_per_class=2000,
                max_total_images=10000
            )
        
        # Report summary
        logger.info("\n" + "="*40)
        logger.info("DOWNLOAD SUMMARY")
        logger.info("="*40)
        
        successful = [name for name, success in results.items() if success]
        failed = [name for name, success in results.items() if not success]
        
        if successful:
            logger.info(f"Successfully downloaded/created: {', '.join(successful)}")
        if failed:
            logger.error(f"Failed to download/create: {', '.join(failed)}")
        
        return results

    def get_dataset_path(self, dataset_name: str, use_full_dataset: bool = False) -> Path:
        """
        Get the path to use for training.
        
        Args:
            dataset_name: Name of the dataset
            use_full_dataset: If True, use the full dataset instead of mini
            
        Returns:
            Path to the dataset to use
        """
        if use_full_dataset and dataset_name != "mini_dataset":
            return self.base_path / dataset_name
        elif dataset_name == "mini_dataset":
            return self.base_path / "mini_dataset"
        else:
            # For compatibility, check if mini exists
            mini_path = self.base_path / "mini_dataset"
            if mini_path.exists():
                logger.info(f"Using mini dataset for quick testing")
                return mini_path
            else:
                return self.base_path / dataset_name


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Improved Dataset Manager for Drone AI Agriculture",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python download_datasets.py --list
  python download_datasets.py --download plantvillage
  python download_datasets.py --download-all
  python download_datasets.py --download-all --no-mini-dataset
  python download_datasets.py --verify plantvillage
  python download_datasets.py --create-mini-dataset --images-per-class 1000
        """
    )

    parser.add_argument('--list', action='store_true',
                       help='List all available datasets with verification')
    parser.add_argument('--download', type=str,
                       help='Download a specific dataset')
    parser.add_argument('--download-all', action='store_true',
                       help='Download all datasets')
    parser.add_argument('--no-mini-dataset', action='store_true',
                       help='Do not create mini dataset when using --download-all')
    parser.add_argument('--verify', type=str,
                       help='Verify a dataset')
    parser.add_argument('--create-mini-dataset', action='store_true',
                       help='Create balanced mini dataset from existing datasets')
    parser.add_argument('--images-per-class', type=int, default=2000,
                       help='Images per class for mini dataset')
    parser.add_argument('--force', action='store_true',
                       help='Force re-download')
    parser.add_argument('--base-path', type=str, default='./data/datasets',
                       help='Base path for datasets')
    parser.add_argument('--cache-path', type=str, default='./data/cache',
                       help='Cache path for downloads')

    args = parser.parse_args()

    # Initialize manager
    manager = DatasetManager(
        base_path=args.base_path,
        cache_path=args.cache_path
    )

    if args.list:
        manager.list_datasets(check_existing=True)
    elif args.download:
        success = manager.download_dataset(args.download, force=args.force)
        sys.exit(0 if success else 1)
    elif args.download_all:
        results = manager.download_all(create_mini_dataset=not args.no_mini_dataset)
        failed = [name for name, success in results.items() if not success]
        if failed:
            logger.error(f"Failed to download: {failed}")
            sys.exit(1)
    elif args.verify:
        result = manager.verify_dataset(args.verify, verbose=True)
        sys.exit(0 if result["exists"] and result["total_images"] > 0 else 1)
    elif args.create_mini_dataset:
        success = manager.create_balanced_mini_dataset(
            "mini_dataset",
            images_per_class=args.images_per_class,
            max_total_images=args.images_per_class * 5
        )
        sys.exit(0 if success else 1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()