"""Broadlink hub wrapper used by PG3 nodes.

This wrapper keeps Broadlink specifics in one place so new Broadlink device
classes can be added later without changing node classes.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from threading import RLock
import time
from typing import Callable

import broadlink
import udi_interface

LOGGER = udi_interface.LOGGER

LearnProgressCallback = Callable[[str], None]


class FrequencyNotFoundError(TimeoutError):
    """Raised when RF sweep completes without a valid frequency lock."""


@dataclass(slots=True)
class BroadlinkHubInfo:
    """Cached identity information for a connected hub."""

    ip_address: str
    mac_address: str
    device_type: str
    model_name: str


@dataclass(slots=True)
class SensorData:
    """Sensor readings from a hub with an attached sensor cable."""

    has_temperature: bool
    has_humidity: bool
    temperature_c: float
    humidity: float


class BroadlinkHubClient:
    """Thin wrapper around python-broadlink remote functionality."""

    def __init__(self, hub_ip: str, user_id: str = "", user_password: str = "") -> None:
        LOGGER.debug("[BroadlinkHubClient.__init__] Creating client for ip=%s", hub_ip)
        self.hub_ip = hub_ip
        self.user_id = user_id
        self.user_password = user_password
        self._device = None
        self._hub_info: BroadlinkHubInfo | None = None
        self._lock = RLock()
        LOGGER.debug("[BroadlinkHubClient.__init__] Client initialized")

    @property
    def connected(self) -> bool:
        return self._device is not None

    @property
    def hub_info(self) -> BroadlinkHubInfo | None:
        return self._hub_info

    def connect(self) -> bool:
        """Discover and authenticate the Broadlink device at the configured IP."""
        with self._lock:
            LOGGER.debug("[connect] Attempting to connect to %s", self.hub_ip)
            if not self.hub_ip:
                LOGGER.error("[connect] HUB_IP is required")
                raise ValueError("HUB_IP is required")

            try:
                LOGGER.debug("[connect] Calling broadlink.hello(%s)", self.hub_ip)
                device = broadlink.hello(self.hub_ip)
                if device is None:
                    LOGGER.error("[connect] No Broadlink device found at %s", self.hub_ip)
                    raise RuntimeError(f"No Broadlink device found at {self.hub_ip}")
                
                LOGGER.debug("[connect] Device discovered, calling auth()")
                device.auth()
                
                self._device = device
                self._hub_info = BroadlinkHubInfo(
                    ip_address=self.hub_ip,
                    mac_address=_normalize_mac_address(getattr(device, "mac", None)),
                    device_type=_normalize_device_type(getattr(device, "devtype", None)),
                    model_name=type(device).__name__,
                )
                LOGGER.debug("[connect] Raw hub_info payload for %s: %r", self.hub_ip, self._hub_info)
                LOGGER.info("[connect] Connected to %s, model=%s, mac=%s",
                            self.hub_ip, self._hub_info.model_name, self._hub_info.mac_address)
                # Log all raw device attributes for diagnostics
                raw_attrs = {
                    "ip":          getattr(device, "host", (self.hub_ip, None))[0]
                                   if isinstance(getattr(device, "host", None), tuple)
                                   else getattr(device, "host", self.hub_ip),
                    "mac":         self._hub_info.mac_address,
                    "devtype":     hex(getattr(device, "devtype", 0)),
                    "model":       type(device).__name__,
                    "manufacturer":getattr(device, "manufacturer", "unknown"),
                    "is_locked":   getattr(device, "is_locked", "unknown"),
                    "timeout":     getattr(device, "timeout", "unknown"),
                }
                LOGGER.debug(
                    "[connect] Raw device attributes for %s:\n"
                    "  ip          : %s\n"
                    "  mac         : %s\n"
                    "  devtype     : %s\n"
                    "  model       : %s\n"
                    "  manufacturer: %s\n"
                    "  is_locked   : %s\n"
                    "  timeout     : %s",
                    self.hub_ip,
                    raw_attrs["ip"],
                    raw_attrs["mac"],
                    raw_attrs["devtype"],
                    raw_attrs["model"],
                    raw_attrs["manufacturer"],
                    raw_attrs["is_locked"],
                    raw_attrs["timeout"],
                )
                return True
            except Exception as err:
                LOGGER.error("[connect] Connection failed: %s", err)
                raise

    def identify(self) -> BroadlinkHubInfo:
        """Ensure the hub is connected and return cached identity details."""
        with self._lock:
            if self._hub_info is None or self._device is None:
                self.connect()
            return self._hub_info

    def refresh(self) -> bool:
        """Best-effort connectivity refresh."""
        with self._lock:
            LOGGER.debug("[refresh] Attempting refresh")
            if self._device is None:
                try:
                    LOGGER.debug("[refresh] Device not cached, connecting")
                    self.connect()
                    return True
                except Exception as err:
                    LOGGER.warning("[refresh] Connect failed: %s", err)
                    return False
            try:
                LOGGER.debug("[refresh] Testing cached device with ping")
                self._device.ping()
                LOGGER.debug("[refresh] Ping successful")
                return True
            except Exception as err:
                LOGGER.warning("[refresh] Ping failed: %s, attempting re-auth", err)
                try:
                    self._device.auth()
                    if self._hub_info is None:
                        self._hub_info = BroadlinkHubInfo(
                            ip_address=self.hub_ip,
                            mac_address=_normalize_mac_address(getattr(self._device, "mac", None)),
                            device_type=_normalize_device_type(getattr(self._device, "devtype", None)),
                            model_name=type(self._device).__name__,
                        )
                    LOGGER.info("[refresh] Re-auth successful")

                    return True
                except Exception as auth_err:
                    LOGGER.error("[refresh] Re-auth failed: %s, clearing device", auth_err)
                    self._device = None
                    return False

    def ensure_connected(self) -> BroadlinkHubInfo:
        """Reconnect if needed and return the current identified hub details."""
        with self._lock:
            LOGGER.debug("[ensure_connected] Checking connection state")
            if self._device is not None:
                try:
                    LOGGER.debug("[ensure_connected] Testing cached device with ping")
                    self._device.ping()
                    if self._hub_info is not None:
                        LOGGER.debug("[ensure_connected] Device already connected")
                        return self._hub_info
                except Exception as err:
                    LOGGER.warning("[ensure_connected] Ping failed: %s, will reconnect", err)
                    self._device = None

            LOGGER.info("[ensure_connected] Connecting to %s", self.hub_ip)
            self.connect()
            return self._hub_info

    def send_code(self, encoded_code: str) -> bool:
        """Transmit an IR or RF packet to the Broadlink hub. Returns True on success."""
        packet = decode_code_string(encoded_code)

        with self._lock:
            if self._device is None:
                self.connect()
            try:
                self._device.send_data(packet)
                return True
            except Exception as err:
                LOGGER.error("[send_code] Transmission failed: %s", err)
                return False

    def check_sensors(self) -> SensorData:
        """Query the hub for temperature and humidity sensor readings.

        Raises an exception if the device does not support sensor queries
        or if no sensor cable is attached.
        """
        with self._lock:
            if self._device is None:
                self.connect()
            data = self._device.check_sensors()
            LOGGER.debug("[check_sensors] Raw sensor payload from %s: %r", self.hub_ip, data)
            # Log full raw sensor dict from device before any processing
            if data:
                formatted = "\n".join(f"  {k:<20}: {v}" for k, v in sorted(data.items()))
                LOGGER.debug("[check_sensors] Raw sensor data from %s:\n%s", self.hub_ip, formatted)
            else:
                LOGGER.debug("[check_sensors] Raw sensor data from %s: <empty>", self.hub_ip)
            temp = data.get("temperature")
            humidity = data.get("humidity")

            # Broadlink hubs with no physical sensor attached return 0.0 for
            # all fields rather than omitting them.  Treat a response where
            # every numeric value rounds to exactly zero as "no sensor".
            temp_val = float(temp) if temp is not None else 0.0
            humidity_val = float(humidity) if humidity is not None else 0.0
            all_zero = (temp_val == 0.0 and humidity_val == 0.0)
            if all_zero:
                LOGGER.debug(
                    "[check_sensors] All-zero sensor response from %s — treating as no sensor attached",
                    self.hub_ip,
                )

            return SensorData(
                has_temperature=temp is not None and not all_zero,
                has_humidity=humidity is not None and not all_zero,
                temperature_c=temp_val,
                humidity=humidity_val,
            )

    def learn_ir(
        self,
        timeout_sec: int = 30,
        poll_interval: float = 1.0,
        progress_callback: LearnProgressCallback | None = None,
    ) -> bytes:
        """Learn a single IR packet and return raw Broadlink bytes."""
        with self._lock:
            if self._device is None:
                self.connect()

            LOGGER.info("[learn_ir] Entering learning mode (timeout=%ss poll=%.2fs)", timeout_sec, poll_interval)
            self._device.enter_learning()
            if progress_callback:
                progress_callback("ir_enter_learning_completed")
            return self._wait_for_learned_packet(
                timeout_sec=timeout_sec,
                poll_interval=poll_interval,
                progress_callback=progress_callback,
                waiting_event="",
            )

    def learn_rf(
        self,
        timeout_sec: int = 45,
        packet_timeout_sec: int = 30,
        poll_interval: float = 1.0,
        progress_callback: LearnProgressCallback | None = None,
    ) -> bytes:
        """Learn a single RF packet and return raw Broadlink bytes.

        For devices that support RF sweep APIs we use sweep->check_frequency->find_rf_packet.
        If the device does not expose RF sweep APIs, we fall back to generic learning.
        """
        with self._lock:
            if self._device is None:
                self.connect()

            if hasattr(self._device, "sweep_frequency") and hasattr(self._device, "check_frequency"):
                LOGGER.info("[learn_rf] Using RF sweep flow (timeout=%ss poll=%.2fs)", timeout_sec, poll_interval)
                # Cancel any residual learning state from a previous session before starting.
                try:
                    self._device.cancel_sweep_frequency()
                    LOGGER.debug("[learn_rf] Cancelled any previous sweep state")
                except Exception:
                    pass
                time.sleep(0.25)
                self._device.sweep_frequency()
                if progress_callback:
                    progress_callback("rf_sweep_completed")
                start = time.time()
                found = False
                frequency = None
                checks = 0

                while (time.time() - start) < timeout_sec:
                    time.sleep(poll_interval)
                    checks += 1
                    try:
                        check_result = self._device.check_frequency()
                    except Exception:
                        continue
                    if isinstance(check_result, tuple):
                        found = bool(check_result[0])
                        frequency = check_result[1] if len(check_result) > 1 else None
                    else:
                        found = bool(check_result)
                        frequency = None
                    if checks == 1 or checks % 5 == 0 or found:
                        LOGGER.debug(
                            "[learn_rf] check_frequency attempt=%s found=%s frequency=%s result_type=%s",
                            checks,
                            found,
                            frequency,
                            type(check_result).__name__,
                        )
                    if found:
                        break

                if found:
                    try:
                        if frequency is not None:
                            self._device.find_rf_packet(frequency)
                        else:
                            self._device.find_rf_packet()
                    except TypeError:
                        # Older/alternate implementations may not accept frequency.
                        self._device.find_rf_packet()
                    LOGGER.info("[learn_rf] Frequency lock found after %s checks; waiting for RF packet", checks)
                    if progress_callback:
                        progress_callback("rf_find_packet_completed")
                    return self._wait_for_learned_packet(
                        timeout_sec=packet_timeout_sec,
                        poll_interval=poll_interval,
                        progress_callback=progress_callback,
                        waiting_event="",
                    )

                # RF-capable devices should stop here when no valid frequency lock was found.
                try:
                    self._device.cancel_sweep_frequency()
                except Exception:
                    pass
                if progress_callback:
                    progress_callback("rf_frequency_not_found")
                LOGGER.warning("[learn_rf] RF frequency sweep timed out after %s checks; stopping learn", checks)
                raise FrequencyNotFoundError("RF frequency was not identified before timeout")

            # Some remote models learn RF through the same generic IR flow.
            if progress_callback:
                progress_callback("rf_fallback_enter_learning")
            LOGGER.info("[learn_rf] Using enter_learning fallback flow")
            self._device.enter_learning()
            return self._wait_for_learned_packet(
                timeout_sec=packet_timeout_sec,
                poll_interval=poll_interval,
                progress_callback=progress_callback,
                waiting_event="rf_check_data",
            )

    def _wait_for_learned_packet(
        self,
        timeout_sec: int = 30,
        poll_interval: float = 1.0,
        progress_callback: LearnProgressCallback | None = None,
        waiting_event: str = "check_data",
    ) -> bytes:
        """Poll the hub until a learned packet is available."""
        start = time.time()
        announced_wait = False
        polls = 0
        LOGGER.debug("[_wait_for_learned_packet] waiting_event=%s timeout=%ss poll=%.2fs", waiting_event, timeout_sec, poll_interval)
        while (time.time() - start) < timeout_sec:
            if progress_callback and waiting_event and not announced_wait:
                progress_callback(waiting_event)
                announced_wait = True
            time.sleep(poll_interval)
            polls += 1
            try:
                packet = self._device.check_data()
            except Exception:
                continue
            if packet:
                LOGGER.info("[_wait_for_learned_packet] Packet received after %s polls, size=%s", polls, len(packet))
                return packet
            if polls == 1 or polls % 5 == 0:
                LOGGER.debug("[_wait_for_learned_packet] No packet yet after %s polls", polls)

        LOGGER.warning("[_wait_for_learned_packet] Timed out after %s polls", polls)
        raise TimeoutError("No learned packet received before timeout")

    def provision_ap(self, ssid: str, password: str, security_mode: int = 4, setup_ip: str = "255.255.255.255") -> bool:
        """Provision a Broadlink device in AP mode using broadlink.setup."""
        if not ssid:
            raise ValueError("WIFI_SSID is required for AP setup")
        if security_mode < 0 or security_mode > 4:
            raise ValueError("WIFI_SECURITY_MODE must be between 0 and 4")

        broadlink.setup(ssid=ssid, password=password, security_mode=security_mode, ip_address=setup_ip)
        return True


def decode_code_string(raw: str) -> bytes:
    """Decode user code strings into Broadlink packet bytes.

    Supported input:
    - Hex string (with or without spaces)
    - base64 with `b64:` prefix
    """
    text = str(raw).strip()
    if not text:
        raise ValueError("Code string is empty")

    if text.lower().startswith("b64:"):
        return base64.b64decode(text[4:].strip())

    hex_text = "".join(text.split())
    return bytes.fromhex(hex_text)


def _normalize_mac_address(raw_mac) -> str:
    """Convert Broadlink MAC representations to a normalized lowercase string."""
    if raw_mac is None:
        return ""

    if isinstance(raw_mac, bytes):
        return raw_mac.hex()

    if isinstance(raw_mac, str):
        return "".join(char for char in raw_mac.lower() if char.isalnum())

    try:
        return "".join(f"{int(part):02x}" for part in raw_mac)
    except TypeError:
        return str(raw_mac).strip().lower()


def _normalize_device_type(raw_device_type) -> str:
    """Convert Broadlink device type information to a stable string."""
    if raw_device_type is None:
        return "unknown"
    if isinstance(raw_device_type, int):
        return f"0x{raw_device_type:04x}"
    return str(raw_device_type).strip()
