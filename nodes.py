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
VERSION = "0.2.0"

MODEL_INDEX_NAMES = {
    "0": "Unknown",
    "1": "RM4 Pro",
    "2": "RM4 Mini",
    "3": "RM Pro",
    "4": "RM Mini",
    "5": "RM2",
    "6": "Other Broadlink",
}

def _build_profile_definition(
    has_temp: bool = False,
    has_humidity: bool = False,
    temp_unit: str = "C",
) -> dict:
    """Build the dynamic JSON profile definition.

    Conditionally includes temperature (GV2) and humidity (GV3) drivers on the
    setup node based on detected sensor cable state. Temperature UOM is chosen
    based on temp_unit: 'C' → UOM 17 (°C), 'F' → UOM 4 (°F).
    """
    temp_editor_id = "temp_f" if temp_unit == "F" else "temp_c"

    editors = [
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
            "id": "learn_status",
            "ranges": [{"uom": "25", "subset": "0-3", "names": {"0": "Idle", "1": "Learning", "2": "Learned OK", "3": "Failed"}}],
        },
        {
            "id": "tx_status",
            "ranges": [{"uom": "25", "subset": "0-3", "names": {"0": "Ready", "1": "Sending", "2": "Sent OK", "3": "Failed"}}],
        },
        {
            "id": "tx_result",
            "ranges": [{"uom": "25", "subset": "0-2", "names": {"0": "Never", "1": "Success", "2": "Failed"}}],
        },
    ]

    if has_temp:
        editors.append({"id": "temp_c", "ranges": [{"uom": "17", "min": -40, "max": 125, "prec": 1}]})
        editors.append({"id": "temp_f", "ranges": [{"uom": "4", "min": -40, "max": 257, "prec": 1}]})
    if has_humidity:
        editors.append({"id": "humidity_pct", "ranges": [{"uom": "22", "min": 0, "max": 100, "prec": 1}]})

    setup_properties = [
        {"id": "ST", "name": "Status", "editor": "status_index"},
        {"id": "GV0", "name": "Model", "editor": "model_index"},
        {"id": "GV1", "name": "Connected", "editor": "binary_index"},
        {"id": "TIME", "name": "Last Update", "editor": "timestamp"},
    ]
    if has_temp:
        setup_properties.append({"id": "GV2", "name": "Temperature", "editor": temp_editor_id})
    if has_humidity:
        setup_properties.append({"id": "GV3", "name": "Humidity", "editor": "humidity_pct"})

    nodedefs = [
        {
            "id": "setup",
            "nls": "nlssetup",
            "icon": "GenericCtl",
            "properties": setup_properties,
            "cmds": {
                "accepts": [
                    {"id": "QUERY", "name": "Query"},
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
            "id": "blirctl",
            "nls": "nlsirctl",
            "icon": "GenericCtl",
            "properties": [
                {"id": "ST", "name": "Status", "editor": "learn_status"},
                {"id": "GV0", "name": "Last Learn", "editor": "timestamp"},
                {"id": "GV1", "name": "Learn Count", "editor": "raw_value"},
                {"id": "GV2", "name": "Hub Connected", "editor": "binary_index"},
            ],
            "cmds": {
                "accepts": [
                    {"id": "LEARNCODE", "name": "Learn IR Code"},
                    {"id": "QUERY", "name": "Query"},
                ],
                "sends": [],
            },
            "links": {"ctl": [], "rsp": []},
        },
        {
            "id": "blrfctl",
            "nls": "nlsrfctl",
            "icon": "GenericCtl",
            "properties": [
                {"id": "ST", "name": "Status", "editor": "learn_status"},
                {"id": "GV0", "name": "Last Learn", "editor": "timestamp"},
                {"id": "GV1", "name": "Learn Count", "editor": "raw_value"},
                {"id": "GV2", "name": "Hub Connected", "editor": "binary_index"},
            ],
            "cmds": {
                "accepts": [
                    {"id": "LEARNCODE", "name": "Learn RF Code"},
                    {"id": "QUERY", "name": "Query"},
                ],
                "sends": [],
            },
            "links": {"ctl": [], "rsp": []},
        },
        {
            "id": "blircode",
            "nls": "nlsircode",
            "icon": "GenericCtl",
            "properties": [
                {"id": "ST", "name": "Status", "editor": "tx_status"},
                {"id": "GV0", "name": "Created", "editor": "timestamp"},
                {"id": "GV1", "name": "Last Sent", "editor": "timestamp"},
                {"id": "GV2", "name": "Last Result", "editor": "tx_result"},
                {"id": "GV3", "name": "TX Count", "editor": "raw_value"},
            ],
            "cmds": {
                "accepts": [
                    {"id": "TXCODE", "name": "Send Code"},
                    {"id": "QUERY", "name": "Query"},
                ],
                "sends": [],
            },
            "links": {"ctl": [], "rsp": []},
        },
        {
            "id": "blrfcode",
            "nls": "nlsrfcode",
            "icon": "GenericCtl",
            "properties": [
                {"id": "ST", "name": "Status", "editor": "tx_status"},
                {"id": "GV0", "name": "Created", "editor": "timestamp"},
                {"id": "GV1", "name": "Last Sent", "editor": "timestamp"},
                {"id": "GV2", "name": "Last Result", "editor": "tx_result"},
                {"id": "GV3", "name": "TX Count", "editor": "raw_value"},
            ],
            "cmds": {
                "accepts": [
                    {"id": "TXCODE", "name": "Send Code"},
                    {"id": "QUERY", "name": "Query"},
                ],
                "sends": [],
            },
            "links": {"ctl": [], "rsp": []},
        },
    ]

    return {"editors": editors, "nodedefs": nodedefs, "linkdefs": []}


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
        {"driver": "GV0", "value": 0, "uom": 151},
        {"driver": "GV1", "value": 0, "uom": 56},
        {"driver": "GV2", "value": 0, "uom": 25},
    ]

    def __init__(self, polyglot, primary, address: str, name: str, controller) -> None:
        super().__init__(polyglot, primary, address, name)
        self.controller = controller
        self._learn_thread: threading.Thread | None = None
        self._learn_count: int = 0

    def start(self) -> None:
        existing = [k for k in self.controller.learned_codes if k.startswith(self._code_type + "code")]
        self._learn_count = len(existing)
        self._set("GV1", self._learn_count, 56)
        self._set("GV2", 1 if self.controller.hub_client and self.controller.hub_client.connected else 0)
        self._set("ST", 0)

    def learn_code(self, command=None) -> None:
        if self._learn_thread and self._learn_thread.is_alive():
            LOGGER.warning("[%s] Learn already in progress, ignoring command", type(self).__name__)
            return
        self._set("ST", 1)  # Learning
        self._learn_thread = threading.Thread(
            target=self._do_learn, daemon=True, name=f"{self._code_type}-learn"
        )
        self._learn_thread.start()

    def _do_learn(self) -> None:
        tag = type(self).__name__
        try:
            if not self.controller.hub_client:
                raise RuntimeError("Hub client not available")
            LOGGER.info("[%s._do_learn] Starting %s learn (%ds window)", tag, self._code_type.upper(), self._learn_timeout)
            if self._code_type == "rf":
                packet = self.controller.hub_client.learn_rf(timeout_sec=self._learn_timeout)
            else:
                packet = self.controller.hub_client.learn_ir(timeout_sec=self._learn_timeout)

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
            self._set("ST", 2)  # Learned OK
            self._set("GV0", int(time.time()), 151)
            self._set("GV1", self._learn_count, 56)
            LOGGER.info("[%s._do_learn] Learned OK, stored as %s", tag, addr)
        except TimeoutError:
            LOGGER.warning("[%s._do_learn] Learn timed out after %ds", tag, self._learn_timeout)
            self._set("ST", 3)
        except Exception as err:
            LOGGER.error("[%s._do_learn] Failed: %s", tag, err)
            self._set("ST", 3)

    def query(self, command=None) -> None:
        self.start()

    commands = {
        "LEARNCODE": learn_code,
        "QUERY": query,
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
        {"driver": "GV0", "value": 0, "uom": 151},
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
        self._set("GV0", meta.get("created_at", 0), 151)
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

    def query(self, command=None) -> None:
        self.start()

    commands = {
        "TXCODE": send_code,
        "QUERY": query,
    }


class IRCodeNode(_CodeNode):
    """Learned IR code node."""

    id = "blircode"


class RFCodeNode(_CodeNode):
    """Learned RF code node."""

    id = "blrfcode"


class BroadlinkController(BaseNode):
    """Primary node representing one configured Broadlink hub."""

    id = "setup"
    drivers = [
        {"driver": "ST", "value": 0, "uom": 25},
        {"driver": "GV0", "value": 0, "uom": 25},
        {"driver": "GV1", "value": 0, "uom": 25},
        {"driver": "TIME", "value": int(time.time()), "uom": 151},
    ]

    def __init__(self, polyglot, primary, address, name):
        LOGGER.info("[__init__] Constructing BroadlinkController")
        super().__init__(polyglot, primary, address, name)
        # Keep an instance-local driver definition so dynamic sensor drivers can
        # be added/removed without mutating the class-level defaults.
        self.drivers = [dict(driver) for driver in type(self).drivers]
        self.poly = polyglot
        self.config = PluginConfig()
        self.parameters = Custom(self.poly, "customparams")
        self.typed_data = Custom(self.poly, "customtypeddata")
        self.data_store = Custom(self.poly, "customdata")
        self.heartbeat_state = 0
        self.hub_blueprint: HubBlueprint | None = None
        self.hub_client: BroadlinkHubClient | None = None
        self.node_name_cache: dict[str, str] = {}
        self.temp_unit: str = "C"
        self.has_temp_sensor: bool = False
        self.has_humidity_sensor: bool = False
        self.learned_codes: dict[str, dict] = {}
        self._loaded_code_addrs: set[str] = set()
        self.ir_controller: IRControllerNode | None = None
        self.rf_controller: RFControllerNode | None = None
        LOGGER.debug("[__init__] Initialized instance variables")

        LOGGER.debug("[__init__] Subscribing to polyglot events")
        self.poly.subscribe(self.poly.START, self.start, self.address)
        self.poly.subscribe(self.poly.STOP, self.stop)
        self.poly.subscribe(self.poly.POLL, self.poll)
        self.poly.subscribe(self.poly.CUSTOMPARAMS, self.handle_params)
        self.poly.subscribe(self.poly.CUSTOMDATA, self.handle_custom_data)
        self.poly.subscribe(self.poly.LOGLEVEL, self.handle_log_level)
        self.poly.subscribe(self.poly.DISCOVER, self.discover)
        LOGGER.debug("[__init__] Event subscriptions registered")

        LOGGER.info("[__init__] Publishing JSON profile")
        self._publish_profile()
        
        LOGGER.info("[__init__] Signaling polyglot ready")
        self.poly.ready()
        
        LOGGER.info("[__init__] Adding node to polyglot")
        self.poly.addNode(self, conn_status="ST", rename=False)
        
        LOGGER.info("[__init__] BroadlinkController construction complete")

    def start(self):
        LOGGER.info("[start] Received START event")
        self._set("TIME", int(time.time()), 151)
        LOGGER.debug("[start] Set TIME driver")

        # Detect sensor cable before reconcile so profile can include sensor drivers
        self._detect_and_apply_sensors()

        self.reconcile_structure()
        LOGGER.info("[start] Startup reconciliation complete")

    def stop(self):
        # Flush all node names (captures any user renames since last long poll)
        self._sync_all_node_names()
        self._set("ST", 0)
        self._set("GV1", 0)
        self.poly.stop()

    def handle_log_level(self, level):
        if isinstance(level, dict) and "level" in level:
            LOGGER.info("New log level: %s", level["level"])

    def handle_params(self, custom_params):
        LOGGER.info("[handle_params] CUSTOMPARAMS event received")
        self.parameters.load(custom_params)
        self.poly.Notices.clear()
        LOGGER.debug("[handle_params] Received CUSTOMPARAMS keys: %s", sorted((custom_params or {}).keys()))
        LOGGER.debug("[handle_params] CUSTOMPARAMS payload: %s", custom_params)

        try:
            self.config = build_config(custom_params)
        except Exception as err:
            self.poly.Notices["config"] = f"Invalid configuration format: {err}"
            LOGGER.error("[handle_params] Failed to parse custom params: %s", err)
            self._set("ST", 2)
            self._set("GV1", 0)
            self._set("GV0", 0, 56)
            return

        if self.config.has_hub:
            LOGGER.info("[handle_params] *** HUB_IP RESOLVED FROM CUSTOMPARAMS: %s ***", self.config.hub_ip)
            if self.config.ignored_hub_ips:
                LOGGER.info("[handle_params] Additional HUB_IP values ignored in single-hub mode: %s", self.config.ignored_hub_ips)
        else:
            LOGGER.warning("[handle_params] No HUB_IP resolved from custom params payload.")

        # Parse TEMP_UNIT: republish profile if unit changed while sensor is present
        prev_temp_unit = self.temp_unit
        self.temp_unit = _parse_temp_unit(custom_params)
        if self.temp_unit != prev_temp_unit:
            LOGGER.info("[handle_params] TEMP_UNIT changed from %s to %s", prev_temp_unit, self.temp_unit)
            self._sync_setup_driver_definitions()

        if not self.config.has_hub:
            self.poly.Notices["required"] = "Set HUB_IP to the IP address for this Broadlink hub instance."
        elif self.config.ignored_hub_ips:
            self.poly.Notices["config_scope"] = "Only the first configured hub IP is used. Run one PG3 instance per hub."

        # Detect sensors (may republish profile with sensor drivers)
        if self.config.has_hub:
            self._detect_and_apply_sensors()
        # Republish if only temp_unit changed (sensor state unchanged, detect_and_apply skipped republish)
        if self.temp_unit != prev_temp_unit and self.has_temp_sensor:
            self._publish_profile()

        self.reconcile_structure()

    def handle_custom_data(self, custom_data):
        self.data_store.load(custom_data or {})
        self.node_name_cache = self._safe_name_map(self.data_store.get("node_names", {}))
        self.learned_codes = self._safe_code_map(self.data_store.get("learned_codes", {}))
        # Restore last-known sensor state so __init__'s profile publish is accurate on restart
        sensor_state = self.data_store.get("sensor_state") or {}
        self.has_temp_sensor = bool(sensor_state.get("has_temp", False))
        self.has_humidity_sensor = bool(sensor_state.get("has_humidity", False))
        self._sync_setup_driver_definitions()
        self._sync_node_names_from_db()

    def poll(self, poll_type):
        self._set("TIME", int(time.time()), 151)

        if poll_type == "shortPoll":
            self.heartbeat_state = 1 - self.heartbeat_state
            if self.heartbeat_state:
                self.reportCmd("DON", 2)
            else:
                self.reportCmd("DOF", 2)
            if self.has_temp_sensor or self.has_humidity_sensor:
                self._refresh_sensor_readings()
            return

        self._refresh_hub_connection()
        self._sync_node_names_from_db()
        self.reconcile_structure(update_time=False)

    def discover(self, *_):
        self.reconcile_structure()

    def reconcile_structure(self, update_time: bool = True):
        LOGGER.debug("[reconcile_structure] Starting structure reconciliation")
        self.hub_blueprint = self._build_hub_blueprint()
        LOGGER.debug("[reconcile_structure] Built hub blueprint: %s", self.hub_blueprint)
        
        self._sync_node_names_from_db()
        LOGGER.debug("[reconcile_structure] Synced node names from database")

        if self.hub_blueprint is None:
            LOGGER.info("[reconcile_structure] Hub blueprint is None - no HUB_IP configured")
            self._set("ST", 0)
            self._set("GV0", 0, 25)
            self._set("GV1", 0)
            self.poly.Notices["stage"] = "Single-hub mode active: configure HUB_IP for this node server instance."
            self.poly.Notices.delete("hub_errors")
        else:
            LOGGER.info("[reconcile_structure] Hub blueprint resolved: ip=%s, connected=%s, model=%s", 
                       self.hub_blueprint.ip_address, self.hub_blueprint.connected, self.hub_blueprint.model_name)
            
            status_value = 1 if self.hub_blueprint.connected else 2 if self.hub_blueprint.last_error else 0
            self._set("ST", status_value)
            LOGGER.debug("[reconcile_structure] Set ST driver to %d", status_value)
            
            self._set(
                "GV0",
                _model_index(self.hub_blueprint.model_name),
                25,
            )
            self._set("GV1", 1 if self.hub_blueprint.connected else 0)
            LOGGER.debug("[reconcile_structure] Set GV0 and GV1 drivers")

            self.node_name_cache[self.address] = self.hub_blueprint.display_name
            self._persist_node_name_cache()
            LOGGER.debug("[reconcile_structure] Updated node name cache")

            if self.hub_blueprint.connected:
                LOGGER.info("[reconcile_structure] Hub is connected and ready")
                self.poly.Notices.delete("stage")
                self.poly.Notices.delete("hub_errors")
                self._ensure_controller_nodes()
                self._load_learned_codes()
            else:
                LOGGER.warning("[reconcile_structure] Hub not connected, will retry on next poll")
                self.poly.Notices["stage"] = (
                    "Single-hub mode active: this PG3 instance is reconciling one Broadlink hub. "
                    "IR/RF nodes remain deferred."
                )
                if self.hub_blueprint.last_error:
                    LOGGER.error("[reconcile_structure] Hub error: %s", self.hub_blueprint.last_error)
                    self.poly.Notices["hub_errors"] = (
                        f"{self.hub_blueprint.ip_address}: {self.hub_blueprint.last_error}"
                    )

        if update_time:
            self._set("TIME", int(time.time()), 151)

    def _build_hub_blueprint(self) -> HubBlueprint | None:
        LOGGER.debug("[_build_hub_blueprint] Building hub blueprint, has_hub=%s", self.config.has_hub)
        if not self.config.has_hub:
            LOGGER.debug("[_build_hub_blueprint] No HUB_IP configured")
            return None

        LOGGER.info("[_build_hub_blueprint] Creating/reusing hub client for %s", self.config.hub_ip)
        client = self._get_or_create_hub_client(self.config.hub_ip)
        
        LOGGER.debug("[_build_hub_blueprint] Identifying hub")
        hub_info, error_text, connected = self._identify_hub(client)
        LOGGER.debug("[_build_hub_blueprint] Hub identification: connected=%s, error=%s", connected, error_text)
        
        display_name = self._resolve_node_name(self.address, self._default_hub_name(hub_info))
        LOGGER.debug("[_build_hub_blueprint] Resolved display name: %s", display_name)
        
        blueprint = HubBlueprint(
            ip_address=self.config.hub_ip,
            display_name=display_name,
            mac_address=hub_info.mac_address if hub_info else "",
            device_type=hub_info.device_type if hub_info else "unknown",
            model_name=hub_info.model_name if hub_info else "unknown",
            connected=connected,
            last_error=error_text,
        )
        LOGGER.info("[_build_hub_blueprint] Hub blueprint built: ip=%s, connected=%s, model=%s", 
                   blueprint.ip_address, blueprint.connected, blueprint.model_name)
        return blueprint

    def _refresh_hub_connection(self):
        if self.hub_client is not None:
            self.hub_client.refresh()

    def _get_or_create_hub_client(self, ip_address: str) -> BroadlinkHubClient:
        if self.hub_client is None or self.hub_client.hub_ip != ip_address:
            self.hub_client = BroadlinkHubClient(hub_ip=ip_address)
        return self.hub_client

    def _identify_hub(self, client: BroadlinkHubClient) -> tuple[BroadlinkHubInfo | None, str, bool]:
        try:
            LOGGER.debug("[_identify_hub] Attempting ensure_connected")
            hub_info = client.ensure_connected()
            LOGGER.info("[_identify_hub] Hub identified successfully: %s", hub_info.model_name if hub_info else "unknown")
            return hub_info, "", True
        except Exception as err:
            LOGGER.warning("[_identify_hub] Connection failed: %s", err)
            hub_info = client.hub_info
            return hub_info, str(err), False

    def _default_hub_name(self, hub_info: BroadlinkHubInfo | None) -> str:
        if hub_info is None:
            return self.name or "Broadlink Hub"

        model_name = hub_info.model_name or "Broadlink Hub"
        mac_suffix = hub_info.mac_address[-6:] if hub_info.mac_address else ""
        if mac_suffix:
            return f"{model_name} {mac_suffix.upper()}"
        return model_name

    def _resolve_node_name(self, address: str, default_name: str) -> str:
        if address:
            db_name = self.poly.getNodeNameFromDb(address)
            if db_name:
                self.node_name_cache[address] = db_name
                return db_name
            if address in self.node_name_cache:
                return self.node_name_cache[address]
        return default_name

    def _publish_profile(self):
        LOGGER.info("[_publish_profile] Starting profile publish")
        update_json_profile = getattr(self.poly, "updateJsonProfile", None)
        if not callable(update_json_profile):
            LOGGER.error("[_publish_profile] updateJsonProfile is unavailable")
            self.poly.Notices["profile"] = "Dynamic profile publish failed: updateJsonProfile() is unavailable."
            return
        LOGGER.debug("[_publish_profile] updateJsonProfile method available")

        profile = _build_profile_definition(self.has_temp_sensor, self.has_humidity_sensor, self.temp_unit)

        current_profile_getter = getattr(self.poly, "getJsonProfile", None)
        if callable(current_profile_getter):
            try:
                LOGGER.debug("[_publish_profile] Attempting to retrieve current profile from IoX")
                current_profile = current_profile_getter({"waitResponse": True})
                LOGGER.debug("[_publish_profile] Current JSON profile from IoX: %s", json.dumps(current_profile, sort_keys=True))
                if self._profiles_match(current_profile, profile):
                    LOGGER.info("[_publish_profile] JSON profile already up to date, skipping publish")
                    return
                LOGGER.info("[_publish_profile] Profile mismatch detected, will republish")
            except TypeError:
                LOGGER.debug("[_publish_profile] getJsonProfile does not support waitResponse, trying without")
                current_profile = current_profile_getter()
                LOGGER.debug("[_publish_profile] Current JSON profile from IoX: %s", json.dumps(current_profile, sort_keys=True))
                if self._profiles_match(current_profile, profile):
                    LOGGER.info("[_publish_profile] JSON profile already up to date, skipping publish")
                    return
                LOGGER.info("[_publish_profile] Profile mismatch detected, will republish")
            except Exception as err:
                LOGGER.warning("[_publish_profile] Unable to read existing JSON profile: %s", err)

        try:
            LOGGER.debug("[_publish_profile] Publishing profile with waitResponse=True")
            update_json_profile(profile, {"waitResponse": True})
            LOGGER.info("[_publish_profile] Dynamic JSON profile published successfully")
            self.poly.Notices.delete("profile")
        except TypeError:
            LOGGER.debug("[_publish_profile] updateJsonProfile does not support options, publishing without")
            update_json_profile(profile)
            LOGGER.info("[_publish_profile] Dynamic JSON profile published successfully")
            self.poly.Notices.delete("profile")
        except Exception as err:
            LOGGER.error("[_publish_profile] Dynamic profile publish failed: %s", err)
            self.poly.Notices["profile"] = f"Dynamic profile publish failed: {err}"

    def _profiles_match(self, current_profile, expected_profile) -> bool:
        if not isinstance(current_profile, dict):
            return False
        if not isinstance(expected_profile, dict):
            return False

        for key in ("editors", "nodedefs", "linkdefs"):
            if current_profile.get(key, []) != expected_profile.get(key, []):
                return False
        return True

    def _sync_node_names_from_db(self):
        db_name = self.poly.getNodeNameFromDb(self.address)
        resolved_name = db_name or self.node_name_cache.get(self.address)
        if resolved_name:
            self.name = resolved_name

        self.node_name_cache[self.address] = self.name
        self._persist_node_name_cache()

    def _persist_node_name_cache(self):
        stored_node_names = self._safe_name_map(self.data_store.get("node_names", {}))
        desired_node_names = dict(self.node_name_cache)
        if stored_node_names != desired_node_names:
            self.data_store["node_names"] = desired_node_names

    def _safe_name_map(self, candidate) -> dict[str, str]:
        if not isinstance(candidate, dict):
            return {}

        parsed: dict[str, str] = {}
        for key, value in candidate.items():
            key_text = str(key).strip()
            value_text = str(value).strip()
            if not key_text or not value_text:
                continue
            parsed[key_text] = value_text
        return parsed

    def _detect_and_apply_sensors(self) -> None:
        """Connect to hub, detect sensor cable, and republish profile if state changed."""
        if not self.config.has_hub:
            return
        client = self._get_or_create_hub_client(self.config.hub_ip)
        try:
            sensor_data = client.check_sensors()
            new_has_temp = sensor_data.has_temperature
            new_has_humidity = sensor_data.has_humidity
            if new_has_temp != self.has_temp_sensor or new_has_humidity != self.has_humidity_sensor:
                LOGGER.info(
                    "[_detect_and_apply_sensors] Sensor state changed: temp=%s, humidity=%s",
                    new_has_temp, new_has_humidity,
                )
                self.has_temp_sensor = new_has_temp
                self.has_humidity_sensor = new_has_humidity
                self._sync_setup_driver_definitions()
                # Persist sensor state so next startup's initial profile publish is correct
                self.data_store["sensor_state"] = {"has_temp": new_has_temp, "has_humidity": new_has_humidity}
                self._publish_profile()
        except Exception as err:
            LOGGER.debug(
                "[_detect_and_apply_sensors] Sensor check skipped (no cable or unsupported): %s", err
            )

    def _refresh_sensor_readings(self) -> None:
        """Query hub for current temperature/humidity and update setup node drivers."""
        if not self.hub_client:
            return
        try:
            sensor_data = self.hub_client.check_sensors()
            if sensor_data.has_temperature:
                temp_c = sensor_data.temperature_c
                display_val = round((temp_c * 9 / 5) + 32, 1) if self.temp_unit == "F" else round(temp_c, 1)
                self._set("GV2", display_val, 4 if self.temp_unit == "F" else 17)
            if sensor_data.has_humidity:
                self._set("GV3", round(sensor_data.humidity, 1), 22)
        except Exception as err:
            LOGGER.debug("[_refresh_sensor_readings] Sensor query failed: %s", err)

    def _sync_setup_driver_definitions(self) -> None:
        """Align setup-node drivers with detected sensor capabilities."""
        base_drivers = [
            {"driver": "ST", "value": 0, "uom": 25},
            {"driver": "GV0", "value": 0, "uom": 25},
            {"driver": "GV1", "value": 0, "uom": 25},
            {"driver": "TIME", "value": int(time.time()), "uom": 151},
        ]
        if self.has_temp_sensor:
            base_drivers.append({"driver": "GV2", "value": 0, "uom": 4 if self.temp_unit == "F" else 17})
        if self.has_humidity_sensor:
            base_drivers.append({"driver": "GV3", "value": 0, "uom": 22})
        self.drivers = base_drivers

    def _ensure_controller_nodes(self) -> None:
        """Create IR and RF controller subnodes if they do not already exist."""
        if self.ir_controller is None:
            ir_name = self._resolve_node_name("irctrl", "IR Controller")
            self.ir_controller = IRControllerNode(self.poly, self.address, "irctrl", ir_name, self)
            self.poly.addNode(self.ir_controller)
            LOGGER.info("[_ensure_controller_nodes] Added IRControllerNode")
        if self.rf_controller is None:
            rf_name = self._resolve_node_name("rfctrl", "RF Controller")
            self.rf_controller = RFControllerNode(self.poly, self.address, "rfctrl", rf_name, self)
            self.poly.addNode(self.rf_controller)
            LOGGER.info("[_ensure_controller_nodes] Added RFControllerNode")

    def _load_learned_codes(self) -> None:
        """Recreate code subnodes from persisted metadata (idempotent)."""
        for addr, meta in self.learned_codes.items():
            if addr in self._loaded_code_addrs:
                continue
            code_type = meta.get("controller_type", "ir")
            ctrl_addr = meta.get("controller_addr", "irctrl")
            name = meta.get("name") or f"{code_type.upper()} Code"
            if code_type == "rf":
                node: _CodeNode = RFCodeNode(self.poly, ctrl_addr, addr, name, self)
            else:
                node = IRCodeNode(self.poly, ctrl_addr, addr, name, self)
            node._code_meta = dict(meta)
            self.poly.addNode(node)
            self._loaded_code_addrs.add(addr)
            LOGGER.info("[_load_learned_codes] Restored %s code node: %s", code_type.upper(), addr)

    def _persist_learned_code(self, addr: str, metadata: dict) -> None:
        """Persist a single learned code's metadata to customdata (diff-safe)."""
        updated = dict(self.learned_codes)
        updated[addr] = dict(metadata)
        self.learned_codes = updated
        self._loaded_code_addrs.add(addr)
        stored = self.data_store.get("learned_codes") or {}
        if stored != updated:
            self.data_store["learned_codes"] = updated

    def _next_code_address(self, code_type: str) -> str:
        """Return the next available unique address for a learned code."""
        prefix = f"{code_type}code"
        existing = [k for k in self.learned_codes if k.startswith(prefix)]
        return f"{prefix}{len(existing) + 1:03d}"

    def _safe_code_map(self, candidate) -> dict[str, dict]:
        """Validate and return the learned_codes structure from customdata."""
        if not isinstance(candidate, dict):
            return {}
        return {str(k).strip(): v for k, v in candidate.items() if isinstance(k, str) and isinstance(v, dict)}

    def _sync_all_node_names(self) -> None:
        """Flush all managed node names from PG3 DB to customdata (called on stop)."""
        # Setup node
        self._sync_node_names_from_db()
        # IR/RF controller nodes
        for addr in ("irctrl", "rfctrl"):
            db_name = self.poly.getNodeNameFromDb(addr)
            if db_name:
                self.node_name_cache[addr] = db_name
        # Code nodes — also update name in learned_codes metadata
        codes_changed = False
        updated_codes = dict(self.learned_codes)
        for addr in list(self.learned_codes.keys()):
            db_name = self.poly.getNodeNameFromDb(addr)
            if db_name:
                self.node_name_cache[addr] = db_name
                if updated_codes[addr].get("name") != db_name:
                    updated_codes[addr] = dict(updated_codes[addr])
                    updated_codes[addr]["name"] = db_name
                    codes_changed = True
        if codes_changed:
            self.learned_codes = updated_codes
            stored = self.data_store.get("learned_codes") or {}
            if stored != updated_codes:
                self.data_store["learned_codes"] = updated_codes
        self._persist_node_name_cache()

    def force_update(self, command=None):
        self.reconcile_structure()

    commands = {
        "UPDATE": force_update,
        "QUERY": force_update,
    }
