<img src="https://wikifab.org/images/b/b6/Group-i2CAT_logo-color-alta.jpg" width=25% height=25%>

[![Maintenance](https://img.shields.io/badge/Status-Maintained-green.svg)]()
[![made-with-python](https://img.shields.io/badge/Made%20with-Python-blue)](https://www.python.org/)
[![AGPLv3 license](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0.en.html)


# Virtual Satellite Network Emulator System (VSNES)

The Virtual Satellite Network Emulator System (VSNES) is a Python-based tool designed to simulate satellite networks, including satellite orbits, ground stations, and communication channels. It provides tools for visualizing scenarios in Cesium, managing virtual machines (VMs) and containers for emulation, and propagating satellite orbits using TLE data. VSNES can be integrated into AI workflows by exposing a Model Context Protocol (MCP) server, enabling AI agents such as Claude to autonomously configure, launch, and monitor satellite network emulations.

---

#

### Web Dashboard
A new browser-based control panel is served by the Cesium visualization server (`Class/static/`). It includes a custom design system with Orbitron and Lato fonts, icon set, and a responsive layout. The frontend communicates with the REST API to load configs, manage VMs, and control the simulation without using the CLI.



## Features

- **Orbit Propagation**: Supports SGP4 and Two-Body models for satellite orbit propagation.
- **Node Management**: Handles satellites and ground stations as nodes in the network.
- **Communication Channels**: Simulates communication delays and properties between nodes.
- **Visualization**: Generates CZML files for Cesium-based 3D visualization.
- **VM Management**: Creates, starts, stops, and deletes virtual machines for emulation.
- **Server Integration**: Provides a Flask-based server for Cesium visualizations and API endpoints.
- **REST API**: Full HTTP API for programmatic control of the emulator lifecycle.
- **MCP Server**: AI-agent-friendly tool interface via the Model Context Protocol.
- **Simulation NTP**: Custom NTP server serving simulation time to emulated VMs.
- **Routing Protocol Selection**: Choose `olsrd`, `babel`, or `none` per scenario (`[Routing]` in `config.toml`) — VSNES gates the daemon's discovery to in-LOS neighbours and manages its full lifecycle (start/restart/stop) automatically; only one protocol's rules are ever installed.
- **Mixed Node Types**: `vm`, `vm_external`, `container`, `container_external` per node — internal VMs/containers are created and torn down by VSNES; external ones are only validated over the network.

---

## Project Structure

### 1. **`Class/`**
Contains the core classes and modules for the emulator.

- **Core Classes**:
  - `Node.py`: Base class for all nodes (satellites and ground stations).
  - `Orbit.py`: Base class for handling satellite orbits using TLE data.
  - `Scenario.py`: Manages the overall emulation scenario.

- **Extended Classes**:
  - `Satellite.py`: Extends `Node` to represent satellites.
  - `Ground_Station.py`: Extends `Node` to represent ground stations.

- **Orbit Propagation Models**:
  - `SGP4.py`: Implements the SGP4 model for orbit propagation.
  - `TwoBody.py`: Implements a two-body model for orbit propagation.

- **Communication and Channels**:
  - `Channel.py`: Handles communication channels between nodes.
  - `channel_threshold.py`: Defines thresholds and parameters for channel configurations.

- **Routing**:
  - `routing.py`: Registry of mesh routing protocols (`olsrd`, `babel`) selected by `[Routing]` in `config.toml` — firewall gating of out-of-LOS peers and daemon start/stop.

- **Orbital Data**:
  - `tle_generator.py`: Generates TLE files for N satellites in one orbital plane (CLI and used by the MCP `generate_tle` tool).

- **Time Management**:
  - `Time_parameters.py`: Manages time-related settings for the emulation.

- **Server and Visualization**:
  - `Server.py`: Flask server for Cesium visualization (port 5500).
  - `static/`: Web dashboard assets (CSS, JS, fonts, icons).
  - `templates/`: HTML and CZML templates for Cesium.

---


### Notes
- Ensure that the TLE file specified in the `SpaceSegment` section exists and contains valid TLE data. `sample.tle` contains a sample TLE file. To build a synthetic single-plane constellation, use `python3 Class/tle_generator.py <N> <output.tle>` (see `Class/README.md`) or the MCP `generate_tle` tool.
- The `clone_VM` section is only required for `type = 'vm'` nodes.
- The `Channels` section allows you to define multiple communication links between nodes.
- libvirt implements DHCP, so if you want to avoid modifying the configuration of each VM to allocate a static IP:
  - Get the MAC address of the VM: `$ virsh domiflist <VM_name>`
  - Apply the DHCP rule: `$ virsh net-edit default`
  ```xml
  <dhcp>
  ...
  <host mac="<VM_MAC>" name="VM_name" ip="<VM_static_IP>"/>
  ```
  - Restart the network, in this example `default`: `$ virsh net-destroy default` and `$ virsh net-start default`
  - Reboot the VM: `$ virsh shutdown <VM_name>` and `$ virsh start <VM_name>`
- Be careful if a kernel-level VPN is up in the host, as it will affect the routing table and make VMs not reachable. In that case, consider disabling the VPN.

# Other tools

## Libvirt Dashboard
Libvirt Dashboard utilizes Prometheus to visualize metrics of VMs in Grafana.


## Source

Developed within i2-22-RDI-IoT A2 DSS Sim.
Aquest projecte ha rebut finançament per part del Govern de la Generalitat de Catalunya dins del marc de l'estrategia [NewSpace](https://www.accio.gencat.cat/ca/serveis/banc-coneixement/cercador/BancConeixement/new_space_a_catalunya) a Catalunya.

## Copyright

Developed by Fundació Privada Internet i Innovació Digital a Catalunya (i2CAT).
Find more information at https://i2cat.net/tech-transfer/

## Licence

Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE. See https://www.gnu.org/licenses/agpl-3.0.en.html.

For licensing enquiries: techtransfer@i2cat.net
