# udi-broadlink

Broadlink node server for UDI Polyglot v3 (PG3/PG3x), implemented in Python using:
- `udi_interface`
- `python-broadlink`

Initial scope:
- Broadlink RM remotes (including RM4 Pro class devices)
- Two parent nodes: one for IR, one for RF
- One subnode per configured code string (IR or RF)

The code is intentionally structured for readability and future extension to other Broadlink device families.

## Architecture

- `udi_broadlink.py`: Entry point
- `nodes.py`: Controller + parent/subnode classes
- `config_parser.py`: PG3 custom parameter parsing
- `broadlink_client.py`: Wrapper around `python-broadlink` API

Node layout in ISY/IoX:
- `setup` controller
- `Broadlink IR` parent node
- `Broadlink RF` parent node
- `IR <code_name>` subnodes
- `RF <code_name>` subnodes

## Configuration

Configure custom parameters in PG3 Configuration.

Required parameters:
- `USER_ID`
- `USER_PASSWORD`
- `HUB_IP`

Notes:
- `USER_ID` and `USER_PASSWORD` are currently validated and stored, but not required by the local RM protocol itself.
- `HUB_IP` is used to connect/authenticate to the Broadlink hub.

AP provisioning (optional):
- `WIFI_SSID`, `WIFI_PASSWORD`, `WIFI_SECURITY_MODE`, `SETUP_IP`
- Run setup-node command `Provision AP Setup` to call `broadlink.setup(...)` when device is in AP mode.

Code parameters:
- `IR_CODES`
- `RF_CODES`

Each code parameter supports either format:

1) JSON object
```json
{"TV Power": "2600d200...", "Receiver VolumeUp": "b64:AAECAw..."}
```

2) Multi-line key/value
```text
TV Power=2600d200...
Receiver VolumeUp=b64:AAECAw...
```

Code value encoding:
- Hex string (default)
- Base64 prefixed with `b64:`

## Behavior

- On startup and parameter updates (`handleParams`), the node server:
  - Parses config
  - Connects/authenticates to Broadlink hub using `hello()` + `auth()` for normal runtime control
  - Builds/rebuilds IR and RF code subnodes from configured code maps
- AP provisioning is a separate explicit action (`APSETUP`) that calls `broadlink.setup()`.
- Each code subnode exposes `TXCODE` (Send Code)
- IR/RF parent nodes expose `LEARNCODE` to learn new packets from the hub
- Short poll toggles heartbeat (`DON`/`DOF`) on controller
- Long poll refreshes hub connectivity and updates parent node status

### Learning Workflow

- Run `Learn IR Code` on the `Broadlink IR` parent node or `Learn RF Code` on the `Broadlink RF` parent node.
- After a successful learn, the node server:
  - creates a generated code name (for example `Learned IR 01`)
  - stores the packet in persistent `customdata`
  - rebuilds dynamic subnodes so the learned code appears as a new subnode

Learned codes persist across restarts through `customdata`.

## Install

### Local test
```bash
pip install -r requirements.txt
python udi_broadlink.py
```

### PG3 install script
`install.sh` installs dependencies from `requirements.txt`.

## Extending to Other Broadlink Devices

Design points for extension:
- Add new methods/classes in `broadlink_client.py` for additional device types
- Add new nodedefs in `profile/nodedef/nodedefs.xml`
- Add corresponding node classes in `nodes.py`
- Add parameter parsing in `config_parser.py`

This keeps Broadlink protocol operations separate from node orchestration logic.
