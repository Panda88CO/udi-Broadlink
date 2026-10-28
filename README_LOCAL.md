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
- `nodes.py`: Node classes (`BroadlinkController`, `HubNode`, `HubSensorNode`, `IRControllerNode`, `RFControllerNode`, `IRCodeNode`, `RFCodeNode`) and in-code dynamic JSON profile generation (`_build_profile_definition()`)
- `config_parser.py`: PG3 custom parameter parsing and strict IPv4 validation (`HUB_IP`, `TEMP_UNIT`)
- `broadlink_client.py`: Wrapper around the `python-broadlink` API (discovery, authentication, IR/RF learning, RF frequency sweep, sensor reads)
- `code_helpers.py`: RF payload extraction, duplicate signature matching, and unrecognized code logging
- `profile/`: Static fallback profile definitions (`editor/custom.xml`, `nodedef/custom.xml`, `nls/en_us.txt`) used before dynamic profile initialization

Node hierarchy in ISY/IoX:
- `setup` (`BLSETUP`) — primary coordinator node
- `<mac>` (`BLHUB`) — per-hub status node (12-hex MAC address)
  - `<mac>se` (`BLSENSOR`) — optional temperature/humidity child node
- `<mac>ir` (`BLIRCTL`) — per-hub IR learning controller
  - `<mac[-10:]>i<NNN>` (`BLIRCODE`) — learned IR code child nodes
- `<mac>rf` (`BLRFCTL`) — per-hub RF learning controller
  - `<mac[-10:]>r<NNN>` (`BLRFCODE`) — learned RF code child nodes

All `nodedef` IDs (`BLSETUP`, `BLHUB`, `BLIRCTL`, `BLRFCTL`, `BLIRCODE`, `BLRFCODE`, `BLSENSOR`) and `editor` IDs (`HUBSTATUS`, `STATUSINDEX`, `BINARYINDEX`, `MODELINDEX`, `RAWVALUE`, `UNIXTIME`, `IRLEARNSTATUS`, `RFLEARNSTATUS`, `TXSTATUS`, `TXRESULT`, `FREQUENCYMHZ`, `BLTEMP`, `BLHUM`) are strictly uppercase alphanumeric with no special characters.

## Configuration

Configure custom parameters in the PG3 web UI:

Required parameters:
- `HUB_IP`: Single IPv4 address (e.g., `192.168.1.120`) or multiple space/comma/semicolon/newline-separated IPv4 addresses (e.g., `192.168.1.120 192.168.1.121`). Non-IPv4 placeholder text is ignored, and when no valid IPv4 address is configured, a single notice (`IP address must be provided in Configuration (HUB_IP).`) is displayed.

Optional parameters:
- `TEMP_UNIT`: `C` (default) or `F` for temperature sensor display unit

## Runtime Behavior

- On startup, `BroadlinkController` registers `BLSETUP`, calls `poly.ready()`, and waits for PG3 to finish delivering its initial configuration (`CONFIGDONE` / `config_done`):
  - `handle_params` parses `CUSTOMPARAMS` and defers initial node reconciliation and dynamic profile loading until `CONFIGDONE`.
  - Once `CONFIGDONE` fires, `BroadlinkController` adds and waits for confirmation (`ADDNODEDONE`) of each parent `BLHUB`, `BLIRCTL`, and `BLRFCTL` node before adding child `BLSENSOR`, `BLIRCODE`, and `BLRFCODE` nodes.
  - Defers all `setDriver()` updates on every node until its own `ADDNODEDONE` event confirms initialization (`nodeDefineDone = True`).
  - Populates driver `name` fields from static `profile/` definitions prior to `CONFIGDONE` and from the in-code dynamic profile (`_build_profile_definition()`) after `CONFIGDONE`, publishing the dynamic JSON profile via `poly.updateJsonProfile(profile, {"waitResponse": False})` only after PG3 configuration (`CONFIGDONE`) and all node initializations (`ADDNODEDONE`) have completed.
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
