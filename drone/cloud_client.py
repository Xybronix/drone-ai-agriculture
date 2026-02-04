"""
Cloud API Client for drone communication.
Handles secure transmission of images and data to the cloud API.
"""

import os
import time
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# HTTP client imports
try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


class CloudClient:
    """
    Cloud API client for drone-to-cloud communication.

    Features:
    - Secure TLS communication
    - Automatic retry with exponential backoff
    - Connection health monitoring
    - WebSocket support for real-time updates
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        drone_id: str,
        timeout: float = 30.0,
        max_retries: int = 3
    ):
        """
        Initialize cloud client.

        Args:
            api_url: Base URL of the cloud API
            api_key: API authentication key
            drone_id: Drone identifier
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.drone_id = drone_id
        self.timeout = timeout
        self.max_retries = max_retries

        self._online = False
        self._last_check = 0
        self._check_interval = 30  # seconds

        # Setup HTTP client
        self._setup_client()

        logger.info(f"Cloud client initialized: {self.api_url}")

    def _setup_client(self):
        """Setup HTTP client with retry logic."""
        if REQUESTS_AVAILABLE:
            self.session = requests.Session()

            # Configure retry strategy
            retry_strategy = Retry(
                total=self.max_retries,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE"]
            )

            adapter = HTTPAdapter(max_retries=retry_strategy)
            self.session.mount("http://", adapter)
            self.session.mount("https://", adapter)

            # Default headers
            self.session.headers.update({
                "Authorization": f"Bearer {self.api_key}",
                "X-Drone-ID": self.drone_id,
                "User-Agent": f"DroneAI/{self.drone_id}"
            })

            self._client_type = "requests"

        elif HTTPX_AVAILABLE:
            self.session = httpx.Client(
                timeout=self.timeout,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "X-Drone-ID": self.drone_id
                }
            )
            self._client_type = "httpx"

        else:
            logger.error("No HTTP client available. Install requests or httpx.")
            self.session = None
            self._client_type = None

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "X-Drone-ID": self.drone_id,
            "X-Timestamp": datetime.utcnow().isoformat()
        }

    def is_online(self) -> bool:
        """
        Check if the API is reachable.

        Uses cached result if checked recently.
        """
        current_time = time.time()

        # Use cached result if recent
        if current_time - self._last_check < self._check_interval:
            return self._online

        # Perform health check
        self._online = self._health_check()
        self._last_check = current_time

        return self._online

    def _health_check(self) -> bool:
        """Perform API health check."""
        if not self.session:
            return False

        try:
            response = self.session.get(
                f"{self.api_url}/health",
                timeout=5
            )
            return response.status_code == 200

        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            return False

    def analyze_image(
        self,
        image_data: bytes,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Send image to cloud API for analysis.

        Args:
            image_data: JPEG image bytes
            metadata: Image metadata (GPS, timestamp, etc.)

        Returns:
            Analysis result dict or None on failure
        """
        if not self.session:
            logger.error("No HTTP client available")
            return None

        endpoint = f"{self.api_url}/api/v1/analyze"
        metadata = metadata or {}

        try:
            # Prepare multipart form data
            files = {
                "image": ("capture.jpg", image_data, "image/jpeg")
            }

            data = {
                "drone_id": metadata.get("drone_id", self.drone_id),
                "field_id": metadata.get("field_id"),
                "latitude": metadata.get("latitude"),
                "longitude": metadata.get("longitude"),
                "altitude": metadata.get("altitude"),
                "notes": metadata.get("notes")
            }

            # Remove None values
            data = {k: v for k, v in data.items() if v is not None}

            # Send request
            start_time = time.time()

            response = self.session.post(
                endpoint,
                files=files,
                data=data,
                timeout=self.timeout
            )

            elapsed = (time.time() - start_time) * 1000

            if response.status_code == 200:
                result = response.json()
                logger.info(f"Analysis successful ({elapsed:.0f}ms)")
                self._online = True
                return result

            else:
                logger.error(f"Analysis failed: {response.status_code} - {response.text}")
                return None

        except requests.exceptions.Timeout:
            logger.error("Request timeout")
            self._online = False
            return None

        except requests.exceptions.ConnectionError:
            logger.error("Connection error - API unreachable")
            self._online = False
            return None

        except Exception as e:
            logger.error(f"Analysis request failed: {e}")
            return None

    def send_heartbeat(self, status: Dict[str, Any]) -> bool:
        """
        Send heartbeat to cloud API.

        Args:
            status: Drone status information

        Returns:
            True if successful
        """
        if not self.session:
            return False

        try:
            # Try WebSocket first, fall back to HTTP
            endpoint = f"{self.api_url}/api/v1/drone/heartbeat"

            response = self.session.post(
                endpoint,
                json=status,
                timeout=10
            )

            return response.status_code == 200

        except Exception as e:
            logger.debug(f"Heartbeat failed: {e}")
            return False

    def get_commands(self) -> Optional[list]:
        """
        Fetch pending commands from cloud.

        Returns:
            List of commands or None
        """
        if not self.session:
            return None

        try:
            endpoint = f"{self.api_url}/api/v1/drone/{self.drone_id}/commands"

            response = self.session.get(endpoint, timeout=10)

            if response.status_code == 200:
                return response.json().get("commands", [])

            return None

        except Exception as e:
            logger.debug(f"Get commands failed: {e}")
            return None

    def report_error(self, error_type: str, message: str, details: Optional[dict] = None):
        """
        Report error to cloud API.

        Args:
            error_type: Type of error
            message: Error message
            details: Additional details
        """
        if not self.session:
            return

        try:
            endpoint = f"{self.api_url}/api/v1/drone/{self.drone_id}/errors"

            payload = {
                "error_type": error_type,
                "message": message,
                "details": details or {},
                "timestamp": datetime.utcnow().isoformat()
            }

            self.session.post(endpoint, json=payload, timeout=10)

        except Exception as e:
            logger.debug(f"Error report failed: {e}")

    def upload_logs(self, log_data: str) -> bool:
        """
        Upload drone logs to cloud.

        Args:
            log_data: Log file content

        Returns:
            True if successful
        """
        if not self.session:
            return False

        try:
            endpoint = f"{self.api_url}/api/v1/drone/{self.drone_id}/logs"

            files = {
                "logfile": ("drone.log", log_data, "text/plain")
            }

            response = self.session.post(
                endpoint,
                files=files,
                timeout=30
            )

            return response.status_code == 200

        except Exception as e:
            logger.error(f"Log upload failed: {e}")
            return False

    def close(self):
        """Close the HTTP client."""
        if self.session:
            if self._client_type == "requests":
                self.session.close()
            elif self._client_type == "httpx":
                self.session.close()


class WebSocketClient:
    """WebSocket client for real-time communication."""

    def __init__(self, ws_url: str, api_key: str, drone_id: str):
        """
        Initialize WebSocket client.

        Args:
            ws_url: WebSocket URL
            api_key: API key
            drone_id: Drone identifier
        """
        self.ws_url = ws_url
        self.api_key = api_key
        self.drone_id = drone_id
        self.connected = False
        self.ws = None

    def connect(self) -> bool:
        """Connect to WebSocket server."""
        try:
            import websockets
            import asyncio

            async def _connect():
                self.ws = await websockets.connect(
                    self.ws_url,
                    extra_headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "X-Drone-ID": self.drone_id
                    }
                )
                self.connected = True
                return True

            return asyncio.get_event_loop().run_until_complete(_connect())

        except ImportError:
            logger.warning("websockets package not available")
            return False
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            return False

    def send(self, message: dict) -> bool:
        """Send message via WebSocket."""
        if not self.connected or not self.ws:
            return False

        try:
            import asyncio

            async def _send():
                await self.ws.send(json.dumps(message))

            asyncio.get_event_loop().run_until_complete(_send())
            return True

        except Exception as e:
            logger.error(f"WebSocket send failed: {e}")
            self.connected = False
            return False

    def close(self):
        """Close WebSocket connection."""
        if self.ws:
            try:
                import asyncio
                asyncio.get_event_loop().run_until_complete(self.ws.close())
            except Exception:
                pass
            self.ws = None
            self.connected = False