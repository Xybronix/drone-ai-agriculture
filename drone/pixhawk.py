"""
Pixhawk Flight Controller Interface.
Handles communication with Pixhawk for GPS, telemetry, and basic control.
"""

import os
import time
import logging
import threading
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Check for simulation mode
SIMULATE = os.environ.get('DRONE_SIMULATE', '0') == '1'

# Try to import MAVLink library
MAVLINK_AVAILABLE = False
if not SIMULATE:
    try:
        from pymavlink import mavutil
        MAVLINK_AVAILABLE = True
    except ImportError:
        pass


@dataclass
class GPSData:
    """GPS data structure."""
    latitude: float
    longitude: float
    altitude: float
    satellites: int
    fix_type: int
    hdop: float
    timestamp: float


@dataclass
class AttitudeData:
    """Attitude data structure."""
    roll: float
    pitch: float
    yaw: float
    rollspeed: float
    pitchspeed: float
    yawspeed: float


@dataclass
class BatteryData:
    """Battery data structure."""
    voltage: float
    current: float
    remaining: int  # Percentage


class PixhawkController:
    """
    Pixhawk flight controller interface.

    Features:
    - GPS data acquisition
    - Attitude/orientation data
    - Battery monitoring
    - Basic flight commands
    - Heartbeat monitoring
    """

    def __init__(
        self,
        connection_string: str = "/dev/ttyAMA0",
        baud_rate: int = 57600
    ):
        """
        Initialize Pixhawk controller.

        Args:
            connection_string: Serial port or UDP address
            baud_rate: Serial baud rate
        """
        self.connection_string = connection_string
        self.baud_rate = baud_rate

        self.connection = None
        self.connected = False

        self._gps_data: Optional[GPSData] = None
        self._attitude_data: Optional[AttitudeData] = None
        self._battery_data: Optional[BatteryData] = None

        self._lock = threading.Lock()
        self._running = False
        self._reader_thread: Optional[threading.Thread] = None

        # Simulation data
        self._sim_lat = 48.8566
        self._sim_lon = 2.3522
        self._sim_alt = 50.0

    def connect(self) -> bool:
        """
        Connect to Pixhawk.

        Returns:
            True if connection successful
        """
        if SIMULATE or not MAVLINK_AVAILABLE:
            logger.info("Pixhawk running in SIMULATION mode")
            self.connected = True
            self._running = True
            self._start_simulation()
            return True

        try:
            logger.info(f"Connecting to Pixhawk: {self.connection_string}")

            self.connection = mavutil.mavlink_connection(
                self.connection_string,
                baud=self.baud_rate
            )

            # Wait for heartbeat
            logger.info("Waiting for heartbeat...")
            self.connection.wait_heartbeat(timeout=30)

            logger.info(
                f"Connected to Pixhawk (system {self.connection.target_system}, "
                f"component {self.connection.target_component})"
            )

            self.connected = True
            self._running = True

            # Start message reader thread
            self._reader_thread = threading.Thread(
                target=self._read_messages,
                name="PixhawkReader",
                daemon=True
            )
            self._reader_thread.start()

            # Request data streams
            self._request_data_streams()

            return True

        except Exception as e:
            logger.error(f"Pixhawk connection failed: {e}")
            self.connected = False
            return False

    def disconnect(self):
        """Disconnect from Pixhawk."""
        self._running = False

        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=2.0)

        if self.connection:
            self.connection.close()
            self.connection = None

        self.connected = False
        logger.info("Pixhawk disconnected")

    def _request_data_streams(self):
        """Request data streams from Pixhawk."""
        if not self.connection:
            return

        # Request all data streams at 4 Hz
        self.connection.mav.request_data_stream_send(
            self.connection.target_system,
            self.connection.target_component,
            mavutil.mavlink.MAV_DATA_STREAM_ALL,
            4,  # 4 Hz
            1   # Start
        )

    def _read_messages(self):
        """Read and process MAVLink messages."""
        while self._running and self.connection:
            try:
                msg = self.connection.recv_match(blocking=True, timeout=1.0)

                if msg is None:
                    continue

                msg_type = msg.get_type()

                with self._lock:
                    if msg_type == 'GPS_RAW_INT':
                        self._gps_data = GPSData(
                            latitude=msg.lat / 1e7,
                            longitude=msg.lon / 1e7,
                            altitude=msg.alt / 1000.0,
                            satellites=msg.satellites_visible,
                            fix_type=msg.fix_type,
                            hdop=msg.eph / 100.0,
                            timestamp=time.time()
                        )

                    elif msg_type == 'GLOBAL_POSITION_INT':
                        # More accurate position
                        if self._gps_data:
                            self._gps_data.latitude = msg.lat / 1e7
                            self._gps_data.longitude = msg.lon / 1e7
                            self._gps_data.altitude = msg.relative_alt / 1000.0

                    elif msg_type == 'ATTITUDE':
                        self._attitude_data = AttitudeData(
                            roll=msg.roll,
                            pitch=msg.pitch,
                            yaw=msg.yaw,
                            rollspeed=msg.rollspeed,
                            pitchspeed=msg.pitchspeed,
                            yawspeed=msg.yawspeed
                        )

                    elif msg_type == 'BATTERY_STATUS':
                        self._battery_data = BatteryData(
                            voltage=msg.voltages[0] / 1000.0 if msg.voltages[0] != 65535 else 0,
                            current=msg.current_battery / 100.0,
                            remaining=msg.battery_remaining
                        )

                    elif msg_type == 'SYS_STATUS':
                        # Alternative battery info
                        if not self._battery_data:
                            self._battery_data = BatteryData(
                                voltage=msg.voltage_battery / 1000.0,
                                current=msg.current_battery / 100.0,
                                remaining=msg.battery_remaining
                            )

            except Exception as e:
                logger.error(f"Message read error: {e}")
                time.sleep(0.1)

    def _start_simulation(self):
        """Start simulation data generator."""
        import random

        def simulate():
            while self._running:
                with self._lock:
                    # Simulate slight movement
                    self._sim_lat += random.uniform(-0.0001, 0.0001)
                    self._sim_lon += random.uniform(-0.0001, 0.0001)
                    self._sim_alt += random.uniform(-1, 1)
                    self._sim_alt = max(10, min(100, self._sim_alt))

                    self._gps_data = GPSData(
                        latitude=self._sim_lat,
                        longitude=self._sim_lon,
                        altitude=self._sim_alt,
                        satellites=12,
                        fix_type=3,
                        hdop=1.0,
                        timestamp=time.time()
                    )

                    self._attitude_data = AttitudeData(
                        roll=random.uniform(-0.1, 0.1),
                        pitch=random.uniform(-0.1, 0.1),
                        yaw=random.uniform(0, 6.28),
                        rollspeed=0,
                        pitchspeed=0,
                        yawspeed=0
                    )

                    self._battery_data = BatteryData(
                        voltage=11.5 + random.uniform(-0.2, 0.2),
                        current=5.0 + random.uniform(-1, 1),
                        remaining=max(0, 85 - int(time.time() % 100))
                    )

                time.sleep(1.0)

        self._reader_thread = threading.Thread(
            target=simulate,
            name="PixhawkSimulator",
            daemon=True
        )
        self._reader_thread.start()

    def get_gps(self) -> Optional[Dict[str, Any]]:
        """
        Get current GPS data.

        Returns:
            GPS data dictionary or None
        """
        with self._lock:
            if self._gps_data:
                return {
                    "latitude": round(self._gps_data.latitude, 6),
                    "longitude": round(self._gps_data.longitude, 6),
                    "altitude": round(self._gps_data.altitude, 1),
                    "satellites": self._gps_data.satellites,
                    "fix_type": self._gps_data.fix_type,
                    "hdop": self._gps_data.hdop
                }
            return None

    def get_attitude(self) -> Optional[Dict[str, float]]:
        """
        Get current attitude data.

        Returns:
            Attitude data dictionary or None
        """
        with self._lock:
            if self._attitude_data:
                return {
                    "roll": round(self._attitude_data.roll, 4),
                    "pitch": round(self._attitude_data.pitch, 4),
                    "yaw": round(self._attitude_data.yaw, 4)
                }
            return None

    def get_battery_level(self) -> Optional[int]:
        """
        Get battery level percentage.

        Returns:
            Battery percentage (0-100) or None
        """
        with self._lock:
            if self._battery_data:
                return self._battery_data.remaining
            return None

    def get_battery_info(self) -> Optional[Dict[str, Any]]:
        """
        Get detailed battery information.

        Returns:
            Battery info dictionary or None
        """
        with self._lock:
            if self._battery_data:
                return {
                    "voltage": round(self._battery_data.voltage, 2),
                    "current": round(self._battery_data.current, 2),
                    "remaining": self._battery_data.remaining
                }
            return None

    def get_telemetry(self) -> Dict[str, Any]:
        """
        Get all telemetry data.

        Returns:
            Complete telemetry dictionary
        """
        return {
            "connected": self.connected,
            "gps": self.get_gps(),
            "attitude": self.get_attitude(),
            "battery": self.get_battery_info()
        }

    def arm(self) -> bool:
        """
        Arm the drone.

        Returns:
            True if successful
        """
        if SIMULATE:
            logger.info("SIMULATE: Drone armed")
            return True

        if not self.connection:
            return False

        try:
            self.connection.mav.command_long_send(
                self.connection.target_system,
                self.connection.target_component,
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                0,
                1, 0, 0, 0, 0, 0, 0
            )

            # Wait for acknowledgment
            ack = self.connection.recv_match(
                type='COMMAND_ACK',
                blocking=True,
                timeout=5
            )

            if ack and ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
                logger.info("Drone armed")
                return True

            logger.warning(f"Arm command rejected: {ack.result if ack else 'timeout'}")
            return False

        except Exception as e:
            logger.error(f"Arm failed: {e}")
            return False

    def disarm(self) -> bool:
        """
        Disarm the drone.

        Returns:
            True if successful
        """
        if SIMULATE:
            logger.info("SIMULATE: Drone disarmed")
            return True

        if not self.connection:
            return False

        try:
            self.connection.mav.command_long_send(
                self.connection.target_system,
                self.connection.target_component,
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                0,
                0, 0, 0, 0, 0, 0, 0
            )

            logger.info("Drone disarmed")
            return True

        except Exception as e:
            logger.error(f"Disarm failed: {e}")
            return False

    def set_mode(self, mode: str) -> bool:
        """
        Set flight mode.

        Args:
            mode: Flight mode name (e.g., 'GUIDED', 'LOITER', 'RTL')

        Returns:
            True if successful
        """
        if SIMULATE:
            logger.info(f"SIMULATE: Mode set to {mode}")
            return True

        if not self.connection:
            return False

        try:
            mode_id = self.connection.mode_mapping().get(mode)

            if mode_id is None:
                logger.error(f"Unknown mode: {mode}")
                return False

            self.connection.mav.set_mode_send(
                self.connection.target_system,
                mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                mode_id
            )

            logger.info(f"Mode set to {mode}")
            return True

        except Exception as e:
            logger.error(f"Set mode failed: {e}")
            return False

    def return_to_launch(self) -> bool:
        """
        Command return to launch.

        Returns:
            True if successful
        """
        return self.set_mode('RTL')