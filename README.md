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
| `POST` | `/api/load-config` | **Stage 1 (load):** load `config.toml`, validate it, and create the nodes. Optional body `{"isCzml": true, "isDockercompose": false}` |
| `POST` | `/api/init-scenario` | **Stage 2 (init/prepare):** start/validate the nodes per their `type`, gate + start the routing protocol selected in the toml's `[Routing]` section, and apply the channel shaping — runs in the background. Optional body `{"isVM": true, "password": "..."}` (`isVM=false` skips all node/network config and computes contacts/timing only) |
| `GET` | `/api/scenario` | Get current scenario description |
| `POST` | `/api/write-czml` | Generate the CZML file for Cesium |
| `POST` | `/api/start-vms` | Start all VMs |
| `POST` | `/api/stop-vm/<name>` | Stop a specific VM |
| `POST` | `/api/stop-all-vms` | Stop all VMs |
| `DELETE` | `/api/delete-vm/<name>` | Delete a specific VM |
| `DELETE` | `/api/delete-all-vms` | Delete all VMs |
| `POST` | `/api/compose/up` | Start the Docker node containers (`docker compose up -d`); optional JSON body `{"services": ["satellite-1", ...]}` to start a subset |
| `POST` | `/api/compose/down` | Stop and remove the Docker node containers (`docker compose down`) |
| `POST` | `/api/simulation/start` | **Stage 3 (start):** start only the simulation clock (init must have finished). Also restarts the clock after a natural end. Optional body `{"isVM": ..., "password": ...}` to override the saved values |
| `POST` | `/api/visualization/start` | Start visualization only |
| `POST` | `/api/simulation/stop` | Stop the run and **remove the channel-shaping/routing rules**, keeping the loaded scenario so the clock can be re-started. Optional body `{"password": "..."}` |
| `GET` | `/api/status` | Get system status and simulation progress |
| `POST` | `/api/reset` | Full teardown — stop, remove rules, and wipe all state back to `IDLE` |
| `GET` | `/api/help` | List all available endpoints |

The API tracks system state across the lifecycle (`IDLE → CONFIG_LOADED → PREPARING_VMS → RUNNING_SIMULATION → SIMULATION_ENDED`) and returns `409 Conflict` responses for invalid transitions. The lifecycle is split into three explicit stages:

1. **load** — parse `config.toml`, validate, and create the nodes.
2. **init / prepare** — configure the nodes, install the per-link rules, and apply the channel shaping (the one-time network setup). After this the scenario is ready but the clock is not moving.
3. **start** — advance the simulation clock only (positions + timing; per-tick network updates when enabled).

Reaching the end of the timeline **stops the clock and resets the time marker to zero, but leaves the channel shaping and rules applied** (`SIMULATION_ENDED`). From there, `start` replays from the reset marker without re-preparing, while `stop` (or `reset`) is what actually removes the rules. This keeps the network state intact at the end of a run instead of tearing it down underneath still-running nodes.

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
| `load_scenario` | **Stage 1:** load `config.toml`, validate, and create the nodes |
| `init_scenario` | **Stage 2:** prepare the scenario — configure nodes, install rules, apply channel shaping |
| `prepare_simulation` | Back-compat one-shot: load + init with defaults |
| `start_simulation` | **Stage 3:** start (or restart) the simulation clock |
| `stop_simulation` | Stop the run and remove the rules, **keeping the scenario** so it can be re-started |
| `reset_system` | Full teardown — stop, remove rules, and wipe the scenario back to `IDLE` |
| `get_emulator_status` | Get full system status |
| `compose_up` | Start the Docker node containers (optionally a list of service names) |
| `compose_down` | Stop and remove the Docker node containers |

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
Generated by `Scenario.generate_docker_compose()` from the loaded scenario: one service per `type='container'` node (real `container_external` nodes are never included — VSNES doesn't manage them) plus a local `registry` service, on the `olsr_net` bridge (subnet derived from the first node's `ip_ext`, typically `172.28.0.0/24`). Regenerate it via `POST /api/load-config {"isDockercompose": true}` or `POST /api/compose/generate` — don't hand-edit it.

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
python SatelliteEmulator.py --web        # API + Cesium web server (port 5580)
python SatelliteEmulator.py --ntp        # API + NTP server (port 12345)
python SatelliteEmulator.py --mcp        # API + MCP server (port 8560)
python SatelliteEmulator.py --all        # API + Web + NTP + MCP
python SatelliteEmulator.py --web --mcp  # combine any flags
```

Services started and their addresses:

| Service | Address | Flag |
|---------|---------|------|
| REST API | `http://localhost:5050` | always |
| Cesium GUI | `http://localhost:5580` | `--web` |
| NTP server | port `12345` | `--ntp` |
| MCP server | `http://localhost:8560` | `--mcp` |

