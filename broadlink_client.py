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
class RFLearnResult:
    """RF learn payload including optional locked frequency in MHz."""

    packet: bytes
    frequency_mhz: float | None = None


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
        timeout_sec: int = 12,
        poll_interval: float = 1.0,
        progress_callback: LearnProgressCallback | None = None,
    ) -> bytes:
        """Learn a single IR packet and return raw Broadlink bytes."""
        with self._lock:
            if self._device is None:
                self.connect()

            self._drain_learn_buffer()
            LOGGER.info("[learn_ir] Entering learning mode (timeout=%ss poll=%.2fs)", timeout_sec, poll_interval)
            self._device.enter_learning()
            if progress_callback:
                progress_callback("ir_enter_learning_completed")
            # Announce that we're waiting for IR packet data and allow the
            # waiter to emit timeout events via the provided event name.
            return self._wait_for_learned_packet(
                timeout_sec=timeout_sec,
                poll_interval=poll_interval,
                progress_callback=progress_callback,
                waiting_event="ir_check_data",
            )

    def learn_rf(
        self,
        timeout_sec: int = 20,
        packet_timeout_sec: int = 6,
        poll_interval: float = 1.0,
        progress_callback: LearnProgressCallback | None = None,
    ) -> RFLearnResult:
        """Learn a single RF packet and return packet bytes plus lock frequency.

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
                self._drain_learn_buffer()
                time.sleep(0.25)
                self._device.sweep_frequency()
                if progress_callback:
                    LOGGER.debug("[learn_rf] Emitting progress event=rf_sweep_completed")
                    progress_callback("rf_sweep_completed")
                start = time.time()
                found = False
                frequency = None
                checks = 0
                LOGGER.debug("[learn_rf] Sweep started at t=%.3f timeout=%ss", start, timeout_sec)

                while (time.time() - start) < timeout_sec:
                    time.sleep(poll_interval)
                    checks += 1
                    try:
                        check_result = self._device.check_frequency()
                        LOGGER.debug(f'[learn_rf] Check Results {check_result }')
                    except Exception as err:
                        if checks == 1 or checks % 5 == 0:
                            LOGGER.debug("[learn_rf] check_frequency attempt=%s raised=%s", checks, err)
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

                elapsed = time.time() - start
                LOGGER.debug(
                    "[learn_rf] Sweep loop ended found=%s checks=%s elapsed=%.2fs timeout=%ss last_frequency=%s",
                    found,
                    checks,
                    elapsed,
                    timeout_sec,
                    frequency,
                )

                # Final check after timeout boundary to avoid missing a lock that arrives
                # between the loop condition and the next iteration.
                if not found:
                    try:
                        final_check_result = self._device.check_frequency()
                        final_found = False
                        final_frequency = None
                        if isinstance(final_check_result, tuple):
                            final_found = bool(final_check_result[0])
                            final_frequency = final_check_result[1] if len(final_check_result) > 1 else None
                        else:
                            final_found = bool(final_check_result)
                        LOGGER.debug(
                            "[learn_rf] Post-timeout check_frequency found=%s frequency=%s result_type=%s",
                            final_found,
                            final_frequency,
                            type(final_check_result).__name__,
                        )
                        if final_found:
                            found = True
                            if final_frequency is not None:
                                frequency = final_frequency
                            LOGGER.info(
                                "[learn_rf] Frequency lock detected on post-timeout check; proceeding to packet capture"
                            )
                    except Exception as err:
                        LOGGER.debug("[learn_rf] Post-timeout check_frequency raised=%s", err)

                # Some devices briefly oscillate between locked/unlocked state.
                # Confirm one extra lock check so we do not proceed on transient locks.
                if found:
                    try:
                        confirm_result = self._device.check_frequency()
                        confirm_found = False
                        confirm_frequency = None
                        if isinstance(confirm_result, tuple):
                            confirm_found = bool(confirm_result[0])
                            confirm_frequency = confirm_result[1] if len(confirm_result) > 1 else None
                        else:
                            confirm_found = bool(confirm_result)
                        if not confirm_found:
                            LOGGER.warning(
                                "[learn_rf] Frequency lock was transient on confirmation check; continuing sweep"
                            )
                            found = False
                        elif confirm_frequency is not None:
                            frequency = confirm_frequency
                    except Exception as err:
                        LOGGER.debug("[learn_rf] Lock confirmation check failed: %s", err)

                if found:
                    LOGGER.info("[learn_rf] Frequency lock found after %s checks; waiting for RF packet", checks)

                    # Retry packet capture once before failing. In practice,
                    # users can miss the "press once" timing on the first pass.
                    capture_timeout_sequence = [packet_timeout_sec, max(3, int(packet_timeout_sec / 2))]
                    last_capture_error: TimeoutError | None = None
                    for capture_idx, capture_timeout in enumerate(capture_timeout_sequence, start=1):
                        self._drain_learn_buffer()
                        try:
                            if frequency is not None:
                                self._device.find_rf_packet(frequency)
                            else:
                                self._device.find_rf_packet()
                        except TypeError:
                            # Older/alternate implementations may not accept frequency.
                            self._device.find_rf_packet()

                        if progress_callback:
                            LOGGER.debug("[learn_rf] Emitting progress event=rf_find_packet_completed (capture_attempt=%s)", capture_idx)
                            progress_callback("rf_find_packet_completed")

                        try:
                            packet = self._wait_for_learned_packet(
                                timeout_sec=capture_timeout,
                                poll_interval=poll_interval,
                                progress_callback=progress_callback,
                                waiting_event="rf_check_data",
                            )
                            try:
                                self._device.cancel_sweep_frequency()
                            except Exception:
                                pass
                            return RFLearnResult(packet=packet, frequency_mhz=float(frequency) if frequency is not None else None)
                        except TimeoutError as err:
                            last_capture_error = err
                            LOGGER.warning(
                                "[learn_rf] RF packet not captured after frequency lock on attempt %s/%s (timeout=%ss)",
                                capture_idx,
                                len(capture_timeout_sequence),
                                capture_timeout,
                            )

                    if last_capture_error is not None:
                        # Stop RF learning session when packet capture timed out
                        # after a successful frequency lock.
                        try:
                            self._device.cancel_sweep_frequency()
                        except Exception:
                            pass
                        raise last_capture_error

                # RF-capable devices should stop here when no valid frequency lock was found.
                try:
                    self._device.cancel_sweep_frequency()
                except Exception:
                    pass
                if progress_callback:
                    LOGGER.debug("[learn_rf] Emitting progress event=rf_frequency_not_found")
                    progress_callback("rf_frequency_not_found")
                LOGGER.warning(
                    "[learn_rf] RF frequency sweep timed out after %s checks (elapsed=%.2fs); no frequency lock found; stopping learn",
                    checks,
                    elapsed,
                )
                raise FrequencyNotFoundError("RF frequency was not identified before timeout")

            # Some remote models learn RF through the same generic IR flow.
            if progress_callback:
                progress_callback("rf_fallback_enter_learning")
            LOGGER.info("[learn_rf] Using enter_learning fallback flow")
            self._drain_learn_buffer()
            self._device.enter_learning()
            packet = self._wait_for_learned_packet(
                timeout_sec=packet_timeout_sec,
                poll_interval=poll_interval,
                progress_callback=progress_callback,
                waiting_event="rf_check_data",
            )
            return RFLearnResult(packet=packet, frequency_mhz=None)

    def _wait_for_learned_packet(
        self,
        timeout_sec: int = 12,
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
        # Emit a timeout-specific progress event when possible so callers
        # (e.g., node logic) can map to a suitable state via
        # _handle_learn_progress.
        if progress_callback and waiting_event:
            try:
                progress_callback(f"{waiting_event}_timeout")
            except Exception:
                pass
        raise TimeoutError("No learned packet received before timeout")

    def _drain_learn_buffer(self, max_reads: int = 4, delay_sec: float = 0.05) -> int:
        """Drain any stale learned packets to avoid reusing old RF/IR data."""
        drained = 0
        for _ in range(max_reads):
            try:
                packet = self._device.check_data()
            except Exception:
                break
            if not packet:
                break
            drained += 1
            time.sleep(delay_sec)
        if drained:
            LOGGER.debug("[_drain_learn_buffer] Discarded %s stale packet(s)", drained)
        return drained

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
