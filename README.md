# udi-broadlink

Broadlink node server for UDI Polyglot v3 (PG3/PG3x), implemented in Python using:
- `udi_interface`
- `python-broadlink`

## Overview

A single PG3 node server instance can manage one or more Broadlink hubs by providing a single IP address or a list of IP addresses in `HUB_IP`.

## Node Organization

Each configured Broadlink hub creates a `BLHUB` node. If a temperature/humidity sensor cable is present, its readings are shown in a child `BLSENSOR` node.
Each hub also creates two separate controller nodes: an IR Controller (`BLIRCTL`) and an RF Controller (`BLRFCTL`), with the hub's IP identifier appended. Each learned IR or RF code becomes a child node (`BLIRCODE` or `BLRFCODE`) under the respective controller node.


## Learning RF Codes

Learning an RF code is a two-step task. First, the RF controller searches for the correct frequency — during this time you need to press and hold (or repeatedly press) the remote button being learned while the hub's LED remains on. Once the LED turns off, the Admin Console status updates to `Check Packet Data`, prompting you to press the button once more to capture the actual RF packet. If the code has already been learned, it is flagged as `Duplicate` and will not create a duplicate node (you can delete learned codes from the PG3 interface or ungroup the controller, delete the node, and regroup).
Note: you can rename code nodes in the Admin Console once learned — custom names are persisted across restarts.


### Broadlink Setup (`BLSETUP`)

Coordinator primary node. Created automatically on startup.

| Driver | Name | Description |
|--------|------|-------------|
| `ST` | Status | `No Hubs Configured` / `All Online` / `Partial` / `None Online` |
| `GV0` | Hub Count | Number of configured hubs |
| `TIME` | Last Update | Timestamp of the most recent poll |

Commands accepted: `UPDATE` (force immediate refresh).
Heartbeat events `DON` / `DOF` are sent each short poll cycle.

### Broadlink Hub (`BLHUB`)

One node created per configured Broadlink hub.

| Driver | Name | Description |
|--------|------|-------------|
| `ST` | Status | `Not Configured` / `Online` / `Error` |
| `GV0` | Model | Detected device model (e.g., RM4 Pro, RM4 Mini) |
| `GV1` | Connected | `Yes` / `No` |
| `TIME` | Last Update | Timestamp of the most recent poll |

Commands accepted: `UPDATE` (force immediate refresh).

### IR Controller (`BLIRCTL`)

Created automatically for each online hub.

| Driver | Name | Description |
|--------|------|-------------|
| `ST` | Status | `Idle` / `Start Learning` / `Check Packet Data` / `Learned` / `Failed` / `Duplicate` |
| `TIME` | Last Learn | Timestamp of the most recently learned IR code |
| `GV1` | Learn Count | Number of IR codes stored |
| `GV2` | Hub Connected | Whether the hub is reachable |

Commands accepted: `LEARNCODE` — starts an IR learning window. A new IR Code node is added automatically when a code is captured.

### RF Controller (`BLRFCTL`)

Same structure as the IR Controller. RF learning uses a sweep-and-capture window via the `python-broadlink` frequency sweep API (`sweep_frequency` / `check_frequency` / `find_rf_packet`). Falls back to the generic learn flow for devices that do not expose RF sweep.

### IR Code (`BLIRCODE`) / RF Code (`BLRFCODE`)

One node per learned code, parented to the appropriate controller.

| Driver | Name | Description |
|--------|------|-------------|
| `ST` | Status | `Ready` / `Sending` / `Sent OK` / `Failed` |
| `GV0` | Frequency (MHz) | Captured RF frequency in MHz (`BLRFCODE` only) |
| `TIME` | Created | Timestamp when the code was learned |
| `GV1` | Last Sent | Timestamp of the most recent transmission |
| `GV2` | Last Result | `Never` / `Success` / `Failed` |
| `GV3` | TX Count | Number of successful transmissions |

Commands accepted: `TXCODE` (`Send Code`) — transmits the stored packet via `device.send_data()`.

### Hub Sensor (`BLSENSOR`)

Optional child node created automatically under the hub node when a temperature/humidity sensor cable is detected. One sensor node per hub.

| Driver | Name | Description |
|--------|------|-------------|
| `ST` | Status | `Not Configured` / `Online` / `Error` — reflects hub connectivity |
| `CLITEMP` | Temperature | Current temperature in °C or °F (controlled by `TEMP_UNIT` parameter) |
| `CLIHUM` | Humidity | Current relative humidity (%) |
| `TIME` | Last Update | Timestamp of the most recent sensor reading |

Commands accepted: `UPDATE` — forces an immediate sensor reading refresh.




## Required parameter

| Key | Description |
|-----|-------------|
| `HUB_IP` | IP address of the Broadlink hub (e.g. `192.168.1.120` or list of IPs `192.168.1.120 192.168.1.121`) |

### Optional parameters

| Key | Default | Description |
|-----|---------|-------------|
| `TEMP_UNIT` | `C` | Temperature display unit. Set to `F` for Fahrenheit. |

### ShortPoll - Sends heartbeat and refreshes sensor if present
### LongPoll - refreshes connection and updates persistent data (node names etc.)


The Broadlink device must already be provisioned onto the local Wi-Fi network before the plugin can connect to it. The plugin does not perform initial Wi-Fi setup automatically.

## Persistence & Dynamic Profiles

Learned codes, hub metadata, and custom node names are persisted in PG3 `customdata`. On startup:
- Initial node reconciliation and dynamic profile loading wait until PG3 finishes its configuration (`CONFIGDONE`).
- If no valid IPv4 address is provided in `HUB_IP`, a single notice (`IP address must be provided in Configuration (HUB_IP).`) is posted without generating connection error notices.
- Parent hub (`BLHUB`) and controller (`BLIRCTL` / `BLRFCTL`) nodes are registered and confirmed via `ADDNODEDONE` before child sensor (`BLSENSOR`) and learned code (`BLIRCODE` / `BLRFCODE`) nodes are added.
- Stored node names are restored so user-defined renames in the Admin Console survive restarts.
- Driver names are populated from the dynamic profile definition (or fallback static `profile/` files prior to `CONFIGDONE`), and the dynamic JSON profile is published to PG3 via `updateJsonProfile()` only after PG3 configuration (`CONFIGDONE`) and all node initializations (`ADDNODEDONE`) have completed.

## Python Interface

Utilizes [`python-broadlink`](https://github.com/mjg59/python-broadlink), an open-source Broadlink device library by Matthew Garrett.