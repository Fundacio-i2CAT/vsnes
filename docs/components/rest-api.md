---
title: REST API
nav_order: 1
parent: Components
---

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
