---
title: Satellites & ground stations
nav_order: 5
parent: Configuration
---

- **`TLE`**: Path to the TLE file containing satellite orbital data.
- **`SatelliteSistem`**: Defines individual satellites.
  - **`propagator`**: Orbit propagation model (`SGP4` or `TwoBody`).
  - **`name`**: Name of the satellite.
  - **`group`**: Group name (e.g., `LEO` for Low Earth Orbit).
  - **`OS`**: Operating system of the satellite's node (`debian`, `ubuntu`, or `alpine`).
  - **`username`**: Username for SSH/container access.
  - **`password`**: Password for SSH/container access.
  - **`type`**: Node lifecycle type — see [Node Type]({{ site.baseurl }}/configuration/node-type/) above.
  - **`ip_ext`**: Management/external IP address (required for all types except `vm`).
  - **`interface`**: Network interface name.
  - **`clone_VM`**: Only meaningful for `type = 'vm'`.
    - **`name_VM`**: Name of the base VM to clone.

---

### 6. Ground Segment (Ground Stations)
- **`GroundSistem`**: Defines individual ground stations.
  - **`name`**: Name of the ground station.
  - **`group`**: Group name (e.g., `GS` for Ground Station).
  - **`latitude`**: Latitude of the ground station in degrees.
  - **`longitude`**: Longitude of the ground station in degrees.
  - **`height`**: Height of the ground station above sea level in meters.
  - **`OS`**: Operating system of the ground station's node (`debian`, `ubuntu`, or `alpine`).
  - **`username`**: Username for SSH/container access.
  - **`password`**: Password for SSH/container access.
  - **`type`**: Node lifecycle type — see [Node Type]({{ site.baseurl }}/configuration/node-type/) above.
  - **`ip_ext`**: Management/external IP address (required for all types except `vm`).
  - **`interface`**: Network interface name.
  - **`clone_VM`**: Only meaningful for `type = 'vm'`.
    - **`name_VM`**: Name of the base VM to clone.
