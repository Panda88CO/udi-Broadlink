"""Configuration parsing helpers for the Broadlink PG3 node server."""

from __future__ import annotations

from dataclasses import dataclass, field
import json


@dataclass(slots=True)
class PluginConfig:
    """Runtime configuration loaded from PG3 custom parameters."""

    hub_ip: str = ""
    ignored_hub_ips: list[str] = field(default_factory=list)

    @property
    def has_hub(self) -> bool:
        return bool(self.hub_ip)


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


def build_config(custom_params: dict | None) -> PluginConfig:
    """Build PluginConfig from raw PG3 custom params."""
    params = custom_params or {}
    raw_hubs = params.get("hub_ip", params.get("hub_ips", params.get("HUB_IP", params.get("HUB_IPS", ""))))
    hub_ips = parse_ip_list(raw_hubs)
    return PluginConfig(
        hub_ip=hub_ips[0] if hub_ips else "",
        ignored_hub_ips=hub_ips[1:],
    )
