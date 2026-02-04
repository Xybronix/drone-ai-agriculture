"""
Camera Controller for Raspberry Pi.
Handles image acquisition from Pi Camera or USB camera.
"""

import os
import io
import time
import logging
from typing import Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# Check for simulation mode
SIMULATE = os.environ.get('DRONE_SIMULATE', '0') == '1'

# Try to import picamera2 (Raspberry Pi)
PICAMERA_AVAILABLE = False
if not SIMULATE:
    try:
        from picamera2 import Picamera2
        PICAMERA_AVAILABLE = True
    except ImportError:
        pass

# Try to import OpenCV as fallback
CV2_AVAILABLE = False
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    pass

# PIL for image processing
try:
    from PIL import Image
    import numpy as np
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class CameraController:
    """
    Camera controller supporting multiple backends.

    Supported cameras:
    - Raspberry Pi Camera (picamera2)
    - USB Camera (OpenCV)
    - Simulation mode (synthetic images)
    """

    def __init__(
        self,
        resolution: Tuple[int, int] = (1920, 1080),
        fps: int = 30,
        camera_id: int = 0
    ):
        """
        Initialize camera controller.

        Args:
            resolution: Image resolution (width, height)
            fps: Frames per second
            camera_id: Camera device ID (for USB cameras)
        """
        self.resolution = resolution
        self.fps = fps
        self.camera_id = camera_id

        self.camera = None
        self.backend = None
        self.initialized = False

        # Capture settings
        self.jpeg_quality = 90
        self.auto_exposure = True
        self.exposure_time = None  # Auto

    def initialize(self) -> bool:
        """
        Initialize the camera.

        Returns:
            True if initialization successful
        """
        if SIMULATE:
            logger.info("Camera initialized in SIMULATION mode")
            self.backend = "simulation"
            self.initialized = True
            return True

        # Try Raspberry Pi Camera first
        if PICAMERA_AVAILABLE:
            try:
                self.camera = Picamera2()

                # Configure camera
                config = self.camera.create_still_configuration(
                    main={"size": self.resolution, "format": "RGB888"},
                    buffer_count=2
                )
                self.camera.configure(config)
                self.camera.start()

                # Wait for camera to warm up
                time.sleep(2)

                self.backend = "picamera2"
                self.initialized = True
                logger.info(f"Pi Camera initialized at {self.resolution}")
                return True

            except Exception as e:
                logger.warning(f"Pi Camera initialization failed: {e}")

        # Try OpenCV (USB camera)
        if CV2_AVAILABLE:
            try:
                self.camera = cv2.VideoCapture(self.camera_id)

                if not self.camera.isOpened():
                    raise RuntimeError("Failed to open camera")

                # Set resolution
                self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
                self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
                self.camera.set(cv2.CAP_PROP_FPS, self.fps)

                # Verify settings
                actual_width = int(self.camera.get(cv2.CAP_PROP_FRAME_WIDTH))
                actual_height = int(self.camera.get(cv2.CAP_PROP_FRAME_HEIGHT))

                self.backend = "opencv"
                self.initialized = True
                logger.info(f"USB Camera initialized at {actual_width}x{actual_height}")
                return True

            except Exception as e:
                logger.warning(f"OpenCV camera initialization failed: {e}")

        # Fall back to simulation
        logger.warning("No camera available, falling back to simulation")
        self.backend = "simulation"
        self.initialized = True
        return True

    def capture(self) -> Optional[bytes]:
        """
        Capture an image.

        Returns:
            JPEG image data as bytes, or None on failure
        """
        if not self.initialized:
            logger.error("Camera not initialized")
            return None

        try:
            if self.backend == "picamera2":
                return self._capture_picamera()
            elif self.backend == "opencv":
                return self._capture_opencv()
            else:
                return self._capture_simulation()

        except Exception as e:
            logger.error(f"Capture failed: {e}")
            return None

    def _capture_picamera(self) -> Optional[bytes]:
        """Capture using Pi Camera."""
        # Capture to numpy array
        array = self.camera.capture_array()

        # Convert to JPEG
        image = Image.fromarray(array)
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=self.jpeg_quality)

        return buffer.getvalue()

    def _capture_opencv(self) -> Optional[bytes]:
        """Capture using OpenCV."""
        ret, frame = self.camera.read()

        if not ret:
            logger.error("OpenCV capture failed")
            return None

        # Convert BGR to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Convert to JPEG
        image = Image.fromarray(frame_rgb)
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=self.jpeg_quality)

        return buffer.getvalue()

    def _capture_simulation(self) -> bytes:
        """Generate synthetic image for testing."""
        if not PIL_AVAILABLE:
            # Return minimal valid JPEG
            return b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9televsedede\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&\'()*456televsedede\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xff\xd9'

        import numpy as np

        # Create synthetic agricultural image
        width, height = 640, 480

        # Green field background
        image = np.zeros((height, width, 3), dtype=np.uint8)
        image[:, :] = [34, 139, 34]  # Forest green

        # Add some variation
        noise = np.random.randint(-20, 20, (height, width, 3), dtype=np.int16)
        image = np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        # Add timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Convert to PIL and add text
        pil_image = Image.fromarray(image)

        # Convert to JPEG
        buffer = io.BytesIO()
        pil_image.save(buffer, format='JPEG', quality=self.jpeg_quality)

        return buffer.getvalue()

    def set_exposure(self, exposure_time: Optional[int] = None):
        """
        Set camera exposure.

        Args:
            exposure_time: Exposure time in microseconds, None for auto
        """
        self.exposure_time = exposure_time

        if self.backend == "picamera2" and self.camera:
            if exposure_time:
                self.camera.set_controls({"ExposureTime": exposure_time})
            else:
                self.camera.set_controls({"AeEnable": True})

    def set_resolution(self, width: int, height: int):
        """Change camera resolution."""
        self.resolution = (width, height)

        if self.initialized:
            self.release()
            self.initialize()

    def get_info(self) -> dict:
        """Get camera information."""
        return {
            "backend": self.backend,
            "initialized": self.initialized,
            "resolution": self.resolution,
            "fps": self.fps,
            "jpeg_quality": self.jpeg_quality
        }

    def release(self):
        """Release camera resources."""
        if self.camera:
            if self.backend == "picamera2":
                try:
                    self.camera.stop()
                    self.camera.close()
                except Exception:
                    pass
            elif self.backend == "opencv":
                self.camera.release()

            self.camera = None

        self.initialized = False
        logger.info("Camera released")


class VideoStreamer:
    """Video streaming for real-time monitoring."""

    def __init__(self, camera: CameraController):
        """
        Initialize video streamer.

        Args:
            camera: Camera controller instance
        """
        self.camera = camera
        self.streaming = False
        self.frame_count = 0

    def generate_frames(self):
        """Generator for MJPEG streaming."""
        while self.streaming:
            frame = self.camera.capture()

            if frame:
                self.frame_count += 1
                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
                )

            time.sleep(1.0 / self.camera.fps)

    def start(self):
        """Start streaming."""
        self.streaming = True
        self.frame_count = 0

    def stop(self):
        """Stop streaming."""
        self.streaming = False