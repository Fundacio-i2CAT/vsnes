<img src="https://wikifab.org/images/b/b6/Group-i2CAT_logo-color-alta.jpg" width=25% height=25%>

[![Maintenance](https://img.shields.io/badge/Status-Maintained-green.svg)]()
[![made-with-python](https://img.shields.io/badge/Made%20with-Python-blue)](https://www.python.org/)
[![AGPLv3 license](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0.en.html)


# Virtual Satellite Network Emulator System (VSNES)

The Virtual Satellite Network Emulator System (VSNES) is a Python-based tool designed to simulate satellite networks, including satellite orbits, ground stations, and communication channels. It provides tools for visualizing scenarios in Cesium, managing virtual machines (VMs) and containers for emulation, and propagating satellite orbits using TLE data. VSNES can be integrated into AI workflows by exposing a [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server, enabling AI agents such as Claude to autonomously configure, launch, and monitor satellite network emulations.

---

## What's New in v2.0

### REST API (`apiServer.py`)
A new Flask-based REST API server runs on port `5050` alongside the Cesium visualization server, exposing the full emulator lifecycle over HTTP. This replaces the need for direct CLI interaction and enables integration with external tools, dashboards, and automation pipelines.

Key endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/upload-config` | Upload a TOML configuration file |
| `POST` | `/api/upload-tle` | Upload a TLE file |
| `POST` | `/api/load-config` | Load `config.toml` into the system |
| `POST` | `/api/init-scenario` | Initialize the scenario from loaded config |
| `GET` | `/api/scenario` | Get current scenario description |
| `POST` | `/api/write-czml` | Generate the CZML file for Cesium |
| `POST` | `/api/start-vms` | Start all VMs |
| `POST` | `/api/stop-vm/<name>` | Stop a specific VM |
| `POST` | `/api/stop-all-vms` | Stop all VMs |
| `DELETE` | `/api/delete-vm/<name>` | Delete a specific VM |
| `DELETE` | `/api/delete-all-vms` | Delete all VMs |
| `POST` | `/api/simulation/start` | Start full emulation and visualization |
| `POST` | `/api/visualization/start` | Start visualization only |
| `POST` | `/api/simulation/stop` | Stop the running simulation |
| `GET` | `/api/status` | Get system status and simulation progress |
| `POST` | `/api/reset` | Stop simulation and reset all state |
| `GET` | `/api/help` | List all available endpoints |

The API tracks system state across the lifecycle (`IDLE → CONFIG_LOADED → SCENARIO_INIT → PREPARING_VMS → RUNNING_SIMULATION`) and returns `409 Conflict` responses for invalid transitions.

To start (launched automatically by `SatelliteEmulator.py`):
```bash
python SatelliteEmulator.py        # starts API + interactive CLI
python SatelliteEmulator.py --web  # API + Cesium web server
```

---

### MCP Server (`mcpServer.py`)
A [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server built with `fastmcp`, running on port `8560`. It exposes the emulator and VM management as callable tools for AI agents (e.g., Claude Desktop, Claude Code).

Available tools:

**Emulator Control** (via REST API)

| Tool | Description |
|------|-------------|
| `prepare_simulation` | Load config and initialize scenario |
| `start_simulation` | Start emulation and visualization |
| `stop_simulation` | Stop and reset the emulator |
| `get_emulator_status` | Get full system status |

**VM Management** (direct Libvirt/SSH)

| Tool | Description |
|------|-------------|
| `list_vms` | List all VMs (name, state, IP) via Libvirt |
| `manage_vm_power` | Start or stop a VM (or all VMs) via Libvirt |
| `execute_vm_command` | Run a shell command on a VM (or all VMs) via SSH |

**Configuration Generation** (AI-assisted setup)

| Tool | Description |
|------|-------------|
| `get_config_guide` | Returns a structured guide the AI uses to interview the user and collect scenario parameters |
| `generate_config_toml` | Generates a `config.toml` file from satellites, ground stations, channels, and time parameters |
| `generate_docker_compose` | Generates `docker-compose.yml` from a config file or explicit node list, optionally creating a `Dockerfile` |

To start (launched automatically by `SatelliteEmulator.py`):
```bash
python SatelliteEmulator.py --mcp        # API + MCP
python SatelliteEmulator.py --all        # API + Web + NTP + MCP
```

Configure SSH credentials and API base URL via environment variables:
```bash
export SNES_API_URL=http://localhost:5050
export VM_SSH_USER=debian
export VM_SSH_PASS=debian
```

---

### Simulation-Aware NTP Server (`ntpserver.py`)
A custom UDP NTP server that synchronizes VM clocks to the emulator's simulated time. It reads the current simulation timestamp from `simulation_time.txt` (updated by the emulator during runtime) and serves it to NTP clients. Falls back to system time if the file is unavailable.

```bash
# Default (port 123, requires root)
sudo python3 ntpserver.py

# Custom port (no root required)
python3 ntpserver.py --port 12345
```

The API server starts the NTP server automatically on port `12345`.

---

### Web Dashboard
A new browser-based control panel is served by the Cesium visualization server (`Class/static/`). It includes a custom design system with Orbitron and Lato fonts, icon set, and a responsive layout. The frontend communicates with the REST API to load configs, manage VMs, and control the simulation without using the CLI.

---

### Structured Logging
All server components write structured logs to `/tmp/log/snes.log` with timestamps and severity levels, in addition to console output.

---

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

- **Time Management**:
  - `Time_parameters.py`: Manages time-related settings for the emulation.

- **Server and Visualization**:
  - `Server.py`: Flask server for Cesium visualization (port 5500).
  - `static/`: Web dashboard assets (CSS, JS, fonts, icons).
  - `templates/`: HTML and CZML templates for Cesium.

---

### 2. **`SatelliteEmulator.py`**
Interactive CLI entry point. Talks to the REST API to load configs, manage VMs, generate CZML, and launch or stop the simulation.

---

### 3. **`apiServer.py`**
REST API server (port 5050). Exposes the full emulator lifecycle over HTTP. Also starts the Cesium visualization server and the NTP server automatically on launch.

---

### 4. **`mcpServer.py`**
MCP server (port 8560). Exposes emulator control, VM management, and configuration generation as AI-callable tools. Enables full integration with AI agents such as Claude Desktop or Claude Code.

---

### 5. **`ntpserver.py`**
Simulation-aware NTP server. Serves emulator simulation time to nodes in the emulated network.

---

### 6. **`docker-compose.yml`**
Defines all satellite and ground station containers for Docker-based deployments on the `vsnes_net` (172.27.12.0/24) bridge network.

---

### 7. **`docker/`**
- **`Dockerfile`**: Debian 12 image with SSH, networking tools, and k3s pre-installed.
- **`entrypoint.sh`**: Container startup script.

---

### 8. **`config.toml`**
Configuration file defining the scenario: nodes, channels, time parameters, and network settings.

---

## Installation

Follow these steps to set up VSNES on your machine:

### 1. System Requirements
- Linux-based operating system (tested on Ubuntu).
- Python 3.10 or later.
- Virtualization support (QEMU/KVM).

---

### 2. Install Required Packages

```bash
sudo install.sh
```

### 3. Fix for czml Library
The czml library requires a small fix. Open the file:

`sudo nano /usr/local/lib/python3.10/dist-packages/czml/czml.py`

> **Note:** Find the exact path with `pip3 show czml`

Replace:
```python
from pygeoif.geometry import as_shape as asShape
```
With:
```python
from pygeoif.factories import shape as asShape
```

---

## Usage

### CLI Mode

`SatelliteEmulator.py` is the single entry point. It always starts `apiServer.py` internally and drops into an interactive CLI once the API is ready. Optional flags control which additional services start alongside it.

```bash
python SatelliteEmulator.py              # API only
python SatelliteEmulator.py --web        # API + Cesium web server (port 5000)
python SatelliteEmulator.py --ntp        # API + NTP server (port 12345)
python SatelliteEmulator.py --mcp        # API + MCP server (port 8560)
python SatelliteEmulator.py --all        # API + Web + NTP + MCP
python SatelliteEmulator.py --web --mcp  # combine any flags
```

Services started and their addresses:

| Service | Address | Flag |
|---------|---------|------|
| REST API | `http://localhost:5050` | always |
| Cesium GUI | `http://localhost:5000` | `--web` |
| NTP server | port `12345` | `--ntp` |
| MCP server | `http://localhost:8560` | `--mcp` |

Available interactive commands:

| Command | Aliases | Description |
|---------|---------|-------------|
| `help` | | Show all available actions |
| `load_scenario` | `load` | Load `config.toml` and initialize the scenario |
| `scenario` | | Display loaded nodes and their types |
| `start_vms` | `vm` | Create or start containers/VMs for all nodes |
| `write_czml` | | Generate `ScenarioCZML.czml` for Cesium |
| `run_all` | `run` | Run full emulation and Cesium visualization |
| `run_emulator` | `emu`, `emulator`, `run_emu` | Run emulation only (no Cesium) |
| `run_cesium` | `cesium` | Run Cesium visualization only |
| `stop` | | Stop the running simulation |
| `shutdown_vms` | | Shut down all nodes |
| `delete_vm` | `delete` | Delete a specific VM or all VMs |
| `exit` | | End the program (prompts to delete VMs) |

### API Mode

```bash
python SatelliteEmulator.py --web
```

- REST API: `http://localhost:5050`
- Cesium GUI: `http://localhost:5000`
- API docs: `http://localhost:5050/api/help`

Typical workflow:
```bash
# 1. Upload files
curl -F "file=@config.toml" http://localhost:5050/api/upload-config
curl -F "file=@sample.tle"  http://localhost:5050/api/upload-tle

# 2. Load and initialize
curl -X POST http://localhost:5050/api/load-config
curl -X POST http://localhost:5050/api/init-scenario

# 3. Start simulation
curl -X POST http://localhost:5050/api/simulation/start

# 4. Monitor
curl http://localhost:5050/api/status

# 5. Stop
curl -X POST http://localhost:5050/api/simulation/stop
```

### MCP Mode (AI Integration)

The MCP server connects an AI agent directly to VSNES, allowing it to configure, launch, and monitor satellite network emulations through natural language.

```bash
python SatelliteEmulator.py --mcp        # API + MCP
python SatelliteEmulator.py --all        # API + Web + NTP + MCP
```

Configure the server via environment variables:
```bash
export SNES_API_URL=http://localhost:5050   # REST API address
export VM_SSH_USER=debian                   # SSH user for VMs
export VM_SSH_PASS=debian                   # SSH password for VMs
```

To connect from Claude Desktop, add the following to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "vsnes": {
      "url": "http://localhost:8560/mcp"
    }
  }
}
```

**Typical AI-driven workflow:**
1. AI calls `get_config_guide` to learn what parameters to collect
2. AI interviews the user and calls `generate_config_toml` to write `config.toml`
3. AI calls `generate_docker_compose` to create the container manifest
4. AI calls `prepare_simulation` → `start_simulation` to launch the emulation
5. AI monitors progress with `get_emulator_status` and stops with `stop_simulation`

---

## Configuration File

The configuration file (`config.toml`) defines the parameters for VSNES. Below is a detailed explanation of each section:

---

### 1. Network Configuration
- **`network`**: Specifies the subnet for the emulated network (in CIDR notation).
- **`network_ext`**: Specifies the subnet of the network which hosts the external domains/VMs in the Relay mode (in CIDR notation).
- **`unicast_flooding`**: If `1`, the virtual switch of brSATEMU will not logically map MAC addresses with ports. This means that all the traffic received from one port will be broadcasted to all the other ports. If `0`, the virtual switch will map MAC addresses and forward traffic only to the correct destination port.

---

### 2. Time Configuration
- **`TimeInterval`**: Time step for the simulation in minutes.
- **`Contact_speed`**: Speed multiplier for contact periods.
- **`Non_contact_speed`**: Speed multiplier for non-contact periods.
- **`start_datetime`**: Start time of the simulation in `YYYY-MM-DD HH:MM:SS` format.
- **`end_datetime`**: End time of the simulation in `YYYY-MM-DD HH:MM:SS` format.

---

### 3. Space Segment (Satellites)
- **`TLE`**: Path to the TLE file containing satellite orbital data.
- **`SatelliteSistem`**: Defines individual satellites.
  - **`propagator`**: Orbit propagation model (`SGP4` or `TwoBody`).
  - **`Service`**: Satellite service type (`Standard` or `Relay`).
  - **`name`**: Name of the satellite.
  - **`group`**: Group name (e.g., `LEO` for Low Earth Orbit).
  - **`OS`**: Operating system of the satellite's VM (`ubuntu` or `alpine`).
  - **`username`**: Username for the VM.
  - **`password`**: Password for the VM.
  - **`isVM`**: Indicates if the satellite is a virtual machine (`1` for true, `0` for false).
  - **`ip_ext`**: External IP address of the VM.
  - **`interface`**: Network interface name.
  - **`clone_VM`**: Configuration for cloning the VM.
    - **`name_VM`**: Name of the base VM to clone.

---

### 4. Ground Segment (Ground Stations)
- **`GroundSistem`**: Defines individual ground stations.
  - **`name`**: Name of the ground station.
  - **`group`**: Group name (e.g., `GS` for Ground Station).
  - **`latitude`**: Latitude of the ground station in degrees.
  - **`longitude`**: Longitude of the ground station in degrees.
  - **`height`**: Height of the ground station above sea level in meters.
  - **`OS`**: Operating system of the ground station's VM (`ubuntu` or `alpine`).
  - **`username`**: Username for the VM.
  - **`password`**: Password for the VM.
  - **`interface`**: Network interface name.
  - **`clone_VM`**: Configuration for cloning the VM.
    - **`name_VM`**: Name of the base VM to clone.

---

### 5. Channels (Communication Links)
- **`Channel`**: Defines communication links between nodes.
  - **`Node1`**: Group name of the first node (e.g., `LEO` for satellites).
  - **`Node2`**: Group name of the second node (e.g., `GS` for ground stations).
  - **`Min_elevation_angle`**: Minimum elevation angle for the link in degrees.
  - **`Threshold`**: Maximum distance for the link in meters.
  - **`Data_rate`**: Data rate of the link in Mbit/s.
  - **`Packet_loss`**: Percentage of packet loss for the link.
  - **`Correlated_losses`**: Percentage of correlated packet losses (e.g., burst losses).

---

### Notes
- Ensure that the TLE file specified in the `SpaceSegment` section exists and contains valid TLE data. `sample.tle` contains a sample TLE file.
- The `clone_VM` section is optional and only required if you are cloning virtual machines for the emulation.
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

### 0. Install Prometheus and Grafana
Install Prometheus

`$ sudo apt install prometheus`

`$ sudo systemctl status prometheus`

Install Grafana

`$ sudo apt-get install -y apt-transport-https software-properties-common wget`

`$ sudo mkdir -p /etc/apt/keyrings/`

`$ echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" | sudo tee -a /etc/apt/sources.list.d/grafana.list`

`$ echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com beta main" | sudo tee -a /etc/apt/sources.list.d/grafana.list`

`$ sudo apt-get update`

`$ sudo apt-get install grafana`

`$ sudo systemctl daemon-reload`

`$ sudo systemctl start grafana-server`

`$ sudo systemctl enable grafana-server`

`$ sudo systemctl status grafana-server`

### 1. Install prometheus-libvirt-exporter
Install prometheus-libvirt-exporter (https://github.com/zhangjianweibj/prometheus-libvirt-exporter)

`$ sudo apt install golang-go`

`$ go install github.com/goreleaser/goreleaser@latest`

`$ go install github.com/go-task/task/v3/cmd/task@latest`

`$ git clone https://github.com/zhangjianweibj/prometheus-libvirt-exporter.git`

`$ cd prometheus-libvirt-exporter/`

`$ go mod tidy`

`$ go mod vendor`

`$ go build ./...`

`$ go build`

Configure Prometheus

`$ nano /etc/prometheus/prometheus.yml`

At the end of the file `/etc/prometheus/prometheus.yml` (within `scrape_configs:`), add the following:

```
  - job_name: 'libvirt_exporter'
    static_configs:
      - targets: ['localhost:9000']
```

`$ sudo systemctl restart prometheus`

### 2. Add prometheus-libvirt-exporter to Grafana
Add a new data source connection of type Prometheus to Grafana. Include `http://localhost:9090` as the connection URL.

### 3. Import the dashboard
Download or copy the dashboard in JSON: https://grafana.com/grafana/dashboards/15682-libvirt/

Import or paste it in Grafana

### 4. Run prometheus-libvirt-exporter
Run prometheus-libvirt-exporter to start capturing metrics (Grafana will visualize them automatically)

`$ cd prometheus-libvirt-exporter`

`$ ./prometheus-libvirt-exporter`


## Source

Developed within i2-22-RDI-IoT A2 DSS Sim.
Aquest projecte ha rebut finançament per part del Govern de la Generalitat de Catalunya dins del marc de l'estrategia [NewSpace](https://www.accio.gencat.cat/ca/serveis/banc-coneixement/cercador/BancConeixement/new_space_a_catalunya) a Catalunya.

## Copyright

Developed by Fundació Privada Internet i Innovació Digital a Catalunya (i2CAT).
Find more information at https://i2cat.net/tech-transfer/

## Licence

Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE. See https://www.gnu.org/licenses/agpl-3.0.en.html.

For licensing enquiries: techtransfer@i2cat.net
