# udi-broadlink (Local & Developer Reference)

Broadlink node server for UDI Polyglot v3 (PG3/PG3x), implemented in Python using:
- `udi_interface`
- `python-broadlink`

Scope:
- Supports one or multiple Broadlink RM hubs (such as RM4 Pro and RM4 Mini) in a single PG3 instance
- Coordinator setup node (`BLSETUP`) plus one hub node (`BLHUB`) per configured IP
- Optional child sensor node (`BLSENSOR`) when a temperature/humidity sensor cable is connected
- Separate IR (`BLIRCTL`) and RF (`BLRFCTL`) controller nodes per hub
- One child node per learned IR (`BLIRCODE`) or RF (`BLRFCODE`) code

## Architecture

- `udibroadlink.py`: Entry point
- `nodes.py`: Node classes (`SetupController`, `HubNode`, `HubSensorNode`, `IRControllerNode`, `RFControllerNode`, `IRCodeNode`, `RFCodeNode`) and dynamic profile generation
- `config_parser.py`: PG3 custom parameter parsing (`HUB_IP`, `TEMP_UNIT`)
- `broadlink_client.py`: Wrapper around the `python-broadlink` API (discovery, authentication, IR/RF learning, RF frequency sweep, sensor reads)
- `code_helpers.py`: RF payload extraction, duplicate signature matching, and unrecognized code logging
- `dynamic_profiles.json`: Source definitions for dynamic editors, node definitions, and NLS labels

Node hierarchy in ISY/IoX:
- `setup` (`BLSETUP`) — primary coordinator node
- `hub_<id>` (`BLHUB`) — per-hub status node
  - `sens_<id>` (`BLSENSOR`) — optional temperature/humidity child node
- `ir_<id>` (`BLIRCTL`) — per-hub IR learning controller
  - `irc_<id>_<hash>` (`BLIRCODE`) — learned IR code child nodes
- `rf_<id>` (`BLRFCTL`) — per-hub RF learning controller
  - `rfc_<id>_<hash>` (`BLRFCODE`) — learned RF code child nodes

All `nodedef` IDs (`BLSETUP`, `BLHUB`, `BLIRCTL`, `BLRFCTL`, `BLIRCODE`, `BLRFCODE`, `BLSENSOR`) and `editor` IDs (`HUBSTATUS`, `STATUSINDEX`, `BINARYINDEX`, `MODELINDEX`, `RAWVALUE`, `UNIXTIME`, `IRLEARNSTATUS`, `RFLEARNSTATUS`, `TXSTATUS`, `TXRESULT`, `FREQUENCYMHZ`, `BLTEMP`, `BLHUM`) are strictly uppercase alphanumeric with no special characters.

## Configuration

Configure custom parameters in the PG3 web UI:

Required parameters:
- `HUB_IP`: Single IP address (e.g., `192.168.1.120`) or multiple space/comma/newline-separated IPs (e.g., `192.168.1.120 192.168.1.121`)

Optional parameters:
- `TEMP_UNIT`: `C` (default) or `F` for temperature sensor display unit

## Runtime Behavior

- On startup (`START`) and parameter updates (`CUSTOMPARAMS`), `SetupController` reconciles the node hierarchy once both events have fired:
  - Adds and waits for confirmation (`ADDNODEDONE`) of each parent `BLHUB`, `BLIRCTL`, and `BLRFCTL` node before adding child `BLSENSOR`, `BLIRCODE`, and `BLRFCODE` nodes.
  - Defers all `setDriver()` updates on every node until its own `ADDNODEDONE` event confirms initialization (`nodeDefineDone = True`).
  - Generates dynamic profile files (`profile/editor/custom.xml`, `profile/nodedef/custom.xml`, `profile/nls/en_us.txt`) from `dynamic_profiles.json` (falling back to static `profile/` files if needed) and calls `poly.updateProfile()` only after all nodes have finished initializing.
- `shortPoll`: Toggles heartbeat (`DON` / `DOF`) on `BLSETUP` and refreshes `BLSENSOR` readings.
- `longPoll`: Verifies hub connectivity, reconnects offline hubs, and syncs user-customized node names to `customdata`.

### Learning Workflow

- Trigger `Learn IR Code` (`LEARNCODE`) on the `BLIRCTL` node or `Learn RF Code` (`LEARNCODE`) on the `BLRFCTL` node.
- For RF learning, the hub first sweeps for the RF frequency (`Start Learning`), then prompts (`Check Packet Data`) for a second button press to capture the packet.
- Duplicate codes are detected via multi-signature fingerprint matching (`code_helpers.py`) and flagged as `Duplicate` without creating redundant nodes.
- Newly learned codes are stored in PG3 `customdata`, assigned an initial name (e.g., `IR Code 001` or `RF Code 001`), and added immediately as child nodes.

## Install & Local Testing

```bash
pip install -r requirements.txt
pytest
python udibroadlink.py
```

`install.sh` is executed by PG3 to install dependencies from `requirements.txt`.
