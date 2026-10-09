
### Core Classes
1. **`Node.py`**
   - **Purpose**: Base class for all nodes (satellites and ground stations).
   - **Usage**: 
     - Create a `Node` object to represent a network node.
     - Configure VLAN interfaces, IP addresses, and manage ARP tables.
   - **Related Files**:
     - Extended by `Satellite.py` and `Ground_Station.py`.

2. **`Orbit.py`**
   - **Purpose**: Base class for handling satellite orbits using TLE data.
   - **Usage**:
     - Create an `Orbit` object to store and manage TLE data.
   - **Related Files**:
     - Extended by `SGP4.py` and `TwoBody.py` for orbit propagation.

3. **`Scenario.py`**
   - **Purpose**: Manages the overall emulation scenario.
   - **Usage**:
     - Load configuration from TOML files.
     - Manage nodes and channels.
     - Generate runtime scripts and CZML files for visualization.
   - **Related Files**:
     - Interacts with `Node.py`, `Channel.py`, and `Satellite.py`.

---

### Extended Classes
1. **`Satellite.py`**
   - **Purpose**: Extends `Node` to represent satellites.
   - **Usage**:
     - Create a `Satellite` object to propagate satellite positions.
     - Generate CZML data for visualization.
   - **Related Files**:
     - Uses `Orbit.py` for orbit data.

2. **`Ground_Station.py`**
   - **Purpose**: Extends `Node` to represent ground stations.
   - **Usage**:
     - Create a `GroundStation` object to represent static nodes on Earth.
     - Generate CZML data for visualization.

---

### Orbit Propagation Models
1. **`SGP4.py`**
   - **Purpose**: Implements the SGP4 model for orbit propagation.
   - **Usage**:
     - Use the `_ECEF`, `_POS`, or `_ECI` methods to calculate satellite positions in different coordinate systems.
   - **Related Files**:
     - Extends `Orbit.py`.

2. **`TwoBody.py`**
   - **Purpose**: Implements a two-body model for orbit propagation.
   - **Usage**:
     - Use as an alternative to the SGP4 model for simpler orbit calculations.
   - **Related Files**:
     - Extends `Orbit.py`.

---

### Communication and Channels
1. **`Channel.py`**
   - **Purpose**: Handles communication channels between nodes.
   - **Usage**:
     - Create a `Channel` object to calculate delays and manage channel properties.
     - Generate CZML data for visualizing communication links.
   - **Related Files**:
     - Uses `channel_threshold.py` for threshold calculations.

2. **`channel_threshold.py`**
   - **Purpose**: Defines thresholds and parameters for channel configurations.
   - **Usage**:
     - Use to manage or calculate thresholds for communication channels.

---

### Routing
1. **`routing.py`**
   - **Purpose**: Registry of mesh routing protocols. Exactly one is active per scenario, selected with `[Routing] protocol = 'olsrd' | 'babel' | 'none'` in `config.toml` (`none` = netem shaping only, no daemon).
   - **Usage**:
     - `get_protocol(name)` returns the `RoutingProtocol` entry, `None` for `'none'`, and raises on unknown names so config errors surface at load time.
     - Each `RoutingProtocol` declares its firewall binary, dedicated chain (`VSNES_OLSR`, `VSNES_BABEL`), how out-of-LOS peers are dropped (`src_ip` for OLSR, `src_mac` for babel's IPv6 link-local hellos), the gated UDP port (698 / 6696), and the `routing-ctl` start/stop commands.
     - Its methods build the shell lines that set up/tear down the chain, add/remove per-peer DROP rules, and start/stop the daemon; `Channel.py` batches them into one `docker exec` per node.
     - To add a protocol, add one entry to `PROTOCOLS` (plus `routing-ctl` support in the node image) — see the module docstring, "Adding a routing protocol".
   - **Related Files**:
     - Used by `Scenario.py` (validates the protocol at load) and `Channel.py` (applies the gating and manages the daemon lifecycle).

---

### Orbital Data Generation
1. **`tle_generator.py`**
   - **Purpose**: Generates a TLE file for N satellites in one orbital plane — a full evenly spaced ring by default, or a tight arc with `--spacing-deg` so all satellites stay in line of sight of each other.
   - **Usage**:
     - Satellites are named `<prefix><n>` (default `SATELLITE-1..N`) so they match the satellite names in `config.toml`. Defaults reproduce the walker66 orbit (86.4° inclination, 14.35663288 rev/day).
     - CLI: `python3 Class/tle_generator.py 5 test/configs/plane5.tle` — options `--prefix`, `--first-index`, `--inclination`, `--raan`, `--altitude-km` (overrides `--mean-motion`), `--mean-motion`, `--phase-offset`, `--spacing-deg`, `--epoch`, `--overwrite`.
     - Python: `generate_tle_text(...)` returns the TLE text; `write_tle(path, ...)` writes it (refuses to overwrite unless `overwrite=True`).
   - **Related Files**:
     - Backs the `generate_tle` tool in `mcpServer.py`.

---

### Time Management
1. **`Time_parameters.py`**
   - **Purpose**: Manages time-related settings for the emulation.
   - **Usage**:
     - Configure time intervals and speeds for contact and non-contact scenarios.

---

### Server and Visualization
1. **`Server.py`**
   - **Purpose**: Implements a Flask-based server for Cesium visualizations.
   - **Usage**:
     - Serve CZML files for visualization.
     - Query satellite positions and orbits via API endpoints.

2. **`templates/`**
   - **Purpose**: Contains HTML and CZML templates for Cesium visualizations.
   - **Key Files**:
     - `index.html`: Main HTML file for Cesium-based visualization.
     - `ScenarioCZML.czml`: CZML file defining the scenario for visualization.

---

### Miscellaneous
1. **`__pycache__/`**
   - **Purpose**: Contains compiled Python files for faster execution.
   - **Note**: This folder is typically ignored in version control.

---