Available interactive commands:

| Command | Aliases | Description |
|---------|---------|-------------|
| `help` | | Show all available actions |
| `load` | `load_scenario` | **Stage 1:** ask for the config path, then load + validate it and create the nodes |
| `init` | `init_scenario`, `prepare` | **Stage 2:** prepare the scenario — asks for the sudo password and the `isVM` flag, then starts/validates nodes per their `type`, gates + starts the toml-selected routing protocol, and applies channel shaping |
| `scenario` | | Display loaded nodes and their types |
| `start_vms` | `vm` | Create or start containers/VMs for all nodes |
| `compose_up [services...]` | `compose up` | Start the Docker node containers via the API (`docker compose up -d`); optionally name specific services, e.g. `compose_up satellite-1 ibi_es` |
| `compose_down` | `compose down` | Stop and remove the Docker node containers via the API (`docker compose down`) |
| `write_czml` | | Generate `ScenarioCZML.czml` for Cesium |
| `run` | `run_all`, `emu`, `cesium` | **Stage 3:** start the simulation clock (init must have finished). Also restarts the clock after a natural end |
| `stop` | | Stop the run and remove the rules; keeps the scenario (re-run with `run`) |
| `reset` | | Full teardown — stop, remove rules, and wipe the scenario to `IDLE` |
| `shutdown_vms` | | Shut down all nodes |
| `delete_vm` | `delete` | Delete a specific VM or all VMs |
| `exit` | | Detach the controller — **leaves the sim and rules running**; use `stop`/`reset` first to tear down |

### API Mode

```bash
python SatelliteEmulator.py --web
```

- REST API: `http://localhost:5050`
- Cesium GUI: `http://localhost:5580`
- API docs: `http://localhost:5050/api/help`

Typical workflow:
```bash
# 1. Upload files
curl -F "file=@config.toml" http://localhost:5050/api/upload-config
curl -F "file=@sample.tle"  http://localhost:5050/api/upload-tle

# 2. Start the Docker node containers (all, or a subset of services)
curl -X POST http://localhost:5050/api/compose/up
curl -X POST -H "Content-Type: application/json" \
     -d '{"services": ["satellite-1", "satellite-2", "satellite-3", "ibi_es"]}' \
     http://localhost:5050/api/compose/up

# 3. Load (create nodes), then init/prepare (start/validate nodes per type,
#    gate + start the toml-selected routing protocol, apply channel shaping —
#    runs in the background; poll /api/status until ready)
curl -X POST http://localhost:5050/api/load-config
curl -X POST -H "Content-Type: application/json" \
     -d '{"isVM": true, "password": "..."}' \
     http://localhost:5050/api/init-scenario

# 4. Start the clock (start again later to replay after a natural end)
curl -X POST http://localhost:5050/api/simulation/start

# 5. Monitor (RUNNING_SIMULATION → SIMULATION_ENDED when the timeline finishes;
#    the rules stay applied at the end)
curl http://localhost:5050/api/status

# 6. Stop — removes the rules but keeps the scenario (use /api/reset for a full wipe)
curl -X POST http://localhost:5050/api/simulation/stop

# 7. Tear down the containers
curl -X POST http://localhost:5050/api/compose/down
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
4. AI calls `load_scenario` → `init_scenario` → `start_simulation` to launch the emulation (or `prepare_simulation` for the one-shot load+init)
5. AI monitors progress with `get_emulator_status`; at the end of the timeline the run stops but the rules stay applied (`start_simulation` replays it), and `stop_simulation` / `reset_system` tears it down

---

## Configuration File

The configuration file (`config.toml`) defines the parameters for VSNES. Below is a detailed explanation of each section:

---

### 1. Network Configuration
- **`network`**: Specifies the subnet for the emulated network (in CIDR notation) — the flat `10.0.0.x`-style address every node gets as its per-scenario emulated IP.
- **`network_ext`**: Specifies the subnet of the network that hosts the nodes' management/external addresses (`ip_ext`, in CIDR notation) — the Docker bridge or host-reachable network for classic-VM/external nodes.
- **`unicast_flooding`**: If `1`, the virtual switch of brSATEMU will not logically map MAC addresses with ports. This means that all the traffic received from one port will be broadcasted to all the other ports. If `0`, the virtual switch will map MAC addresses and forward traffic only to the correct destination port.
- **`host_interface`** *(optional)*: The host NIC used for classic-VM vxlan tunnels. Auto-detected (first non-loopback, non-libvirt interface) if omitted.

---

### 2. Routing Protocol

```toml
[Routing]
	protocol = 'olsrd'   # olsrd | babel | none
