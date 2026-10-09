---
title: MCP server
nav_order: 2
parent: Components
---

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
| `generate_tle` | Generates a TLE file of N satellites evenly spaced in one orbital plane (names `SATELLITE-1..N` by default, matching `config.toml`); defaults reproduce the walker66 orbit. Writes only inside the SNES directory |
| `generate_config_toml` | Generates a `config.toml` file from satellites, ground stations, channels, and time parameters. For `type = 'vm'` nodes, `clone_vm` sets the libvirt base image to clone (default `debian11`) |
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
