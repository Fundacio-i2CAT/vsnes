
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
