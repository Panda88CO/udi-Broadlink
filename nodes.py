"""Node classes for the Broadlink PG3 plugin single-hub rewrite."""

from __future__ import annotations

from dataclasses import dataclass
import json
import threading
import time

import udi_interface

from broadlink_client import BroadlinkHubClient, BroadlinkHubInfo, SensorData
from config_parser import PluginConfig, build_config

LOGGER = udi_interface.LOGGER
Custom = udi_interface.Custom
VERSION = "0.2.5"
DEFAULT_SETUP_ADDRESS = "setup"

MODEL_INDEX_NAMES = {
    "0": "Unknown",
    "1": "RM4 Pro",
    "2": "RM4 Mini",
    "3": "RM Pro",
    "4": "RM Mini",
    "5": "RM2",
    "6": "Other Broadlink",
}

IR_LEARN_STATUS_NAMES = {
    "0": "Idle",
    "1": "Start Learning: press the IR button you want to learn",
    "2": "Check Packet Data: keep remote aimed at hub",
    "3": "Learned",
    "4": "Failed",
}

RF_LEARN_STATUS_NAMES = {
    "0": "Idle",
    "1": "When LED blinks first time long press button you want to learn",
    "2": "When LED blinks short press button you want to learn",
    "3": "Check Packet Data: wait while hub captures RF code",
    "4": "Learned",
    "5": "Failed",
}

LEARN_STATUS_BY_EVENT = {
    "ir": {
        "ir_enter_learning": 1,
        "ir_check_data": 2,
    },
    "rf": {
        "rf_sweep_frequency": 1,
        "rf_check_frequency": 1,
        "rf_find_packet": 2,
        "rf_check_data": 3,
        "rf_fallback_enter_learning": 2,
    },
}