```

Selects which mesh routing daemon VSNES gates and manages inside every container node. Only ONE protocol's firewall rules and daemon are ever installed — switching protocols (or to `none`) between runs always converges cleanly, even without a clean stop first. `none` applies netem channel shaping only, with no routing daemon and no per-pair firewall gating. Missing the `[Routing]` section defaults to `none` (with a warning).

Protocols are a small registry in `Class/routing.py` — see the module docstring ("Adding a routing protocol") to add one (e.g. an experimental QUIC/DTN router): each entry declares its firewall binary/chain/gating-port and daemon start/stop commands, and Channel.py drives any entry generically.

---

### 3. Time Configuration
- **`TimeInterval`**: Time step for the simulation in minutes.
- **`Contact_speed`**: Speed multiplier for contact periods.
- **`Non_contact_speed`**: Speed multiplier for non-contact periods.
- **`start_datetime`**: Start time of the simulation in `YYYY-MM-DD HH:MM:SS` format.
- **`end_datetime`**: End time of the simulation in `YYYY-MM-DD HH:MM:SS` format.

---

### 4. Node Type

Every satellite and ground station carries one required **`type`** key — the single switch that decides how VSNES creates it, reaches it, and tears it down. There is no back-compat with older `isVM`/`is_external_vm`/`is_docker` flags; a config using them is rejected at `load-config` with a clear per-node error.

| `type` | Lifecycle | Reached via |
|---|---|---|
| `vm` | Internal libvirt VM: cloned from `clone_VM.name_VM` with `virt-clone` (machine-id reset before first boot so DHCP leases don't collide), started/resumed with `virsh` | SSH, for configuration only |
| `vm_external` | Never created/destroyed by VSNES — must already be running | SSH; init fails fast (~seconds, not a blind multi-minute retry) if unreachable |
| `container` | Local Docker container: VSNES generates `docker-compose.yml` and brings up exactly the missing services (`--no-recreate --no-build` — a live cluster inside is never disturbed) | `docker exec` |
| `container_external` | A container on another host — never created/removed by VSNES | validated over the network like `vm_external` |

Required keys per type:
- **`ip_ext`**: required for every type except `vm` (internal VMs get their address from `virsh domifaddr`).
- **`clone_VM.name_VM`**: required only for `type = 'vm'` — the base libvirt domain to clone.
- **`interface`**: always required — the node's NIC (`eth0` for containers, the VM's real NIC name, e.g. `enp1s0`, for VMs).

Mixed scenarios are supported (e.g. a container constellation with one `vm_external` ground station) — VSNES configures each node type appropriately in the same run, including data-plane shaping (netem) across both the Docker/IFB path and the classic VLAN+vxlan path.

### 5. Space Segment (Satellites)
- **`TLE`**: Path to the TLE file containing satellite orbital data.
- **`SatelliteSistem`**: Defines individual satellites.
  - **`propagator`**: Orbit propagation model (`SGP4` or `TwoBody`).
  - **`name`**: Name of the satellite.
  - **`group`**: Group name (e.g., `LEO` for Low Earth Orbit).
  - **`OS`**: Operating system of the satellite's node (`debian`, `ubuntu`, or `alpine`).
  - **`username`**: Username for SSH/container access.
  - **`password`**: Password for SSH/container access.
  - **`type`**: Node lifecycle type — see [Node Type](#4-node-type) above.
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
  - **`type`**: Node lifecycle type — see [Node Type](#4-node-type) above.
  - **`ip_ext`**: Management/external IP address (required for all types except `vm`).
  - **`interface`**: Network interface name.
  - **`clone_VM`**: Only meaningful for `type = 'vm'`.
    - **`name_VM`**: Name of the base VM to clone.

---

### 7. Channels (Communication Links)
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
