#!/usr/bin/env python3
"""
Drone AI Agriculture - Main Drone Controller
Raspberry Pi-based drone control and image acquisition system.
"""

import os
import sys
import time
import signal
import logging
import argparse
import threading
from datetime import datetime
from typing import Optional
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from drone.camera import CameraController
from drone.cloud_client import CloudClient
from drone.offline_queue import OfflineQueue
from drone.pixhawk import PixhawkController

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/var/log/drone-ai/drone.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)


class DroneController:
    """
    Main drone controller orchestrating all components.
    
    Components:
    - Camera: Image acquisition
    - Cloud Client: API communication
    - Offline Queue: Local storage when offline
    - Pixhawk: Flight controller interface
    """
    
    def __init__(
        self,
        api_url: str,
        api_key: str,
        drone_id: str = "drone-001",
        capture_interval: float = 5.0,
        field_id: Optional[str] = None
    ):
        """
        Initialize drone controller.
        
        Args:
            api_url: Cloud API URL
            api_key: API authentication key
            drone_id: Unique drone identifier
            capture_interval: Seconds between captures
            field_id: Optional field identifier
        """
        self.api_url = api_url
        self.api_key = api_key
        self.drone_id = drone_id
        self.capture_interval = capture_interval
        self.field_id = field_id
        
        self.running = False
        self.capture_thread: Optional[threading.Thread] = None
        self.sync_thread: Optional[threading.Thread] = None
        
        # Initialize components
        logger.info("Initializing drone components...")
        
        self.camera = CameraController()
        self.cloud_client = CloudClient(api_url, api_key, drone_id)
        self.offline_queue = OfflineQueue()
        self.pixhawk = PixhawkController()
        
        # Statistics
        self.stats = {
            "images_captured": 0,
            "images_sent": 0,
            "images_queued": 0,
            "errors": 0,
            "start_time": None
        }
        
        logger.info(f"Drone controller initialized: {drone_id}")
        
    def start(self):
        """Start the drone controller."""
        if self.running:
            logger.warning("Drone controller already running")
            return
            
        self.running = True
        self.stats["start_time"] = datetime.utcnow()
        
        logger.info("Starting drone controller...")
        
        # Initialize camera
        if not self.camera.initialize():
            logger.error("Failed to initialize camera")
            self.running = False
            return
            
        # Connect to Pixhawk
        if not self.pixhawk.connect():
            logger.warning("Pixhawk not connected - GPS data unavailable")
            
        # Start capture thread
        self.capture_thread = threading.Thread(
            target=self._capture_loop,
            name="CaptureThread",
            daemon=True
        )
        self.capture_thread.start()
        
        # Start sync thread (uploads queued images when online)
        self.sync_thread = threading.Thread(
            target=self._sync_loop,
            name="SyncThread",
            daemon=True
        )
        self.sync_thread.start()
        
        # Start heartbeat
        self._start_heartbeat()
        
        logger.info("Drone controller started successfully")
        
    def stop(self):
        """Stop the drone controller."""
        logger.info("Stopping drone controller...")
        self.running = False
        
        # Wait for threads to finish
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=5.0)
            
        if self.sync_thread and self.sync_thread.is_alive():
            self.sync_thread.join(timeout=5.0)
            
        # Cleanup
        self.camera.release()
        self.pixhawk.disconnect()
        self.offline_queue.close()
        
        # Log statistics
        self._log_statistics()
        
        logger.info("Drone controller stopped")
        
    def _capture_loop(self):
        """Main capture loop - runs in separate thread."""
        logger.info(f"Capture loop started (interval: {self.capture_interval}s)")
        
        while self.running:
            try:
                # Capture image
                image_data = self.camera.capture()
                
                if image_data is None:
                    logger.warning("Capture returned no data")
                    time.sleep(self.capture_interval)
                    continue
                    
                self.stats["images_captured"] += 1
                
                # Get GPS data if available
                gps_data = self.pixhawk.get_gps()
                
                # Prepare metadata
                metadata = {
                    "drone_id": self.drone_id,
                    "field_id": self.field_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "latitude": gps_data.get("latitude") if gps_data else None,
                    "longitude": gps_data.get("longitude") if gps_data else None,
                    "altitude": gps_data.get("altitude") if gps_data else None,
                }
                
                # Try to send to cloud
                if self.cloud_client.is_online():
                    success = self._send_to_cloud(image_data, metadata)
                    if success:
                        self.stats["images_sent"] += 1
                    else:
                        self._queue_image(image_data, metadata)
                else:
                    self._queue_image(image_data, metadata)
                    
            except Exception as e:
                logger.error(f"Capture loop error: {e}")
                self.stats["errors"] += 1
                
            # Wait for next capture
            time.sleep(self.capture_interval)
            
    def _send_to_cloud(self, image_data: bytes, metadata: dict) -> bool:
        """Send image to cloud API for analysis."""
        try:
            result = self.cloud_client.analyze_image(image_data, metadata)
            
            if result:
                logger.info(
                    f"Analysis complete: plant_detected={result.get('plant_detection', {}).get('detected')}, "
                    f"health={result.get('health_diagnosis', {}).get('status')}"
                )
                return True
            return False
            
        except Exception as e:
            logger.error(f"Cloud send failed: {e}")
            return False
            
    def _queue_image(self, image_data: bytes, metadata: dict):
        """Queue image for later upload."""
        try:
            self.offline_queue.add(image_data, metadata)
            self.stats["images_queued"] += 1
            logger.debug(f"Image queued. Queue size: {self.offline_queue.size()}")
        except Exception as e:
            logger.error(f"Queue error: {e}")
            
    def _sync_loop(self):
        """Sync loop - uploads queued images when online."""
        logger.info("Sync loop started")
        
        while self.running:
            try:
                # Check if online and have queued items
                if self.cloud_client.is_online() and self.offline_queue.size() > 0:
                    # Get oldest item from queue
                    item = self.offline_queue.get_oldest()
                    
                    if item:
                        image_data, metadata = item
                        success = self._send_to_cloud(image_data, metadata)
                        
                        if success:
                            self.offline_queue.remove_oldest()
                            self.stats["images_sent"] += 1
                            self.stats["images_queued"] -= 1
                            logger.info(f"Synced queued image. Remaining: {self.offline_queue.size()}")
                            
            except Exception as e:
                logger.error(f"Sync loop error: {e}")
                
            # Check every 10 seconds
            time.sleep(10)
            
    def _start_heartbeat(self):
        """Start heartbeat thread to maintain connection with cloud."""
        def heartbeat_loop():
            while self.running:
                try:
                    status = {
                        "drone_id": self.drone_id,
                        "status": "active",
                        "battery_level": self.pixhawk.get_battery_level(),
                        "queue_size": self.offline_queue.size(),
                        "images_captured": self.stats["images_captured"],
                        "location": self.pixhawk.get_gps()
                    }
                    self.cloud_client.send_heartbeat(status)
                except Exception as e:
                    logger.debug(f"Heartbeat error: {e}")
                    
                time.sleep(30)  # Every 30 seconds
                
        thread = threading.Thread(
            target=heartbeat_loop,
            name="HeartbeatThread",
            daemon=True
        )
        thread.start()
        
    def _log_statistics(self):
        """Log session statistics."""
        if self.stats["start_time"]:
            duration = datetime.utcnow() - self.stats["start_time"]
            
            logger.info("=" * 50)
            logger.info("SESSION STATISTICS")
            logger.info("=" * 50)
            logger.info(f"Duration: {duration}")
            logger.info(f"Images captured: {self.stats['images_captured']}")
            logger.info(f"Images sent: {self.stats['images_sent']}")
            logger.info(f"Images queued: {self.stats['images_queued']}")
            logger.info(f"Errors: {self.stats['errors']}")
            logger.info("=" * 50)
            
    def get_status(self) -> dict:
        """Get current drone status."""
        return {
            "drone_id": self.drone_id,
            "running": self.running,
            "online": self.cloud_client.is_online(),
            "queue_size": self.offline_queue.size(),
            "battery_level": self.pixhawk.get_battery_level(),
            "gps": self.pixhawk.get_gps(),
            "statistics": self.stats
        }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Drone AI Agriculture Controller",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--api-url',
        type=str,
        default=os.environ.get('API_URL', 'http://localhost:8000'),
        help='Cloud API URL'
    )
    parser.add_argument(
        '--api-key',
        type=str,
        default=os.environ.get('API_KEY', ''),
        help='API authentication key'
    )
    parser.add_argument(
        '--drone-id',
        type=str,
        default=os.environ.get('DRONE_ID', 'drone-001'),
        help='Drone identifier'
    )
    parser.add_argument(
        '--field-id',
        type=str,
        default=os.environ.get('FIELD_ID'),
        help='Field identifier'
    )
    parser.add_argument(
        '--interval',
        type=float,
        default=5.0,
        help='Capture interval in seconds'
    )
    parser.add_argument(
        '--simulate',
        action='store_true',
        help='Run in simulation mode (no real hardware)'
    )
    parser.add_argument(
        '--ai-backend',
        type=str,
        choices=['local', 'external', 'auto'],
        default=os.environ.get('AI_BACKEND', 'local'),
        help='AI backend: local (TensorFlow/ONNX), external (Plant.id API), or auto (fallback)'
    )
    
    args = parser.parse_args()
    
    # Create log directory
    os.makedirs('/var/log/drone-ai', exist_ok=True)
    
    # Set simulation mode
    if args.simulate:
        os.environ['DRONE_SIMULATE'] = '1'
        logger.info("Running in SIMULATION mode")
    
    # Create controller
    controller = DroneController(
        api_url=args.api_url,
        api_key=args.api_key,
        drone_id=args.drone_id,
        capture_interval=args.interval,
        field_id=args.field_id
    )
    
    # Handle shutdown signals
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}")
        controller.stop()
        sys.exit(0)
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start controller
    controller.start()
    
    # Keep main thread alive
    try:
        while controller.running:
            time.sleep(1)
    except KeyboardInterrupt:
        controller.stop()


if __name__ == "__main__":
    main()