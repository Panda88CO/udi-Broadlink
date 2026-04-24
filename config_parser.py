"""Configuration parsing helpers for the Broadlink PG3 node server."""

from __future__ import annotations

from dataclasses import dataclass, field
import json


@dataclass(slots=True)
class PluginConfig:
    """Runtime configuration loaded from PG3 custom parameters."""

    hub_ips: list[str] = field(default_factory=list)

    @property
    def has_hub(self) -> bool:
        return bool(self.hub_ips)

    @property
    def hub_ip(self) -> str:
        """First configured hub IP (backwards-compat accessor)."""
        return self.hub_ips[0] if self.hub_ips else ""

    @property
    def ignored_hub_ips(self) -> list[str]:
        """Additional hub IPs beyond the first (backwards-compat accessor)."""
        return self.hub_ips[1:]


def parse_ip_list(raw_value) -> list[str]:
    """Parse hub IPs from JSON list, CSV, or newline-delimited text."""
    if not raw_value:
        return []

    if isinstance(raw_value, list):
        candidates = raw_value
    elif isinstance(raw_value, tuple):
        candidates = list(raw_value)
    else:
        text = str(raw_value).strip()
        if not text:
            return []

        if text.startswith("["):
            data = json.loads(text)
            if not isinstance(data, list):
                raise ValueError("HUB_IPS JSON must be a list")
            candidates = data
        else:
            candidates = []
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                candidates.extend(part.strip() for part in stripped.split(","))

    parsed: list[str] = []
    seen: set[str] = set()

    for candidate in candidates:
        value = str(candidate).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        parsed.append(value)

    return parsed


def _extract_typed_value(raw_value):
    """Extract actual value from common PG3 typed-parameter payload shapes."""
    if isinstance(raw_value, dict):
        for key in ("value", "val", "text", "raw", "default"):
            if key in raw_value:
                return raw_value[key]
    return raw_value


def _flatten_param_map(params: dict) -> dict:
    """Normalize incoming param payload into a flat key/value dictionary."""
    normalized = dict(params)

    for container_key in ("customparams", "customtypeddata", "typed_data", "params"):
        candidate = params.get(container_key)
        if isinstance(candidate, dict):
            for key, value in candidate.items():
                normalized.setdefault(key, value)

    for list_key in ("customtypedparams", "typedparams", "typed_parameters"):
        candidate = params.get(list_key)
        if isinstance(candidate, list):
            for item in candidate:
                if not isinstance(item, dict):
                    continue
                name = item.get("name") or item.get("id") or item.get("key")
                if not name:
                    continue
                normalized.setdefault(str(name), item.get("value", item.get("val", "")))

    return normalized


def _first_present(params: dict, keys: tuple[str, ...]):
    for key in keys:
        if key in params:
            return params[key]
    return ""


def build_config(custom_params: dict | None) -> PluginConfig:
    """Build PluginConfig from raw PG3 custom params."""
    params = _flatten_param_map(custom_params or {})

    raw_hubs = _first_present(
        params,
        (
            "hub_ip",
            "hub_ips",
            "HUB_IP",
            "HUB_IPS",
            "Hub_IP",
            "Hub_IPs",
            "hubIp",
            "hubIps",
        ),
    )
    raw_hubs = _extract_typed_value(raw_hubs)

    hub_ips = parse_ip_list(raw_hubs)
    return PluginConfig(hub_ips=hub_ips)
