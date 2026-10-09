---
title: CLI mode
nav_order: 1
parent: Usage
---

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
