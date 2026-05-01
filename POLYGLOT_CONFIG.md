# Broadlink Node Server Configuration



## Required Parameters

- `HUB_IP`: IP address of the Broadlink hub managed by this PG3 instance

The node server assumes each Broadlink device is already provisioned on the local Wi-Fi network.
AP setup is not part of the normal workflow for this implementation stage.

You can serach the web on how to do this, but the simplest is to use the broadlink app to connect to the local network - once hub is registered Kill the app.  If you complete with teh APP the HUB get locked and cannot be controlled by this node.  

Supported `HUB_IP` formats:

### Single IP
```text
192.168.1.120
```

### Legacy list input
```text
192.168.1.120, 192.168.1.121
```

## Operational Notes

- `shortPoll` provides heartbeat updates on the HUB and refreshes the sensor if present.
- `longPoll` refreshes hub connectivity, reconnects if needed, and syncs persisted node-name information with PG3.

