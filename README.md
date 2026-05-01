# udi-broadlink

Broadlink node server for UDI Polyglot v3 (PG3/PG3x), implemented in Python using:


## Overview

Run one PG3 node server instance per Broadlink hub. Multiple hubs are supported by providing a list of IP addresses

## Node Organization
Each Hub creates a node - If temp and humidity sensor is present its data is shown in a child node 
The hub also generates 2 separate nodes RF Controller and IR Controller (with the HUB IP appended).  Each learned code becomes a child to this controller node


## Learning RF codes
Learning an RF code is a two step task.  First the RF controller searches for teh correct frequecy - During this time oneneed to press the key being learned - The HUBs LED remains on during this time.  once the LED goes off, the AC will ask you to press the key one more - and the actual code is learned.  If the code is alrady learned it cannot be stored again (you can erase the code in the polyglot interface or ungroup the RF controller, Delete and regroup)
Note, you can rename the codes once learned - they should keep the name after a restart.


### Broadlink Controller (`setup`)

Top-level coordinator node. Created automatically on startup.

| Driver | Name | Description |
|--------|------|-------------|
| `ST` | Status | `No Hubs Configured` / `All Online` / `Partial` / `None Online` |
| `GV0` | Hub Count | Number of configured hubs |
| `TIME` | Last Update | Timestamp of the most recent poll |

Commands accepted: `UPDATE` (force immediate refresh).
Heartbeat events `DON` / `DOF` are sent each short poll cycle.

### Broadlink Hub (`blhub`)

One node per configured hub IP. Created automatically once the hub is confirmed online.

| Driver | Name | Description |
|--------|------|-------------|
| `ST` | Status | `Not Configured` / `Online` / `Error` |
| `GV0` | Model | Detected device model (e.g., RM4 Pro, RM4 Mini) |
| `GV1` | Connected | `Yes` / `No` |
| `TIME` | Last Update | Timestamp of the most recent poll |

Commands accepted: `UPDATE` (force immediate refresh).

### IR Controller (`blirctl`)

Created automatically under the hub node when the hub is online.

| Driver | Name | Description |
|--------|------|-------------|
| `ST` | Status | `Idle` / `Learning` / `Learned OK` / `Failed` |
| `TIME` | Last Learn | Timestamp of the most recently learned IR code |
| `GV1` | Learn Count | Number of IR codes stored |
| `GV2` | Hub Connected | Whether the hub is reachable |

Commands accepted: `LEARNCODE` — starts a 12-second IR learning window. A new IR Code node is added automatically when a code is captured.

### RF Controller (`blrfctl`)

Same driver structure as the IR Controller. RF learning uses a 20-second frequency sweep window followed by a 6-second packet-capture window via the `python-broadlink` frequency sweep API (`sweep_frequency` / `check_frequency` / `find_rf_packet`). Falls back to the generic learn flow for devices that do not expose RF sweep.

### IR Code (`blircode`)

One node per learned IR code, parented to the IR Controller.

| Driver | Name | Description |
|--------|------|-------------|
| `ST` | Status | `Ready` / `Sending` / `Sent OK` / `Failed` |
| `TIME` | Created | Timestamp when the code was learned |
| `GV1` | Last Sent | Timestamp of the most recent transmission |
| `GV2` | Last Result | `Never` / `Success` / `Failed` |
| `GV3` | TX Count | Number of successful transmissions |

Commands accepted: `TXCODE` (`Send Code`) — transmits the stored packet.

### RF Code (`blrfcode`)

One node per learned RF code, parented to the RF Controller. Identical to IR Code with one additional driver:

| Driver | Name | Description |
|--------|------|-------------|
| `ST` | Status | `Ready` / `Sending` / `Sent OK` / `Failed` |
| `GV0` | Frequency (MHz) | Detected RF carrier frequency, or `No Frequency Identified` if not captured |
| `TIME` | Created | Timestamp when the code was learned |
| `GV1` | Last Sent | Timestamp of the most recent transmission |
| `GV2` | Last Result | `Never` / `Success` / `Failed` |
| `GV3` | TX Count | Number of successful transmissions |

Commands accepted: `TXCODE` (`Send Code`) — transmits the stored packet.

### Hub Sensor (`blsensor`)

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

## Persistence

Learned codes and node names are persisted to PG3 `customdata`. On restart:
- Stored node names are replayed so user-defined names survive restarts.
- All previously learned IR and RF code nodes are restored from `customdata` before the IR/RF controller nodes are added.
- Sensor state (has_temperature / has_humidity) is restored from `customdata` so the profile can be published correctly before the first sensor poll.

## Python interface
    Utilizes [`python-broadlink`] interface (https://github.com/mjg59/python-broadlink)  open-source Broadlink device library by Matthew Garrett