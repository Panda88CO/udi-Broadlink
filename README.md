# udi-broadlink

Broadlink node server rewrite for UDI Polyglot v3 (PG3/PG3x), implemented in Python using:
- `udi_interface`
- `python-broadlink`

## Current Status

The repository is now in the hub-integration rewrite phase.

Implemented in this pass:
- Controller startup and PG3 scaffolding
- Single-hub configuration parsing from PG3 custom parameters
- Structure and persistence groundwork for later rename replay
- Architecture separation for primary hub, capability, and code layers
- Hub initialization from the configured IP using `broadlink.hello(ip)` and `auth()`
- Cached hub identity and status reconciliation during startup and polling
- Minimal in-code JSON profile publication for `setup`

Intentionally deferred:
- IR and RF operational nodes
- Code send and learn flows

## Profile Direction

The rewrite now publishes a minimal JSON profile from code for the primary node.
That currently covers:
- `setup`

If the installed `udi_interface` does not support JSON profile publication, the code falls back to the legacy `updateProfile()` path.

## Architecture Direction

Planned node layout in ISY/IoX:
- One `setup` primary node per configured Broadlink hub instance
- One IR operational node below that hub
- One RF operational node below that hub
- Code subnodes below the relevant IR or RF node

Run one PG3 node server instance per Broadlink hub. The design is being staged so the per-hub structure, naming, and persistence are stable before IR/RF runtime logic is added.

## Configuration

Configure runtime values through the PG3 configuration UI.
The current rewrite does not rely on `server.json` to provide runtime configuration defaults.

Current required parameter:
- `HUB_IP`

The preferred configuration surface is now a code-defined typed parameter in PG3.
The parser still accepts plain custom parameter input as a fallback during the rewrite.
Older list-style inputs such as `HUB_IPS` are still accepted for migration, but only the first IP is used.

Supported formats:

### Single IP
```text
192.168.1.120
```

### Legacy list input
```text
192.168.1.120, 192.168.1.121
```

Only the first IP is used from legacy list input.

The current design assumes each Broadlink device is already provisioned on the local Wi-Fi network.

## Staged Plan

1. Build the overall PG3 structure and persistence model.
2. Add single-hub integration using the configured IP and stable identity data.
3. Add IR and RF operational nodes and their code subnodes.

## Install

### Local test
```bash
pip install -r requirements.txt
python udibroadlink.py
```

### PG3 install script
`install.sh` installs dependencies from `requirements.txt`.
