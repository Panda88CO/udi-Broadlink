"""Node classes for the Broadlink PG3 plugin single-hub rewrite."""

from __future__ import annotations

from dataclasses import dataclass
import json
import time

import udi_interface

from broadlink_client import BroadlinkHubClient, BroadlinkHubInfo
from config_parser import PluginConfig, build_config

LOGGER = udi_interface.LOGGER
Custom = udi_interface.Custom
VERSION = "0.2.0"

PROFILE_DEFINITION = {
    "editors": [
        {
            "id": "status_index",
            "ranges": [
                {
                    "uom": "25",
                    "subset": "0-2",
                    "names": {
                        "0": "Not Configured",
                        "1": "Online",
                        "2": "Error",
                    },
                }
            ],
        },
        {
            "id": "binary_index",
            "ranges": [
                {
                    "uom": "25",
                    "subset": "0-1",
                    "names": {
                        "0": "No",
                        "1": "Yes",
                    },
                }
            ],
        },
        {
            "id": "raw_value",
            "ranges": [
                {
                    "uom": "56",
                    "min": 0,
                    "max": 65535,
                    "prec": 0,
                }
            ],
        },
        {
            "id": "timestamp",
            "ranges": [
                {
                    "uom": "151",
                    "min": 0,
                    "max": 4294967295,
                    "prec": 0,
                }
            ],
        },
    ],
    "nodedefs": [
        {
            "id": "setup",
            "icon": "GenericCtl",
            "properties": [
                {
                    "id": "ST",
                    "name": "Status",
                    "editor": "status_index",
                },
                {
                    "id": "GV0",
                    "name": "Device Type",
                    "editor": "raw_value",
                },
                {
                    "id": "GV1",
                    "name": "Connected",
                    "editor": "binary_index",
                },
                {
                    "id": "TIME",
                    "name": "Last Update",
                    "editor": "timestamp",
                },
            ],
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
            "links": {
                "ctl": [],
                "rsp": [],
            },
        },
    ],
    "linkdefs": [],
}


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


class BroadlinkCapabilityNode(BaseNode):
    """Placeholder capability node for a later implementation pass."""

    id = "blcap"
    drivers = [
        {"driver": "ST", "value": 0, "uom": 25},
        {"driver": "GV0", "value": 0, "uom": 56},
        {"driver": "GV30", "value": 0, "uom": 25},
        {"driver": "TIME", "value": int(time.time()), "uom": 151},
    ]

    def __init__(self, polyglot, primary, address: str, name: str, capability: str):
        super().__init__(polyglot, primary, address, name)
        self.capability = capability
        self.id = f"bl{capability}"

    def start(self):
        self.query()

    def query(self, command=None):
        self._set("TIME", int(time.time()), 151)

    commands = {
        "QUERY": query,
        "UPDATE": query,
    }


class BroadlinkCodeNode(BaseNode):
    """Placeholder code node for a later implementation pass."""

    id = "blcode"
    drivers = [
        {"driver": "ST", "value": 0, "uom": 25},
        {"driver": "GV30", "value": 0, "uom": 25},
        {"driver": "TIME", "value": int(time.time()), "uom": 151},
    ]

    def start(self):
        self.query()

    def query(self, command=None):
        self._set("TIME", int(time.time()), 151)

    commands = {
        "QUERY": query,
    }


