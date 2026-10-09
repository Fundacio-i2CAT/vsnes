---
title: Time, server & misc
nav_order: 3
parent: Core classes
---

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
