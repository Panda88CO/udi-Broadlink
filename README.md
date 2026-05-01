# udi-broadlink

Broadlink node server for UDI Polyglot v3 (PG3/PG3x), implemented in Python using:
Python interface
    Utilizes [`python-broadlink`] interface (https://github.com/mjg59/python-broadlink)  open-source Broadlink device library by Matthew Garrett

## Overview

Run one PG3 node server instance per Broadlink hub. Multiple hubs are supported by providing a list of IP addresses

## Node Organization
Each Hub creates a node - If temp and humidity sersor is present its data is shown in a child node 
The hub also generates 2 seprate nodes RF Controller and IF controller (with the HUB IP appended).  Each learned code becomes a child to this controller node

```

### Broadlink Hub (`setup`)

Primary node. Created automatically on startup.

| Driver | Name | Description |
|--------|------|-------------|
| `ST` | Status | `Not Configured` / `Online` / `Error` |
| `GV0` | Model | Detected device model (e.g., RM4 Pro, RM4 Mini) |
| `GV1` | Connected | `Yes` / `No` |
| `TIME` | Last Update | Timestamp of the most recent poll |
| `GV2` | Temperature | Present only when a sensor cable is detected |
| `GV3` | Humidity | Present only when a sensor cable is detected |

Commands accepted: `UPDATE` (force immediate refresh).
Heartbeat events `DON` / `DOF` are sent each short poll cycle.

### IR Controller (`blirctl`)

Created automatically under the hub node when the hub is online.

| Driver | Name | Description |
|--------|------|-------------|
| `ST` | Status | `Idle` / `Learning` / `Learned OK` / `Failed` |
| `TIME` | Last Learn | Timestamp of the most recently learned IR code |
| `GV1` | Learn Count | Number of IR codes stored |
| `GV2` | Hub Connected | Whether the hub is reachable |

Commands accepted: `LEARNCODE` — starts a 30-second IR learning window. A new IR Code node is added automatically when a code is captured.

### RF Controller (`blrfctl`)

Same structure as the IR Controller. RF learning uses a 45-second sweep-and-capture window via the `python-broadlink` frequency sweep API (`sweep_frequency` / `check_frequency` / `find_rf_packet`). Falls back to the generic learn flow for devices that do not expose RF sweep.

### IR Code (`blircode`) / RF Code (`blrfcode`)

One node per learned code, parented to the appropriate controller.

| Driver | Name | Description |
|--------|------|-------------|
| `ST` | Status | `Ready` / `Sending` / `Sent OK` / `Failed` |
| `TIME` | Created | Timestamp when the code was learned |
| `GV1` | Last Sent | Timestamp of the most recent transmission |
| `GV2` | Last Result | `Never` / `Success` / `Failed` |
| `GV3` | TX Count | Number of successful transmissions |

Commands accepted: `Send Code` — transmits the stored packet via `device.send_data()`.

## python-broadlink API Usage



### Required parameter

| Key | Description |
|-----|-------------|
| `HUB_IP` | IP address of the Broadlink hub (e.g. `192.168.1.120`) |

### Optional parameters

| Key | Default | Description |
|-----|---------|-------------|
| `TEMP_UNIT` | `C` | Temperature display unit. Set to `F` for Fahrenheit. |

The Broadlink device must already be provisioned onto the local Wi-Fi network before the plugin can connect to it. The plugin does not perform initial Wi-Fi setup automatically.

### Supported `HUB_IP` formats

Single IP:
```text
192.168.1.120
```

Legacy comma-separated list (only the first IP is used):
```text
192.168.1.120, 192.168.1.121
```

> Run one PG3 node server instance per hub. Multi-hub configurations are not supported in a single instance.

## Profile

The plugin publishes a fully dynamic JSON profile at startup via `updateJsonProfile(...)`. No static profile files are required. The profile is regenerated whenever sensor state or `TEMP_UNIT` changes so that temperature and humidity drivers appear or disappear from the `setup` node automatically.

## Persistence

Learned codes and node names are persisted to PG3 `customdata`. On restart:
- Stored node names are replayed so user-defined names survive restarts.
- All previously learned IR and RF code nodes are restored from `customdata` before the IR/RF controller nodes are added.
- Sensor state (has_temperature / has_humidity) is restored from `customdata` so the profile can be published correctly before the first sensor poll.

### PG3 install script
`install.sh` installs dependencies from `requirements.txt`.
