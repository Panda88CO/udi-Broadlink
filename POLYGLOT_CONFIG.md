# Broadlink Node Server Configuration

## Required Parameters

- `HUB_IP`: IP address (or list of IP addresses) of the Broadlink hub(s) managed by this PG3 instance.

The node server requires each Broadlink device to be already provisioned on the local Wi-Fi network.
Initial Wi-Fi AP setup is not performed by this plugin.

To provision a new hub on Wi-Fi, use the Broadlink mobile app only up to the step where the hub joins your local Wi-Fi network, then close/quit the app before adding the device to a cloud room/account. Completing full cloud registration in the Broadlink app locks the hub, preventing local control until unlocked in the app's device properties.

Supported `HUB_IP` formats:

### Single IP
```text
192.168.1.120
```

### Multiple IPs (space, comma, semicolon, or newline separated)
```text
192.168.1.120, 192.168.1.121
```

## Optional Parameters

- `TEMP_UNIT`: Temperature display unit for hubs with an external temperature/humidity sensor (`C` for Celsius by default, or `F` for Fahrenheit).

## Operational Notes

- `shortPoll` sends heartbeat (`DON` / `DOF`) updates on the `BLSETUP` node and refreshes sensor readings on each hub's `BLSENSOR` node (if present).
- `longPoll` checks hub connectivity, reconnects if needed, and syncs persisted node-name information with PG3 `customdata`.

