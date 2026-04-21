# Broadlink Node Server Configuration

## Current Stage

This rewrite is currently in the hub-integration pass.

What is implemented now:
- Controller startup and PG3x scaffolding
- Single-hub configuration parsing
- Structure and persistence groundwork
- Rename replay groundwork using PG3 database names as the first priority
- Hub initialization from the configured IP address
- Cached hub identity plus automatic reconnect and status reconciliation on startup and long poll
- Minimal in-code JSON profile publication for `setup`

What is intentionally deferred:
- IR and RF operational nodes
- Code send and learn flows

## Profile Notes

The node server now publishes a minimal JSON profile from code for the currently implemented primary node.
If the installed `udi_interface` version does not support JSON profile publication, the code falls back to the legacy profile update path.

## Required Parameters

- `HUB_IP`: IP address of the Broadlink hub managed by this PG3 instance

The node server assumes each Broadlink device is already provisioned on the local Wi-Fi network.
AP setup is not part of the normal workflow for this implementation stage.
The current implementation does not rely on `server.json` to seed runtime configuration values.
Enter configuration through the PG3 configuration UI.

The preferred UI path is now a code-defined typed parameter published by the node server.
Plain custom parameter text is still accepted as a fallback while the rewrite is in progress.
Older list-style inputs such as `HUB_IPS` are still accepted for migration, but only the first IP is used.

Supported `HUB_IP` formats:

### Single IP
```text
192.168.1.120
```

### Legacy list input
```text
192.168.1.120, 192.168.1.121
```

Only the first IP is used from legacy list input.

## Operational Notes

- `shortPoll` provides heartbeat updates on the controller.
- `longPoll` refreshes hub connectivity, reconnects if needed, and syncs persisted node-name information from PG3.
- Run one PG3 node server instance per Broadlink hub.
- The next implementation pass will add IR/RF operational nodes and code handling on top of the current single-hub layer.
