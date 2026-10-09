---
title: MCP mode (AI integration)
nav_order: 3
parent: Usage
---

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
2. AI interviews the user; if a synthetic constellation is wanted, it calls `generate_tle` first and passes the resulting path as `tle_file`
3. AI calls `generate_config_toml` to write `config.toml`
4. AI calls `generate_docker_compose` to create the container manifest
5. AI calls `load_scenario` → `init_scenario` → `start_simulation` to launch the emulation (or `prepare_simulation` for the one-shot load+init)
6. AI monitors progress with `get_emulator_status`; at the end of the timeline the run stops but the rules stay applied (`start_simulation` replays it), and `stop_simulation` / `reset_system` tears it down