def _build_profile_definition(temp_unit: str = "C") -> dict:
    """Build the dynamic JSON profile definition.

    Temperature UOM follows ``temp_unit``: 'C' → UOM 17 (°C), 'F' → UOM 4 (°F).
    """
    temp_editor_id = "temp_f" if temp_unit == "F" else "temp_c"

    editors = [
        {
            "id": "hub_status",
            "ranges": [{"uom": "25", "subset": "0-3", "names": {
                "0": "No Hubs Configured", "1": "All Online", "2": "Partial", "3": "None Online",
            }}],
        },
        {
            "id": "status_index",
            "ranges": [{"uom": "25", "subset": "0-2", "names": {"0": "Not Configured", "1": "Online", "2": "Error"}}],
        },
        {
            "id": "binary_index",
            "ranges": [{"uom": "25", "subset": "0-1", "names": {"0": "No", "1": "Yes"}}],
        },
        {
            "id": "model_index",
            "ranges": [{"uom": "25", "subset": "0-6", "names": MODEL_INDEX_NAMES}],
        },
        {
            "id": "raw_value",
            "ranges": [{"uom": "56", "min": 0, "max": 65535, "prec": 0}],
        },
        {
            "id": "timestamp",
            "ranges": [{"uom": "151", "min": 0, "max": 4294967295, "prec": 0}],
        },
        {
            "id": "ir_learn_status",
            "ranges": [{"uom": "25", "subset": "0-4", "names": IR_LEARN_STATUS_NAMES}],
        },
        {
            "id": "rf_learn_status",
            "ranges": [{"uom": "25", "subset": "0-5", "names": RF_LEARN_STATUS_NAMES}],
        },
        {
            "id": "tx_status",
            "ranges": [{"uom": "25", "subset": "0-3", "names": {"0": "Ready", "1": "Sending", "2": "Sent OK", "3": "Failed"}}],
        },
        {
            "id": "tx_result",
            "ranges": [{"uom": "25", "subset": "0-2", "names": {"0": "Never", "1": "Success", "2": "Failed"}}],
        },
        {"id": "temp_c", "ranges": [{"uom": "17", "min": -40, "max": 125, "prec": 1}]},
        {"id": "temp_f", "ranges": [{"uom": "4", "min": -40, "max": 257, "prec": 1}]},
        {"id": "humidity_pct", "ranges": [{"uom": "22", "min": 0, "max": 100, "prec": 1}]},
    ]

    blhub_properties = [
        {"id": "ST", "name": "Status", "editor": "status_index"},
        {"id": "GV0", "name": "Model", "editor": "model_index"},
        {"id": "GV1", "name": "Connected", "editor": "binary_index"},
        {"id": "TIME", "name": "Last Update", "editor": "timestamp"},
    ]

    nodedefs = [
        {
            "id": "setup",
            "name": "Broadlink",
            "icon": "GenericCtl",
            "properties": [
                {"id": "ST", "name": "Status", "editor": "hub_status"},
                {"id": "GV0", "name": "Hub Count", "editor": "raw_value"},
                {"id": "TIME", "name": "Last Update", "editor": "timestamp"},
            ],
            "cmds": {
                "accepts": [
                    {"id": "UPDATE", "name": "Update"},
                ],
                "sends": [
                    {"id": "DON", "name": "Heartbeat On"},
                    {"id": "DOF", "name": "Heartbeat Off"},
                ],
            },
            "links": {"ctl": [], "rsp": []},
        },
        {
            "id": "blhub",
            "name": "Broadlink Hub",
            "icon": "GenericCtl",
            "properties": blhub_properties,
            "cmds": {
                "accepts": [
                    {"id": "UPDATE", "name": "Update"},
                ],
                "sends": [],
            },
            "links": {"ctl": [], "rsp": []},
        },
        {
            "id": "blirctl",
            "name": "IR Controller",
            "icon": "GenericCtl",
            "properties": [
                {"id": "ST", "name": "Status", "editor": "ir_learn_status"},
                {"id": "TIME", "name": "Last Learn", "editor": "timestamp"},
                {"id": "GV1", "name": "Learn Count", "editor": "raw_value"},
                {"id": "GV2", "name": "Hub Connected", "editor": "binary_index"},
            ],
            "cmds": {
                "accepts": [
                    {"id": "LEARNCODE", "name": "Learn IR Code"},
                ],
                "sends": [],
            },
            "links": {"ctl": [], "rsp": []},
        },
        {
            "id": "blrfctl",
            "name": "RF Controller",
            "icon": "GenericCtl",
            "properties": [
                {"id": "ST", "name": "Status", "editor": "rf_learn_status"},
                {"id": "TIME", "name": "Last Learn", "editor": "timestamp"},
                {"id": "GV1", "name": "Learn Count", "editor": "raw_value"},
                {"id": "GV2", "name": "Hub Connected", "editor": "binary_index"},
            ],
            "cmds": {
                "accepts": [
                    {"id": "LEARNCODE", "name": "Learn RF Code"},
                ],
                "sends": [],
            },
            "links": {"ctl": [], "rsp": []},
        },
        {
            "id": "blircode",
            "name": "IR Code",
            "icon": "GenericCtl",
            "properties": [
                {"id": "ST", "name": "Status", "editor": "tx_status"},
                {"id": "TIME", "name": "Created", "editor": "timestamp"},
                {"id": "GV1", "name": "Last Sent", "editor": "timestamp"},
                {"id": "GV2", "name": "Last Result", "editor": "tx_result"},
                {"id": "GV3", "name": "TX Count", "editor": "raw_value"},
            ],
            "cmds": {
                "accepts": [
                    {"id": "TXCODE", "name": "Send Code"},
                ],
                "sends": [],
            },
            "links": {"ctl": [], "rsp": []},
        },
        {
            "id": "blrfcode",
            "name": "RF Code",
            "icon": "GenericCtl",
            "properties": [
                {"id": "ST", "name": "Status", "editor": "tx_status"},
                {"id": "TIME", "name": "Created", "editor": "timestamp"},
                {"id": "GV1", "name": "Last Sent", "editor": "timestamp"},
                {"id": "GV2", "name": "Last Result", "editor": "tx_result"},
                {"id": "GV3", "name": "TX Count", "editor": "raw_value"},
            ],
            "cmds": {
                "accepts": [
                    {"id": "TXCODE", "name": "Send Code"},
                ],
                "sends": [],
            },
            "links": {"ctl": [], "rsp": []},
        },
        {
            "id": "blsensor",
            "name": "Hub Sensor",
            "icon": "GenericCtl",
            "properties": [
                {"id": "ST", "name": "Status", "editor": "status_index"},
                {"id": "GV2", "name": "Temperature", "editor": temp_editor_id},
                {"id": "GV3", "name": "Humidity", "editor": "humidity_pct"},
                {"id": "TIME", "name": "Last Update", "editor": "timestamp"},
            ],
            "cmds": {
                "accepts": [
                    {"id": "UPDATE", "name": "Update"},
                ],
                "sends": [],
            },
            "links": {"ctl": [], "rsp": []},
        },
def _parse_temp_unit(custom_params: dict) -> str:
    """Extract and normalize TEMP_UNIT from custom params. Returns 'C' or 'F'."""
    raw = str((custom_params or {}).get("TEMP_UNIT", "")).strip().upper()
    if raw in ("F", "FAHRENHEIT"):
        return "F"
    return "C"


@dataclass(slots=True)
class HubBlueprint:
    """Runtime representation of the configured hub for this PG3 instance."""

    ip_address: str
    display_name: str
    mac_address: str = ""
    device_type: str = "unknown"
    model_name: str = "unknown"
    connected: bool = False
    last_error: str = ""


class BaseNode(udi_interface.Node):
    """Common helpers shared by all nodes."""

    def _set(self, driver: str, value, uom: int | None = None, force: bool = False) -> None:
        if uom is None:
            self.setDriver(driver, value, True, force)
        else:
            self.setDriver(driver, value, True, force, uom=uom)


def _model_index(model_name: str) -> int:
    text = str(model_name or "").strip().lower()
    if not text or text == "unknown":
        return 0
    if text.startswith("rm4pro"):
        return 1
    if text.startswith("rm4mini"):
        return 2
    if text.startswith("rmpro"):
        return 3
    if text.startswith("rmmini"):
        return 4
    if text.startswith("rm2"):
        return 5
    return 6


class _ControllerNode(BaseNode):
    """Base class for IR and RF controller nodes.

    Subclasses set ``id``, ``_code_type`` ('ir' or 'rf'), and ``_learn_timeout``.
    Learning runs in a daemon thread so the LEARNCODE command returns immediately.
    """

    _code_type: str = "ir"
    _learn_timeout: int = 30

    drivers = [
        {"driver": "ST", "value": 0, "uom": 25},
        {"driver": "TIME", "value": 0, "uom": 151},
        {"driver": "GV1", "value": 0, "uom": 56},
        {"driver": "GV2", "value": 0, "uom": 25},
    ]

    def __init__(self, polyglot, primary, address: str, name: str, controller) -> None:
        super().__init__(polyglot, primary, address, name)
        self.controller = controller
        self._learn_thread: threading.Thread | None = None
        self._learn_count: int = 0

    def start(self) -> None:
        existing = [
            meta
            for meta in self.controller.learned_codes.values()
            if meta.get("controller_type") == self._code_type
        ]
        self._learn_count = len(existing)
        self._set("GV1", self._learn_count, 56)
        self._set("GV2", 1 if self.controller.hub_client and self.controller.hub_client.connected else 0)
        self._set("ST", 0)

    def learn_code(self, command=None) -> None:
        if self._learn_thread and self._learn_thread.is_alive():
            LOGGER.warning("[%s] Learn already in progress, ignoring command", type(self).__name__)
            return
        self._set("ST", 0)
        self._learn_thread = threading.Thread(
            target=self._do_learn, daemon=True, name=f"{self._code_type}-learn"
        )
        self._learn_thread.start()

    def _handle_learn_progress(self, event: str) -> None:
        state = LEARN_STATUS_BY_EVENT.get(self._code_type, {}).get(event)
        if state is not None:
            self._set("ST", state)

    def _do_learn(self) -> None:
        tag = type(self).__name__
        try:
            if not self.controller.hub_client:
                raise RuntimeError("Hub client not available")
            LOGGER.info("[%s._do_learn] Starting %s learn (%ds window)", tag, self._code_type.upper(), self._learn_timeout)
            if self._code_type == "rf":
                packet = self.controller.hub_client.learn_rf(
                    timeout_sec=self._learn_timeout,
                    progress_callback=self._handle_learn_progress,
                )
            else:
                packet = self.controller.hub_client.learn_ir(
                    timeout_sec=self._learn_timeout,
                    progress_callback=self._handle_learn_progress,
                )

            code_hex = packet.hex()
            addr = self.controller._next_code_address(self._code_type)
            name = f"{self._code_type.upper()} Code {addr[-3:]}"
            metadata: dict = {
                "name": name,
                "code_hex": code_hex,
                "created_at": int(time.time()),
                "last_sent": 0,
                "last_send_success": 0,
                "tx_count": 0,
                "controller_type": self._code_type,
                "controller_addr": self.address,
            }
            self.controller._persist_learned_code(addr, metadata)

            if self._code_type == "rf":
                code_node = RFCodeNode(self.poly, self.address, addr, name, self.controller)
            else:
                code_node = IRCodeNode(self.poly, self.address, addr, name, self.controller)
            code_node._code_meta = metadata
            self.poly.addNode(code_node)

            self._learn_count += 1
            self._set("ST", 4 if self._code_type == "rf" else 3)
            self._set("TIME", int(time.time()), 151)
            self._set("GV1", self._learn_count, 56)
            LOGGER.info("[%s._do_learn] Learned OK, stored as %s", tag, addr)
        except TimeoutError:
            LOGGER.warning("[%s._do_learn] Learn timed out after %ds", tag, self._learn_timeout)
            self._set("ST", 5 if self._code_type == "rf" else 4)
        except Exception as err:
            LOGGER.error("[%s._do_learn] Failed: %s", tag, err)
            self._set("ST", 5 if self._code_type == "rf" else 4)

    commands = {
        "LEARNCODE": learn_code,
    }


class IRControllerNode(_ControllerNode):
    """IR remote controller node."""

    id = "blirctl"
    _code_type = "ir"
    _learn_timeout = 30


class RFControllerNode(_ControllerNode):
    """RF remote controller node."""

    id = "blrfctl"
    _code_type = "rf"
    _learn_timeout = 45


class _CodeNode(BaseNode):
    """Base class for learned IR and RF code nodes.

    Subclasses set ``id``. Transmission tracking is persisted to customdata
    via the parent BroadlinkController.
    """

    drivers = [
        {"driver": "ST", "value": 0, "uom": 25},
        {"driver": "TIME", "value": 0, "uom": 151},
        {"driver": "GV1", "value": 0, "uom": 151},
        {"driver": "GV2", "value": 0, "uom": 25},
        {"driver": "GV3", "value": 0, "uom": 56},
    ]

    def __init__(self, polyglot, primary, address: str, name: str, controller) -> None:
        super().__init__(polyglot, primary, address, name)
        self.controller = controller
        self._code_meta: dict = {}

    def start(self) -> None:
        meta = self._code_meta
        self._set("TIME", meta.get("created_at", 0), 151)
        self._set("GV1", meta.get("last_sent", 0), 151)
        self._set("GV2", meta.get("last_send_success", 0), 25)
        self._set("GV3", meta.get("tx_count", 0), 56)
        self._set("ST", 0)  # Ready

    def send_code(self, command=None) -> None:
        meta = self._code_meta
        code_hex = meta.get("code_hex", "")
        if not code_hex:
            LOGGER.error("[%s.send_code] No code stored for %s", type(self).__name__, self.address)
            self._set("ST", 3)
            return
        if not self.controller.hub_client:
            LOGGER.error("[%s.send_code] Hub client not available", type(self).__name__)
            self._set("ST", 3)
            return

        self._set("ST", 1)  # Sending
        now = int(time.time())
        try:
            success = self.controller.hub_client.send_code(code_hex)
            meta["last_sent"] = now
            if success:
                meta["last_send_success"] = 1
                meta["tx_count"] = meta.get("tx_count", 0) + 1
                self._set("ST", 2)  # Sent OK
                self._set("GV2", 1, 25)
                self._set("GV3", meta["tx_count"], 56)
            else:
                meta["last_send_success"] = 2
                self._set("ST", 3)  # Failed
                self._set("GV2", 2, 25)
            self._set("GV1", now, 151)
            self.controller._persist_learned_code(self.address, meta)
        except Exception as err:
            LOGGER.error("[%s.send_code] Unexpected error: %s", type(self).__name__, err)
            meta["last_sent"] = now
            meta["last_send_success"] = 2
            self._set("ST", 3)
            self._set("GV1", now, 151)
            self._set("GV2", 2, 25)
            self.controller._persist_learned_code(self.address, meta)

    commands = {
        "TXCODE": send_code,
    }


class IRCodeNode(_CodeNode):
    """Learned IR code node."""

    id = "blircode"


class RFCodeNode(_CodeNode):
    """Learned RF code node."""

    id = "blrfcode"


class HubSensorNode(BaseNode):
    """Temperature/humidity child node under a specific hub."""

    id = "blsensor"
    drivers = [
        {"driver": "ST", "value": 0, "uom": 25},
        {"driver": "GV2", "value": 0, "uom": 17},
        {"driver": "GV3", "value": 0, "uom": 22},
        {"driver": "TIME", "value": 0, "uom": 151},
    ]

    def __init__(self, polyglot, primary, address: str, name: str, hub_node) -> None:
        super().__init__(polyglot, primary, address, name)
        self.hub_node = hub_node

    def start(self) -> None:
        self._set("ST", 1 if self.hub_node.hub_blueprint and self.hub_node.hub_blueprint.connected else 0)
        self._set("TIME", int(time.time()), 151)

    def force_update(self, command=None) -> None:
        self.hub_node._refresh_sensor_readings(self.hub_node.controller.temp_unit)

    commands = {"UPDATE": force_update}


class HubNode(BaseNode):
    """Node representing one Broadlink hub (type ``blhub``).

    One instance is created per configured hub IP.  It owns the IR/RF controller
    nodes and all learned code nodes beneath it.  Hub-specific logic (client
    connection, sensor detection, code persistence) lives here so
    ``BroadlinkController`` can remain a thin coordinator.
    """

    id = "blhub"
    drivers = [
        {"driver": "ST",   "value": 0, "uom": 25},   # status_index
        {"driver": "GV0",  "value": 0, "uom": 25},   # model_index
        {"driver": "GV1",  "value": 0, "uom": 25},   # binary_index
        {"driver": "TIME", "value": 0, "uom": 151},
    ]

    def __init__(self, polyglot, primary, address, name, controller, hub_ip: str) -> None:
        super().__init__(polyglot, primary, address, name)
        self.poly = polyglot
        self.controller = controller        # BroadlinkController
        self.hub_ip = hub_ip
        self.hub_client: BroadlinkHubClient | None = None
        self.hub_blueprint: HubBlueprint | None = None
        self.ir_controller: IRControllerNode | None = None
        self.rf_controller: RFControllerNode | None = None
        self.sensor_node: HubSensorNode | None = None
        self.learned_codes: dict[str, dict] = {}
        self._loaded_code_addrs: set[str] = set()
        self.has_temp_sensor: bool = False
        self.has_humidity_sensor: bool = False

    @property
    def hub_mac(self) -> str:
        """MAC-derived node address for this hub."""
        return self.address

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        self._detect_and_apply_sensors()
        self.reconcile()

    def reconcile(self, update_time: bool = True, trace_id: str = "") -> None:
        """Connect to hub, update drivers, and ensure child nodes exist."""
        trace = trace_id or "direct"
        LOGGER.debug("[HubNode.reconcile][%s] Starting reconcile for ip=%s addr=%s", trace, self.hub_ip, self.address)
        blueprint = self._build_blueprint()
        self.hub_blueprint = blueprint

        if blueprint is None:
            LOGGER.debug("[HubNode.reconcile][%s] No blueprint available for ip=%s", trace, self.hub_ip)
            self._set("ST", 0)
            return

        LOGGER.debug(
            "[HubNode.reconcile][%s] Blueprint resolved ip=%s connected=%s model=%s mac=%s error=%s",
            trace,
            self.hub_ip,
            blueprint.connected,
            blueprint.model_name,
            blueprint.mac_address,
            blueprint.last_error,
        )

        self._set("ST", 1 if blueprint.connected else 2 if blueprint.last_error else 0)
        self._set("GV0", _model_index(blueprint.model_name), 25)
        self._set("GV1", 1 if blueprint.connected else 0)

        self.controller.node_name_cache[self.address] = blueprint.display_name
        self.controller._persist_node_name_cache()

        if blueprint.connected:
            self.controller._remove_hub_error_notice(self.hub_mac)
            LOGGER.debug("[HubNode.reconcile][%s] Hub connected, ensuring child nodes for ip=%s", trace, self.hub_ip)
            self._ensure_controller_nodes(trace)
            # Detect sensor capability live so the optional sensor node is
            # created even when HubNode.start() was never called (e.g. when
            # START event is not delivered by PG3).
            self._detect_and_apply_sensors()
            self._ensure_sensor_node(trace)
            self._load_learned_codes(trace)
            self._refresh_sensor_readings(self.controller.temp_unit)
        else:
            if blueprint.last_error:
                self.controller._add_hub_error_notice(self.hub_mac, self.hub_ip, blueprint.last_error)

        if update_time:
            self._set("TIME", int(time.time()), 151)

    def poll_short(self, temp_unit: str) -> None:
        self._set("TIME", int(time.time()), 151)
        # If a sensor node exists, keep its readings fresh on each short poll.
        if self.sensor_node is not None:
            self._refresh_sensor_readings(temp_unit)

    def poll_long(self) -> None:
        if self.hub_client:
            self.hub_client.refresh()
        self.reconcile(update_time=False)

    # ------------------------------------------------------------------ hub connection

    def _build_blueprint(self) -> HubBlueprint | None:
        if not self.hub_ip:
            return None
        client = self._get_or_create_client()
        hub_info, error_text, connected = self._identify(client)

        if hub_info and hub_info.mac_address:
            mac = self.controller._normalize_hub_address(hub_info.mac_address)
            if mac:
                stored_macs = dict(self.controller.data_store.get("hub_macs") or {})
                if stored_macs.get(self.hub_ip) != mac:
                    stored_macs[self.hub_ip] = mac
                    self.controller.data_store["hub_macs"] = stored_macs

        display_name = self.controller._resolve_node_name(
            self.address, self._default_name(hub_info)
        )
        return HubBlueprint(
            ip_address=self.hub_ip,
            display_name=display_name,
            mac_address=hub_info.mac_address if hub_info else "",
            device_type=hub_info.device_type if hub_info else "unknown",
            model_name=hub_info.model_name if hub_info else "unknown",
            connected=connected,
            last_error=error_text,
        )

    def _get_or_create_client(self) -> BroadlinkHubClient:
        if self.hub_client is None or self.hub_client.hub_ip != self.hub_ip:
            self.hub_client = BroadlinkHubClient(hub_ip=self.hub_ip)
        return self.hub_client

    def _identify(self, client: BroadlinkHubClient) -> tuple[BroadlinkHubInfo | None, str, bool]:
        try:
            hub_info = client.ensure_connected()
            return hub_info, "", True
        except Exception as err:
            return client.hub_info, str(err), False

    def _default_name(self, hub_info: BroadlinkHubInfo | None) -> str:
        if hub_info is None:
            return f"Broadlink Hub ({self.hub_ip})"
        model_name = hub_info.model_name or "Broadlink Hub"
        return f"{model_name} ({self.hub_ip})"

    # ------------------------------------------------------------------ sensors

    def _detect_and_apply_sensors(self) -> None:
        if not self.hub_ip:
            return
        client = self._get_or_create_client()
        try:
            LOGGER.debug("[HubNode._detect_and_apply_sensors] Retrieving sensor capability for ip=%s", self.hub_ip)
            sensor_data = client.check_sensors()
            new_has_temp = sensor_data.has_temperature
            new_has_humidity = sensor_data.has_humidity
            LOGGER.debug(
                "[HubNode._detect_and_apply_sensors] Retrieved capability ip=%s has_temp=%s has_humidity=%s",
                self.hub_ip,
                new_has_temp,
                new_has_humidity,
            )
            if new_has_temp != self.has_temp_sensor or new_has_humidity != self.has_humidity_sensor:
                self.has_temp_sensor = new_has_temp
                self.has_humidity_sensor = new_has_humidity
                self._persist_sensor_state()
                self._ensure_sensor_node()
        except Exception as err:
            LOGGER.debug("[HubNode._detect_and_apply_sensors] %s: %s", self.hub_ip, err)

    def _refresh_sensor_readings(self, temp_unit: str) -> None:
        if not self.hub_client or not self.sensor_node:
            return
        try:
            sensor_data = self.hub_client.check_sensors()
            self.sensor_node._set("ST", 1)
            self.sensor_node._set("TIME", int(time.time()), 151)
            if sensor_data.has_temperature:
                temp_c = sensor_data.temperature_c
                display_val = round((temp_c * 9 / 5) + 32, 1) if temp_unit == "F" else round(temp_c, 1)
                self.sensor_node._set("GV2", display_val, 4 if temp_unit == "F" else 17)
            if sensor_data.has_humidity:
                self.sensor_node._set("GV3", round(sensor_data.humidity, 1), 22)
        except Exception as err:
            self.sensor_node._set("ST", 2)
            LOGGER.debug("[HubNode._refresh_sensor_readings] %s: %s", self.hub_ip, err)

    def _ensure_sensor_node(self, trace_id: str = "") -> None:
        trace = trace_id or "none"
        if not (self.has_temp_sensor or self.has_humidity_sensor):
            LOGGER.debug("[HubNode._ensure_sensor_node][%s] Skipping sensor node for ip=%s (no sensor capability)", trace, self.hub_ip)
            return
        if self.sensor_node is not None:
            LOGGER.debug("[HubNode._ensure_sensor_node][%s] Sensor node already exists for ip=%s", trace, self.hub_ip)
            return
        sensor_addr = self._sensor_address()
        sensor_name = self.controller._resolve_node_name(sensor_addr, f"Sensor ({self.hub_ip})")
        LOGGER.debug(
            "[HubNode._ensure_sensor_node][%s] Creating optional sensor node ip=%s addr=%s name=%s",
            trace,
            self.hub_ip,
            sensor_addr,
            sensor_name,
        )
        self.sensor_node = HubSensorNode(self.poly, self.address, sensor_addr, sensor_name, self)
        self.poly.addNode(self.sensor_node)
        LOGGER.info("[HubNode] Added HubSensorNode %s", sensor_addr)

    def _persist_sensor_state(self) -> None:
        sensor_states = dict(self.controller.data_store.get("sensor_states") or {})
        new_state = {"has_temp": self.has_temp_sensor, "has_humidity": self.has_humidity_sensor}
        if sensor_states.get(self.hub_mac) != new_state:
            sensor_states[self.hub_mac] = new_state
            self.controller.data_store["sensor_states"] = sensor_states

    # ------------------------------------------------------------------ child nodes

    def _ensure_controller_nodes(self, trace_id: str = "") -> None:
        trace = trace_id or "none"
        LOGGER.debug(
            "[HubNode._ensure_controller_nodes][%s] Ensuring IR/RF controllers for ip=%s addr=%s",
            trace,
            self.hub_ip,
            self.address,
        )
        if self.ir_controller is None:
            ir_addr = self._controller_address("ir")
            ir_name = self._resolve_controller_node_name(ir_addr, "ir")
            LOGGER.debug("[HubNode._ensure_controller_nodes][%s] Creating IR controller addr=%s name=%s", trace, ir_addr, ir_name)
            # Controller nodes must be top-level primaries so learned code
            # nodes can be their only direct children.
            self.ir_controller = IRControllerNode(self.poly, ir_addr, ir_addr, ir_name, self)
            self.poly.addNode(self.ir_controller)
            LOGGER.info("[HubNode] Added IRControllerNode %s", ir_addr)
        if self.rf_controller is None:
            rf_addr = self._controller_address("rf")
            rf_name = self._resolve_controller_node_name(rf_addr, "rf")
            LOGGER.debug("[HubNode._ensure_controller_nodes][%s] Creating RF controller addr=%s name=%s", trace, rf_addr, rf_name)
            # Controller nodes must be top-level primaries so learned code
            # nodes can be their only direct children.
            self.rf_controller = RFControllerNode(self.poly, rf_addr, rf_addr, rf_name, self)
            self.poly.addNode(self.rf_controller)
            LOGGER.info("[HubNode] Added RFControllerNode %s", rf_addr)

    def _resolve_controller_node_name(self, controller_addr: str, code_type: str) -> str:
        default_name = f"{code_type.upper()} Controller ({self.hub_ip})"
        legacy_names = {"IR Controller"} if code_type == "ir" else {"RF Controller", "RF Contrller"}

        db_name = self.poly.getNodeNameFromDb(controller_addr)
        if db_name:
            if db_name in legacy_names:
                self.controller.node_name_cache[controller_addr] = default_name
                self.controller._persist_node_name_cache()
                return default_name
            self.controller.node_name_cache[controller_addr] = db_name
            return db_name

        cached_name = self.controller.node_name_cache.get(controller_addr)
        if cached_name:
            if cached_name in legacy_names:
                self.controller.node_name_cache[controller_addr] = default_name
                self.controller._persist_node_name_cache()
                return default_name
            return cached_name

        return default_name

    def _load_learned_codes(self, trace_id: str = "") -> None:
        trace = trace_id or "none"
        total = len(self.learned_codes)
        already = len(self._loaded_code_addrs)
        LOGGER.debug(
            "[HubNode._load_learned_codes][%s] Preparing to restore code nodes for ip=%s total_cached=%d already_loaded=%d",
            trace,
            self.hub_ip,
            total,
            already,
        )
        if total:
            lines = []
            for addr, meta in self.learned_codes.items():
                code_type = meta.get("controller_type", "ir")
                name = meta.get("name") or "(unnamed)"
                has_data = bool(meta.get("code") or meta.get("data"))
                status = "loaded" if addr in self._loaded_code_addrs else "pending"
                lines.append(f"  {addr:<20} type={code_type:<4} name={name:<30} has_code={has_data} status={status}")
            LOGGER.debug(
                "[HubNode._load_learned_codes][%s] Cached codes for ip=%s:\n%s",
                trace,
                self.hub_ip,
                "\n".join(lines),
            )
        else:
            LOGGER.debug("[HubNode._load_learned_codes][%s] No cached codes for ip=%s", trace, self.hub_ip)
        for addr, meta in self.learned_codes.items():
            if addr in self._loaded_code_addrs:
                continue
            code_type = meta.get("controller_type", "ir")
            ctrl_addr = self._normalize_controller_addr(meta.get("controller_addr"), code_type)
            hub_display = self.hub_blueprint.display_name if self.hub_blueprint else self.hub_ip
            default_name = f"{hub_display} {code_type.upper()} Code"
            name = meta.get("name") or default_name
            raw_keys = [k for k in meta if k != "code"]
            LOGGER.debug(
                "[HubNode._load_learned_codes][%s] Restoring %s code addr=%s ctrl=%s name=%s meta_keys=%s",
                trace,
                code_type.upper(),
                addr,
                ctrl_addr,
                name,
                raw_keys,
            )
            if code_type == "rf":
                node: _CodeNode = RFCodeNode(self.poly, ctrl_addr, addr, name, self)
            else:
                node = IRCodeNode(self.poly, ctrl_addr, addr, name, self)
            node._code_meta = dict(meta)
            node._code_meta["controller_addr"] = ctrl_addr
            self.poly.addNode(node)
            self._loaded_code_addrs.add(addr)
            LOGGER.info("[HubNode] Restored %s code node %s", code_type.upper(), addr)

    # ------------------------------------------------------------------ persistence

    def _persist_learned_code(self, addr: str, metadata: dict) -> None:
        updated = dict(self.learned_codes)
        updated[addr] = dict(metadata)
        self.learned_codes = updated
        self._loaded_code_addrs.add(addr)
        all_codes = dict(self.controller.data_store.get("learned_codes") or {})
        all_codes[addr] = dict(metadata)
        stored = self.controller.data_store.get("learned_codes") or {}
        if stored != all_codes:
            self.controller.data_store["learned_codes"] = all_codes

    def _next_code_address(self, code_type: str) -> str:
        prefix = self._code_address_prefix(code_type)
        existing = [k for k in self.learned_codes if k.startswith(prefix)]
        return f"{prefix}{len(existing) + 1:03d}"

    def _controller_address(self, code_type: str) -> str:
        suffix = "ir" if code_type == "ir" else "rf"
        return f"{self.address}{suffix}"

    def _sensor_address(self) -> str:
        return f"{self.address}se"

    def _code_address_prefix(self, code_type: str) -> str:
        suffix = "i" if code_type == "ir" else "r"
        return f"{self.address[-10:]}{suffix}"

    def _normalize_controller_addr(self, controller_addr: str | None, code_type: str) -> str:
        current_addr = self._controller_address(code_type)
        legacy_addrs = {"ir": "irctrl", "rf": "rfctrl"}
        if controller_addr in (None, "", legacy_addrs.get(code_type),
                               f"{DEFAULT_SETUP_ADDRESS}_{code_type}",
                               f"{DEFAULT_SETUP_ADDRESS}{code_type}"):
            return current_addr
        return controller_addr

    def _sync_node_names_from_db(self) -> None:
        db_name = self.poly.getNodeNameFromDb(self.address)
        if db_name:
            self.name = db_name
        self.controller.node_name_cache[self.address] = self.name
        self.controller._persist_node_name_cache()

    def sync_all_node_names(self) -> None:
        """Flush hub and all child node names to cache (called on stop)."""
        self._sync_node_names_from_db()
        for addr in (self._controller_address("ir"), self._controller_address("rf")):
            db_name = self.poly.getNodeNameFromDb(addr)
            if db_name:
                self.controller.node_name_cache[addr] = db_name
        sensor_addr = self._sensor_address()
        db_name = self.poly.getNodeNameFromDb(sensor_addr)
        if db_name:
            self.controller.node_name_cache[sensor_addr] = db_name
        codes_changed = False
        updated_codes = dict(self.learned_codes)
        for addr in list(self.learned_codes.keys()):
            db_name = self.poly.getNodeNameFromDb(addr)
            if db_name:
                self.controller.node_name_cache[addr] = db_name
                if updated_codes[addr].get("name") != db_name:
                    updated_codes[addr] = dict(updated_codes[addr])
                    updated_codes[addr]["name"] = db_name
                    codes_changed = True
        if codes_changed:
            self.learned_codes = updated_codes
            all_codes = dict(self.controller.data_store.get("learned_codes") or {})
            all_codes.update(updated_codes)
            stored = self.controller.data_store.get("learned_codes") or {}
            if stored != all_codes:
                self.controller.data_store["learned_codes"] = all_codes
        self.controller._persist_node_name_cache()

    def force_update(self, command=None) -> None:
        self._detect_and_apply_sensors()
        self.reconcile()

    commands = {"UPDATE": force_update}



class BroadlinkController(BaseNode):
    """Coordinator primary node for all configured Broadlink hubs."""

    id = "setup"
    drivers = [
        {"driver": "ST", "value": 0, "uom": 25},    # hub_status: 0=none configured, 1=all online, 2=partial, 3=none online
        {"driver": "GV0", "value": 0, "uom": 56},   # hub count
        {"driver": "TIME", "value": int(time.time()), "uom": 151},
    ]

    def __init__(self, polyglot, primary, address, name):
        LOGGER.info("[__init__] Constructing BroadlinkController")
        super().__init__(polyglot, primary, address, name)
        self.drivers = [dict(driver) for driver in type(self).drivers]
        self.poly = polyglot
        self.config = PluginConfig()
        self.parameters = Custom(self.poly, "customparams")
        self.data_store = Custom(self.poly, "customdata")
        self.heartbeat_state = 0
        self.hub_nodes: dict[str, "HubNode"] = {}   # keyed by hub IP
        self.node_name_cache: dict[str, str] = {}
        self.temp_unit: str = "C"
        self._node_added: bool = False
        self._ready_signaled: bool = False
        self._bootstrap_applied: bool = False
        self._startup_completed: bool = False
        self._reconcile_seq: int = 0
        self._confirmed_node_addresses: set[str] = set()
        LOGGER.debug("[__init__] Initialized instance variables")

        LOGGER.debug("[__init__] Subscribing to polyglot events")
        self.poly.subscribe(self.poly.START, self.start)
        self.poly.subscribe(self.poly.STOP, self.stop)
        self.poly.subscribe(self.poly.POLL, self.poll)
        self.poly.subscribe(self.poly.CUSTOMPARAMS, self.handle_params)
        self.poly.subscribe(self.poly.CUSTOMDATA, self.handle_custom_data)
        typed_data_event = getattr(self.poly, "CUSTOMTYPEDDATA", None)
        if typed_data_event is not None:
            self.poly.subscribe(typed_data_event, self.handle_custom_data)
        self.poly.subscribe(self.poly.LOGLEVEL, self.handle_log_level)
        self.poly.subscribe(self.poly.DISCOVER, self.discover)
        self.poly.subscribe(self.poly.ADDNODEDONE, self.node_done)
        self.poly.subscribe(self.poly.CONFIGDONE, self.config_done)
        LOGGER.debug("[__init__] Event subscriptions registered")

        # Register setup node immediately so startup does not depend on
        # CUSTOMDATA/CUSTOMPARAMS event ordering.
        self._ensure_registered()

        LOGGER.info("[__init__] Publishing JSON profile")
        self._publish_profile()

        # Signal PG3 that the node server is ready. PG3 will then send
        # CUSTOMPARAMS, CUSTOMDATA, and START. Without this call the START
        # event is never delivered (deadlock).
        LOGGER.info("[__init__] Calling poly.ready() to signal PG3")
        self.poly.ready()
        self._ready_signaled = True

        LOGGER.info("[__init__] BroadlinkController construction complete")

    def start(self, *_args, **_kwargs) -> None:
        LOGGER.info("[start] Received START event")
        self._run_startup_once("START")

    def _run_startup_once(self, source: str) -> None:
        """Execute startup initialization once, even if START was missed."""
        if self._startup_completed:
            return
        if source != "START":
            LOGGER.warning("[_run_startup_once] START event not observed, running startup via %s", source)
        if not self._node_added:
            # START can arrive before CUSTOMDATA; ensure the setup node exists.
            self._ensure_registered()
        self._bootstrap_config_if_needed()
        self._set("TIME", int(time.time()), 151)
        if self.config.has_hub and not self.hub_nodes:
            self._reconcile_hub_nodes()
        for hub_node in list(self.hub_nodes.values()):
            hub_node.start()
        self._update_overall_status()
        # Wait for all nodes to be done
        node_queue = getattr(self.poly, "node_queue", [])
        while node_queue:
            time.sleep(0.1)
        if not self._ready_signaled:
            LOGGER.info("[_run_startup_once] Signaling polyglot ready (late fallback)")
            self.poly.ready()
            self._ready_signaled = True
        self._startup_completed = True
        LOGGER.info("[_run_startup_once] Startup reconciliation complete via %s", source)

    def stop(self, *_args, **_kwargs) -> None:
        if not self._node_added:
            self.poly.stop()
            return
        for hub_node in list(self.hub_nodes.values()):
            hub_node.sync_all_node_names()
        self._set("ST", 0)
        self.poly.stop()

    def handle_log_level(self, level) -> None:
        if isinstance(level, dict) and "level" in level:
            LOGGER.info("New log level: %s", level["level"])

    def node_done(self, node) -> None:
        address = getattr(node, "address", None)
        if address is None and isinstance(node, dict):
            address = node.get("address") or node.get("node")
        if address:
            self._confirmed_node_addresses.add(address)
        LOGGER.debug("[node_done] Node %s is done", address or "unknown")

    def config_done(self, _config=None, *_args, **_kwargs) -> None:
        LOGGER.debug("[config_done] Configuration done")

    def handle_params(self, custom_params) -> None:
        LOGGER.info("[handle_params] CUSTOMPARAMS event received")
        self._bootstrap_applied = True
        self._ensure_registered()
        self.parameters.load(custom_params)
        self.poly.Notices.clear()

        prev_temp_unit = self.temp_unit
        try:
            self.config = build_config(custom_params)
        except Exception as err:
            self.poly.Notices["config"] = f"Invalid configuration format: {err}"
            LOGGER.error("[handle_params] Failed to parse custom params: %s", err)
            if self._node_added:
                self._set("ST", 0)
                self._set("GV0", 0)
            return

        self.temp_unit = _parse_temp_unit(custom_params)

        if not self.config.has_hub:
            self.poly.Notices["required"] = (
                "Set HUB_IP to the IP address(es) of your Broadlink hub(s). "
                "Separate multiple IPs with commas."
            )
            if self._node_added:
                self._set("ST", 0)
                self._set("GV0", 0)
            return

        LOGGER.info("[handle_params] Configured hub IPs: %s", self.config.hub_ips)
        if self._node_added:
            self._set("GV0", len(self.config.hub_ips))

        if self.temp_unit != prev_temp_unit:
            LOGGER.info("[handle_params] TEMP_UNIT changed from %s to %s", prev_temp_unit, self.temp_unit)
            self._publish_profile()

        self._reconcile_hub_nodes()
        self._publish_profile()

    def handle_custom_data(self, custom_data) -> None:
        # PG3 can emit empty custom payload callbacks (e.g. customtypeddata),
        # and loading {} would wipe persisted learned_codes.
        if custom_data is None:
            LOGGER.debug("[handle_custom_data] Ignoring None custom_data payload")
            return
        if isinstance(custom_data, dict) and not custom_data:
            LOGGER.debug("[handle_custom_data] Ignoring empty custom_data payload to preserve persisted state")
            return

        if isinstance(custom_data, dict):
            # Merge onto existing data so partial payloads don't drop keys like
            # learned_codes/sensor_states/hub_macs.
            merged = dict(self.data_store or {})
            merged.update(custom_data)
            self.data_store.load(merged)
        else:
            # Fallback for unexpected payload types.
            self.data_store.load(custom_data)
        self.node_name_cache = self._safe_name_map(self.data_store.get("node_names", {}))
        self._migrate_legacy_data()
        self._ensure_registered()
        # Hub nodes are created by _reconcile_hub_nodes() so all configured hubs
        # can be connected first before any node is added.
        if self._node_added:
            self._sync_node_names_from_db()

    def poll(self, poll_type=None, *_args, **_kwargs) -> None:
        if not self._node_added:
            return
        if not self._startup_completed:
            self._run_startup_once("POLL")
        poll_name = poll_type if isinstance(poll_type, str) else "longPoll"
        self._set("TIME", int(time.time()), 151)
        if poll_name == "shortPoll":
            self.heartbeat_state = 1 - self.heartbeat_state
            if self.heartbeat_state:
                self.reportCmd("DON", 2)
            else:
                self.reportCmd("DOF", 2)
            for hub_node in list(self.hub_nodes.values()):
                hub_node.poll_short(self.temp_unit)
        else:
            for hub_node in list(self.hub_nodes.values()):
                hub_node.poll_long()
            self._sync_node_names_from_db()
            self._cleanup_deleted_codes()
            self._update_overall_status()

    def discover(self, *_) -> None:
        self._reconcile_hub_nodes()

    # ------------------------------------------------------------------ hub node management

    def _ensure_registered(self) -> None:
        """Add the BroadlinkController node to poly if not yet registered."""
        if not self._node_added:
            self.poly.addNode(self, conn_status="ST", rename=False)
            self._node_added = True

    def _bootstrap_config_if_needed(self) -> None:
        """Best-effort load of existing config when CUSTOMPARAMS callbacks are absent."""
        if self._bootstrap_applied or self.config.has_hub:
            return
        payload = self._get_bootstrap_param_payload()
        if not payload:
            return
        LOGGER.info("[_bootstrap_config_if_needed] Applying startup configuration from interface payload")
        self.handle_params(payload)

    def _get_bootstrap_param_payload(self) -> dict:
        """Return a candidate config payload from interface state/getter methods."""
        sources = []
        for attr_name in ("polyConfig", "polyconfig", "config", "Config"):
            value = getattr(self.poly, attr_name, None)
            if isinstance(value, dict):
                sources.append(value)

        get_config = getattr(self.poly, "getConfig", None)
        if callable(get_config):
            try:
                value = get_config()
                if isinstance(value, dict):
                    sources.append(value)
            except Exception as err:
                LOGGER.debug("[_get_bootstrap_param_payload] getConfig failed: %s", err)

        for source in sources:
            for key in (
                "customparams",
                "customParams",
                "params",
                "customtypedparams",
                "customTypedParams",
                "typedparams",
                "typed_parameters",
                "customtypeddata",
                "customTypedData",
                "typed_data",
            ):
                candidate = source.get(key)
                if isinstance(candidate, (dict, list)) and candidate:
                    return {key: candidate}
        return {}

    def _wait_for_node_confirmed(self, address: str, timeout: float = 15.0) -> bool:
        """Block until PG3 sends ADDNODEDONE for *address*, or timeout expires.

        This is the ``wait_for_node_ready`` pattern: after calling
        ``poly.addNode(hub_node)`` we must not add child nodes until PG3 has
        confirmed the parent.  PG3 signals confirmation via the ``addnode``
        response message which udi_interface publishes as ADDNODEDONE.
        """
        if address in self._confirmed_node_addresses:
            LOGGER.debug("[_wait_for_node_confirmed] Node %s already confirmed", address)
            return True

        event = threading.Event()

        def _handler(node):
            node_addr = node.get("address") if isinstance(node, dict) else getattr(node, "address", None)
            if node_addr == address:
                event.set()

        self.poly.subscribe(self.poly.ADDNODEDONE, _handler)
        if address in self._confirmed_node_addresses:
            self.poly.unsubscribe(self.poly.ADDNODEDONE, _handler)
            LOGGER.debug("[_wait_for_node_confirmed] Node %s confirmed before local wait", address)
            return True
        confirmed = event.wait(timeout=timeout)
        self.poly.unsubscribe(self.poly.ADDNODEDONE, _handler)
        if not confirmed:
            LOGGER.warning("[_wait_for_node_confirmed] Timeout waiting for PG3 to confirm node %s", address)
        else:
            LOGGER.debug("[_wait_for_node_confirmed] PG3 confirmed node %s", address)
        return confirmed

    def _reconcile_hub_nodes(self) -> None:
        """Connect each hub, add its node, wait for PG3 confirmation, then add children.

        Hubs are processed one at a time (serial) so that each parent hub node
        is confirmed by PG3 before child IR/RF/Sensor nodes are created.
        """
        self._reconcile_seq += 1
        trace_id = f"rec-{self._reconcile_seq:06d}"
        hub_macs = self._safe_hub_macs()
        LOGGER.debug(
            "[_reconcile_hub_nodes][%s] Begin pass configured_hubs=%s known_hub_macs=%s",
            trace_id,
            self.config.hub_ips,
            hub_macs,
        )

        for ip in self.config.hub_ips:
            if ip in self.hub_nodes:
                # Hub node already confirmed in a previous run — just reconcile.
                LOGGER.debug("[_reconcile_hub_nodes][%s] Hub node already exists for ip=%s, reconciling", trace_id, ip)
                self.hub_nodes[ip].reconcile(trace_id=trace_id)
                continue

            # New hub: get identity, add node, wait for PG3 confirmation, then children.
            mac = hub_macs.get(ip)
            client = None
            if not mac:
                LOGGER.debug("[_reconcile_hub_nodes][%s] No stored MAC for ip=%s, connecting for identity", trace_id, ip)
                connected_mac, client = self._connect_hub_identity(ip, trace_id)
                if not connected_mac:
                    LOGGER.warning("[_reconcile_hub_nodes][%s] Identity retrieval failed for ip=%s, skipping", trace_id, ip)
                    continue
                mac = connected_mac
            else:
                LOGGER.debug("[_reconcile_hub_nodes][%s] Using stored MAC for ip=%s mac=%s", trace_id, ip, mac)

            node = self._create_hub_node(ip, mac, trace_id)
            if not node:
                LOGGER.debug("[_reconcile_hub_nodes][%s] HubNode creation skipped for ip=%s mac=%s", trace_id, ip, mac)
                continue

            if client is not None:
                LOGGER.debug("[_reconcile_hub_nodes][%s] Attaching active client to node ip=%s", trace_id, ip)
                node.hub_client = client
            self._restore_hub_node_data(node, trace_id)

            # Wait for PG3 to confirm the hub node before adding children.
            LOGGER.debug(
                "[_reconcile_hub_nodes][%s] Waiting for PG3 to confirm hub node ip=%s addr=%s",
                trace_id, ip, node.address,
            )
            if self._wait_for_node_confirmed(node.address, timeout=15.0):
                LOGGER.debug("[_reconcile_hub_nodes][%s] Hub confirmed, reconciling children for ip=%s", trace_id, ip)
                node.reconcile(trace_id=trace_id)
            else:
                LOGGER.warning(
                    "[_reconcile_hub_nodes][%s] PG3 did not confirm hub ip=%s within timeout — children not created",
                    trace_id, ip,
                )

        self._update_overall_status()

    def _connect_hub_identity(self, ip: str, trace_id: str = "") -> tuple[str, BroadlinkHubClient | None]:
        """Connect to a hub and return its normalized MAC with active client."""
        trace = trace_id or "none"
        try:
            LOGGER.debug("[_connect_hub_identity][%s] Connecting to hub ip=%s for identity retrieval", trace, ip)
            client = BroadlinkHubClient(hub_ip=ip)
            hub_info = client.ensure_connected()
            if hub_info and hub_info.mac_address:
                mac = self._normalize_hub_address(hub_info.mac_address)
                if mac:
                    hub_macs = dict(self.data_store.get("hub_macs") or {})
                    if hub_macs.get(ip) != mac:
                        hub_macs[ip] = mac
                        self.data_store["hub_macs"] = hub_macs
                    LOGGER.debug(
                        "[_connect_hub_identity][%s] Retrieved hub identity ip=%s mac=%s model=%s",
                        trace,
                        ip,
                        mac,
                        hub_info.model_name,
                    )
                    return mac, client
            LOGGER.debug("[_connect_hub_identity][%s] No MAC returned from hub identity ip=%s", trace, ip)
        except Exception as err:
            LOGGER.warning("[_connect_hub_identity][%s] Failed for %s: %s", trace, ip, err)
            self.poly.Notices[f"hub_connect_{ip.replace('.', '_')}"] = (
                f"Could not connect to hub at {ip}: {err}"
            )
        return "", None

    def _create_hub_node(self, ip: str, mac: str, trace_id: str = "") -> "HubNode | None":
        """Instantiate a HubNode and add it to poly (idempotent by IP)."""
        trace = trace_id or "none"
        if ip in self.hub_nodes:
            return self.hub_nodes[ip]
        if not self._normalize_hub_address(mac):
            LOGGER.debug("[_create_hub_node][%s] Invalid MAC for ip=%s mac=%s", trace, ip, mac)
            return None
        name = self._resolve_node_name(mac, f"Broadlink Hub ({ip})")
        LOGGER.debug("[_create_hub_node][%s] Creating HubNode ip=%s mac=%s name=%s", trace, ip, mac, name)
        # Hub nodes must be top-level primaries so the optional sensor node
        # can be their only direct child.
        hub_node = HubNode(self.poly, mac, mac, name, self, ip)
        self.poly.addNode(hub_node)
        self.hub_nodes[ip] = hub_node
        LOGGER.info("[_create_hub_node] Added HubNode ip=%s mac=%s", ip, mac)
        return hub_node

    def _restore_hub_node_data(self, hub_node: "HubNode", trace_id: str = "") -> None:
        """Load persisted sensor state and learned codes into a HubNode."""
        trace = trace_id or "none"
        mac = hub_node.hub_mac
        LOGGER.debug("[_restore_hub_node_data][%s] Retrieving persisted data for hub mac=%s ip=%s", trace, mac, hub_node.hub_ip)
        sensor_states = self.data_store.get("sensor_states") or {}
        sensor_state = sensor_states.get(mac) or {}
        hub_node.has_temp_sensor = bool(sensor_state.get("has_temp", False))
        hub_node.has_humidity_sensor = bool(sensor_state.get("has_humidity", False))
        LOGGER.debug(
            "[_restore_hub_node_data][%s] Restored sensor options mac=%s has_temp=%s has_humidity=%s",
            trace,
            mac,
            hub_node.has_temp_sensor,
            hub_node.has_humidity_sensor,
        )
        # Do not create optional sensor nodes from cached state alone.
        # Live detection in HubNode.reconcile() decides whether a sensor
        # node should exist for this runtime.
        all_codes = self._safe_code_map(self.data_store.get("learned_codes", {}))
        hub_node.learned_codes = {
            addr: meta
            for addr, meta in all_codes.items()
            if addr.startswith(mac[-10:])
        }
        LOGGER.debug(
            "[_restore_hub_node_data][%s] Restored learned code metadata mac=%s code_count=%d",
            trace,
            mac,
            len(hub_node.learned_codes),
        )

    def _update_overall_status(self) -> None:
        if not self.hub_nodes:
            self._set("ST", 0)
            return
        connected = sum(
            1 for n in self.hub_nodes.values()
            if n.hub_blueprint and n.hub_blueprint.connected
        )
        total = len(self.hub_nodes)
        self._set("ST", 1 if connected == total else 2 if connected > 0 else 3)

    def _add_hub_error_notice(self, mac: str, ip: str, error: str) -> None:
        self.poly.Notices[f"hub_err_{mac}"] = f"Hub {ip}: {error}"

    def _remove_hub_error_notice(self, mac: str) -> None:
        self.poly.Notices.delete(f"hub_err_{mac}")

    # ------------------------------------------------------------------ data helpers

    def _safe_hub_macs(self) -> dict[str, str]:
        """Return the IP→MAC mapping from customdata, migrating legacy single-hub data."""
        hub_macs = self.data_store.get("hub_macs") or {}
        if not isinstance(hub_macs, dict):
            hub_macs = {}
        # Legacy migration: if old hub_address exists map it to the first configured IP
        legacy_mac = self._normalize_hub_address(self.data_store.get("hub_address", ""))
        if legacy_mac and self.config.hub_ips:
            for ip in self.config.hub_ips:
                if ip not in hub_macs:
                    hub_macs = dict(hub_macs)
                    hub_macs[ip] = legacy_mac
                    stored = self.data_store.get("hub_macs")
                    if stored != hub_macs:
                        self.data_store["hub_macs"] = hub_macs
                    break
        return {k: v for k, v in hub_macs.items() if isinstance(k, str) and isinstance(v, str)}

    def _migrate_legacy_data(self) -> None:
        """Migrate old single-hub customdata keys to multi-hub structure (one-time)."""
        old_sensor_state = self.data_store.get("sensor_state")
        if old_sensor_state and not self.data_store.get("sensor_states"):
            legacy_mac = self._normalize_hub_address(self.data_store.get("hub_address", ""))
            if legacy_mac and isinstance(old_sensor_state, dict):
                self.data_store["sensor_states"] = {legacy_mac: old_sensor_state}

    def _publish_profile(self) -> None:
        update_json_profile = getattr(self.poly, "updateJsonProfile", None)
        if not callable(update_json_profile):
            LOGGER.error("[_publish_profile] updateJsonProfile is unavailable")
            self.poly.Notices["profile"] = "Dynamic profile publish failed: updateJsonProfile() is unavailable."
            return

        profile = _build_profile_definition(self.temp_unit)

        current_profile_getter = getattr(self.poly, "getJsonProfile", None)
        if callable(current_profile_getter):
            try:
                # Do not block startup waiting on profile response; this method
                # is called before poly.ready(), and synchronous waits can delay
                # CUSTOMPARAMS/START delivery and make startup appear stuck.
                current_profile = current_profile_getter({"waitResponse": False})
                if self._profiles_match(current_profile, profile):
                    LOGGER.info("[_publish_profile] Profile already up to date, skipping publish")
                    return
            except TypeError:
                current_profile = current_profile_getter()
                if self._profiles_match(current_profile, profile):
                    LOGGER.info("[_publish_profile] Profile already up to date, skipping publish")
                    return
            except Exception as err:
                LOGGER.warning("[_publish_profile] Unable to read existing profile: %s", err)

        try:
            #LOGGER.debug("[_publish_profile] Publishing profile: %s",
            #             json.dumps(profile, sort_keys=True, indent=2, separators=(",", ": ")))
            update_json_profile(profile, {"waitResponse": False})
            LOGGER.info("[_publish_profile] Dynamic JSON profile published successfully")
            self.poly.Notices.delete("profile")
        except TypeError:
            update_json_profile(profile)
            LOGGER.info("[_publish_profile] Dynamic JSON profile published successfully")
            self.poly.Notices.delete("profile")
        except Exception as err:
            LOGGER.error("[_publish_profile] Profile publish failed: %s", err)
            self.poly.Notices["profile"] = f"Dynamic profile publish failed: {err}"

    def _profiles_match(self, current_profile, expected_profile) -> bool:
        if not isinstance(current_profile, dict) or not isinstance(expected_profile, dict):
            return False
        return all(
            current_profile.get(k, []) == expected_profile.get(k, [])
            for k in ("editors", "nodedefs", "linkdefs")
        )

    def _resolve_node_name(self, address: str, default_name: str) -> str:
        if address:
            db_name = self.poly.getNodeNameFromDb(address)
            if db_name:
                self.node_name_cache[address] = db_name
                return db_name
            if address in self.node_name_cache:
                return self.node_name_cache[address]
        return default_name

    def _sync_node_names_from_db(self) -> None:
        if not self._node_added:
            return
        db_name = self.poly.getNodeNameFromDb(self.address)
        resolved_name = db_name or self.node_name_cache.get(self.address)
        if resolved_name:
            self.name = resolved_name
        self.node_name_cache[self.address] = self.name
        self._persist_node_name_cache()

    def _persist_node_name_cache(self) -> None:
        stored = self._safe_name_map(self.data_store.get("node_names", {}))
        desired = dict(self.node_name_cache)
        if stored != desired:
            self.data_store["node_names"] = desired

    def _normalize_hub_address(self, candidate) -> str:
        text = "".join(ch for ch in str(candidate or "").lower() if ch in "0123456789abcdef")
        return text if len(text) == 12 else ""

    def _safe_name_map(self, candidate) -> dict[str, str]:
        if not isinstance(candidate, dict):
            return {}
        parsed: dict[str, str] = {}
        for key, value in candidate.items():
            k, v = str(key).strip(), str(value).strip()
            if k and v:
                parsed[k] = v
        return parsed

    def _safe_code_map(self, candidate) -> dict[str, dict]:
        if not isinstance(candidate, dict):
            return {}
        parsed: dict[str, dict] = {}
        for key, value in candidate.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue
            addr = key.strip()
            if addr:
                parsed[addr] = dict(value)
        return parsed

    def _cleanup_deleted_codes(self) -> None:
        """Remove learned codes from customdata if their nodes have been deleted."""
        if not self._node_added:
            return
        try:
            existing_nodes = self.poly.getNodes()
            # getNodes() returns a dict {address: node} in udi_interface 3.x;
            # fall back gracefully if it ever returns a list.
            if isinstance(existing_nodes, dict):
                existing_addrs = set(existing_nodes.keys())
            else:
                existing_addrs = {node.address for node in existing_nodes}
            all_codes = self._safe_code_map(self.data_store.get("learned_codes", {}))
            to_remove = [addr for addr in all_codes if addr not in existing_addrs]
            if to_remove:
                updated_codes = {k: v for k, v in all_codes.items() if k not in to_remove}
                self.data_store["learned_codes"] = updated_codes
                # Update in-memory copies in hub nodes
                for hub_node in self.hub_nodes.values():
                    hub_node.learned_codes = {
                        addr: meta
                        for addr, meta in hub_node.learned_codes.items()
                        if addr not in to_remove
                    }
                LOGGER.info("[_cleanup_deleted_codes] Cleaned up deleted code nodes: %s", to_remove)
        except Exception as err:
            LOGGER.warning("[_cleanup_deleted_codes] Failed: %s", err)

    def force_update(self, command=None) -> None:
        self._reconcile_hub_nodes()

    commands = {"UPDATE": force_update}
