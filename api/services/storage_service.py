"""
Storage Service for managing image uploads and file storage.
Supports local filesystem, S3, and MinIO backends.
"""

import os
import uuid
import hashlib
import logging
from datetime import datetime
from typing import Optional, Tuple
from io import BytesIO
from PIL import Image

# S3/MinIO imports with fallback
try:
    import boto3
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

try:
    from minio import Minio
    MINIO_AVAILABLE = True
except ImportError:
    MINIO_AVAILABLE = False

from api.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class StorageService:
    """
    Storage service for managing file uploads.

    Supports multiple backends:
    - local: Local filesystem storage
    - s3: Amazon S3 storage
    - minio: MinIO object storage
    """

    def __init__(self):
        """Initialize storage service based on configuration."""
        self.storage_type = settings.storage_type
        self.s3_client = None
        self.minio_client = None

        if self.storage_type == "s3" and BOTO3_AVAILABLE:
            self._init_s3()
        elif self.storage_type == "minio" and MINIO_AVAILABLE:
            self._init_minio()
        elif self.storage_type == "local":
            self._init_local()
        else:
            logger.warning(f"Storage type '{self.storage_type}' not available, falling back to local")
            self.storage_type = "local"
            self._init_local()

    def _init_local(self):
        """Initialize local storage."""
        self.storage_path = settings.local_storage_path
        os.makedirs(self.storage_path, exist_ok=True)
        os.makedirs(os.path.join(self.storage_path, "thumbnails"), exist_ok=True)
        logger.info(f"Local storage initialized at {self.storage_path}")

    def _init_s3(self):
        """Initialize S3 client."""
        try:
            self.s3_client = boto3.client(
                's3',
                endpoint_url=settings.s3_endpoint_url,
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                region_name=settings.aws_region
            )
            self.bucket_name = settings.s3_bucket_name
            logger.info(f"S3 storage initialized with bucket {self.bucket_name}")
        except Exception as e:
            logger.error(f"Failed to initialize S3: {e}")
            self.storage_type = "local"
            self._init_local()

    def _init_minio(self):
        """Initialize MinIO client."""
        try:
            self.minio_client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure
            )
            self.bucket_name = settings.minio_bucket

            # Create bucket if it doesn't exist
            if not self.minio_client.bucket_exists(self.bucket_name):
                self.minio_client.make_bucket(self.bucket_name)

            logger.info(f"MinIO storage initialized with bucket {self.bucket_name}")
        except Exception as e:
            logger.error(f"Failed to initialize MinIO: {e}")
            self.storage_type = "local"
            self._init_local()

    def _generate_filename(self, original_filename: str) -> str:
        """Generate unique filename with timestamp."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        ext = os.path.splitext(original_filename)[1].lower() or ".jpg"
        return f"{timestamp}_{unique_id}{ext}"

    def _create_thumbnail(
        self,
        image_data: bytes,
        size: Tuple[int, int] = (200, 200)
    ) -> bytes:
        """Create thumbnail from image data."""
        image = Image.open(BytesIO(image_data))
        image.thumbnail(size, Image.Resampling.LANCZOS)

        # Convert to RGB if necessary
        if image.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if 'A' in image.mode else None)
            image = background

        output = BytesIO()
        image.save(output, format='JPEG', quality=85)
        return output.getvalue()

    def _calculate_hash(self, data: bytes) -> str:
        """Calculate SHA-256 hash of data."""
        return hashlib.sha256(data).hexdigest()

    async def save_image(
        self,
        image_data: bytes,
        original_filename: str = "image.jpg",
        create_thumbnail: bool = True
    ) -> Tuple[str, str, Optional[str]]:
        """
        Save image to storage.

        Args:
            image_data: Raw image bytes.
            original_filename: Original filename.
            create_thumbnail: Whether to create thumbnail.

        Returns:
            Tuple of (image_path, image_url, thumbnail_url)
        """
        filename = self._generate_filename(original_filename)
        thumbnail_url = None

        if self.storage_type == "local":
            return await self._save_local(image_data, filename, create_thumbnail)
        elif self.storage_type == "s3":
            return await self._save_s3(image_data, filename, create_thumbnail)
        elif self.storage_type == "minio":
            return await self._save_minio(image_data, filename, create_thumbnail)
        else:
            raise ValueError(f"Unknown storage type: {self.storage_type}")

    async def _save_local(
        self,
        image_data: bytes,
        filename: str,
        create_thumbnail: bool
    ) -> Tuple[str, str, Optional[str]]:
        """Save image to local filesystem."""
        # Save main image
        image_path = os.path.join(self.storage_path, filename)
        with open(image_path, 'wb') as f:
            f.write(image_data)

        # Generate URL (relative path for local)
        image_url = f"/uploads/{filename}"

        # Create thumbnail
        thumbnail_url = None
        if create_thumbnail:
            try:
                thumbnail_data = self._create_thumbnail(image_data)
                thumb_filename = f"thumb_{filename}"
                thumb_path = os.path.join(self.storage_path, "thumbnails", thumb_filename)
                with open(thumb_path, 'wb') as f:
                    f.write(thumbnail_data)
                thumbnail_url = f"/uploads/thumbnails/{thumb_filename}"
            except Exception as e:
                logger.warning(f"Failed to create thumbnail: {e}")

        logger.info(f"Image saved locally: {image_path}")
        return image_path, image_url, thumbnail_url

    async def _save_s3(
        self,
        image_data: bytes,
        filename: str,
        create_thumbnail: bool
    ) -> Tuple[str, str, Optional[str]]:
        """Save image to S3."""
        try:
            # Upload main image
            key = f"images/{filename}"
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=image_data,
                ContentType='image/jpeg'
            )

            # Generate URL
            image_url = f"https://{self.bucket_name}.s3.amazonaws.com/{key}"

            # Create and upload thumbnail
            thumbnail_url = None
            if create_thumbnail:
                try:
                    thumbnail_data = self._create_thumbnail(image_data)
                    thumb_key = f"thumbnails/thumb_{filename}"
                    self.s3_client.put_object(
                        Bucket=self.bucket_name,
                        Key=thumb_key,
                        Body=thumbnail_data,
                        ContentType='image/jpeg'
                    )
                    thumbnail_url = f"https://{self.bucket_name}.s3.amazonaws.com/{thumb_key}"
                except Exception as e:
                    logger.warning(f"Failed to create thumbnail: {e}")

            logger.info(f"Image saved to S3: {key}")
            return key, image_url, thumbnail_url

        except ClientError as e:
            logger.error(f"S3 upload failed: {e}")
            raise

    async def _save_minio(
        self,
        image_data: bytes,
        filename: str,
        create_thumbnail: bool
    ) -> Tuple[str, str, Optional[str]]:
        """Save image to MinIO."""
        try:
            # Upload main image
            key = f"images/{filename}"
            self.minio_client.put_object(
                self.bucket_name,
                key,
                BytesIO(image_data),
                len(image_data),
                content_type='image/jpeg'
            )

            # Generate URL
            protocol = "https" if settings.minio_secure else "http"
            image_url = f"{protocol}://{settings.minio_endpoint}/{self.bucket_name}/{key}"

            # Create and upload thumbnail
            thumbnail_url = None
            if create_thumbnail:
                try:
                    thumbnail_data = self._create_thumbnail(image_data)
                    thumb_key = f"thumbnails/thumb_{filename}"
                    self.minio_client.put_object(
                        self.bucket_name,
                        thumb_key,
                        BytesIO(thumbnail_data),
                        len(thumbnail_data),
                        content_type='image/jpeg'
                    )
                    thumbnail_url = f"{protocol}://{settings.minio_endpoint}/{self.bucket_name}/{thumb_key}"
                except Exception as e:
                    logger.warning(f"Failed to create thumbnail: {e}")

            logger.info(f"Image saved to MinIO: {key}")
            return key, image_url, thumbnail_url

        except Exception as e:
            logger.error(f"MinIO upload failed: {e}")
            raise

    async def get_image(self, image_path: str) -> Optional[bytes]:
        """
        Retrieve image from storage.

        Args:
            image_path: Path to the image.

        Returns:
            Image bytes or None if not found.
        """
        if self.storage_type == "local":
            full_path = os.path.join(self.storage_path, os.path.basename(image_path))
            if os.path.exists(full_path):
                with open(full_path, 'rb') as f:
                    return f.read()
            return None

        elif self.storage_type == "s3":
            try:
                response = self.s3_client.get_object(
                    Bucket=self.bucket_name,
                    Key=image_path
                )
                return response['Body'].read()
            except ClientError:
                return None

        elif self.storage_type == "minio":
            try:
                response = self.minio_client.get_object(self.bucket_name, image_path)
                data = response.read()
                response.close()
                response.release_conn()
                return data
            except Exception:
                return None

    async def delete_image(self, image_path: str) -> bool:
        """
        Delete image from storage.

        Args:
            image_path: Path to the image.

        Returns:
            True if deleted successfully.
        """
        if self.storage_type == "local":
            full_path = os.path.join(self.storage_path, os.path.basename(image_path))
            if os.path.exists(full_path):
                os.remove(full_path)
                return True
            return False

        elif self.storage_type == "s3":
            try:
                self.s3_client.delete_object(Bucket=self.bucket_name, Key=image_path)
                return True
            except ClientError:
                return False

        elif self.storage_type == "minio":
            try:
                self.minio_client.remove_object(self.bucket_name, image_path)
                return True
            except Exception:
                return False


# Singleton instance
_storage_service: Optional[StorageService] = None


def get_storage_service() -> StorageService:
    """Get or create Storage Service singleton."""
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service