class BroadlinkController(BaseNode):
    """Primary node representing one configured Broadlink hub."""

    id = "setup"
    drivers = [
        {"driver": "ST", "value": 0, "uom": 25},
        {"driver": "GV0", "value": 0, "uom": 56},
        {"driver": "GV1", "value": 0, "uom": 25},
        {"driver": "TIME", "value": int(time.time()), "uom": 151},
    ]

    def __init__(self, polyglot, primary, address, name):
        LOGGER.info("[__init__] Constructing BroadlinkController")
        super().__init__(polyglot, primary, address, name)
        self.poly = polyglot
        self.config = PluginConfig()
        self.parameters = Custom(self.poly, "customparams")
        self.typed_data = Custom(self.poly, "customtypeddata")
        self.data_store = Custom(self.poly, "customdata")
        self.heartbeat_state = 0
        self.hub_blueprint: HubBlueprint | None = None
        self.hub_client: BroadlinkHubClient | None = None
        self.node_name_cache: dict[str, str] = {}
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
        
        self.reconcile_structure()
        LOGGER.info("[start] Startup reconciliation complete")

    def stop(self):
        self._sync_node_names_from_db()
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

        if not self.config.has_hub:
            self.poly.Notices["required"] = "Set HUB_IP to the IP address for this Broadlink hub instance."
        elif self.config.ignored_hub_ips:
            self.poly.Notices["config_scope"] = "Only the first configured hub IP is used. Run one PG3 instance per hub."

        self.reconcile_structure()

    def handle_custom_data(self, custom_data):
        self.data_store.load(custom_data or {})
        self.node_name_cache = self._safe_name_map(self.data_store.get("node_names", {}))
        self._sync_node_names_from_db()

    def poll(self, poll_type):
        self._set("TIME", int(time.time()), 151)

        if poll_type == "shortPoll":
            self.heartbeat_state = 1 - self.heartbeat_state
            if self.heartbeat_state:
                self.reportCmd("DON", 2)
            else:
                self.reportCmd("DOF", 2)
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
            self._set("GV0", 0, 56)
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
                int(self.hub_blueprint.device_type[2:], 16)
                if self.hub_blueprint.device_type.startswith("0x")
                else 0,
                56,
            )
            self._set("GV1", 1 if self.hub_blueprint.connected else 0)
            LOGGER.debug("[reconcile_structure] Set GV0 and GV1 drivers")

            self.node_name_cache[self.address] = self.hub_blueprint.display_name
            self._persist_node_name_cache()
            LOGGER.debug("[reconcile_structure] Updated node name cache")

            if self.hub_blueprint.connected:
                LOGGER.info("[reconcile_structure] Hub is connected and ready")
                self.poly.Notices["stage"] = (
                    "Single-hub mode active: this PG3 instance is managing one Broadlink hub. "
                    "IR/RF nodes will be added next."
                )
                self.poly.Notices.delete("hub_errors")
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

        current_profile_getter = getattr(self.poly, "getJsonProfile", None)
        if callable(current_profile_getter):
            try:
                LOGGER.debug("[_publish_profile] Attempting to retrieve current profile from IoX")
                current_profile = current_profile_getter({"waitResponse": True})
                LOGGER.debug("[_publish_profile] Current JSON profile from IoX: %s", json.dumps(current_profile, sort_keys=True))
                if self._profiles_match(current_profile, PROFILE_DEFINITION):
                    LOGGER.info("[_publish_profile] JSON profile already up to date, skipping publish")
                    return
                LOGGER.info("[_publish_profile] Profile mismatch detected, will republish")
            except TypeError:
                LOGGER.debug("[_publish_profile] getJsonProfile does not support waitResponse, trying without")
                current_profile = current_profile_getter()
                LOGGER.debug("[_publish_profile] Current JSON profile from IoX: %s", json.dumps(current_profile, sort_keys=True))
                if self._profiles_match(current_profile, PROFILE_DEFINITION):
                    LOGGER.info("[_publish_profile] JSON profile already up to date, skipping publish")
                    return
                LOGGER.info("[_publish_profile] Profile mismatch detected, will republish")
            except Exception as err:
                LOGGER.warning("[_publish_profile] Unable to read existing JSON profile: %s", err)

        try:
            LOGGER.debug("[_publish_profile] Publishing profile with waitResponse=True")
            update_json_profile(PROFILE_DEFINITION, {"waitResponse": True})
            LOGGER.info("[_publish_profile] Dynamic JSON profile published successfully")
            self.poly.Notices.delete("profile")
        except TypeError:
            LOGGER.debug("[_publish_profile] updateJsonProfile does not support options, publishing without")
            update_json_profile(PROFILE_DEFINITION)
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

    def force_update(self, command=None):
        self.reconcile_structure()

    commands = {
        "UPDATE": force_update,
        "QUERY": force_update,
    }
