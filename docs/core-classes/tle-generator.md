---
title: TLE generator
nav_order: 2
parent: Core classes
---

1. **`tle_generator.py`**
   - **Purpose**: Generates a TLE file for N satellites in one orbital plane — a full evenly spaced ring by default, or a tight arc with `--spacing-deg` so all satellites stay in line of sight of each other.
   - **Usage**:
     - Satellites are named `<prefix><n>` (default `SATELLITE-1..N`) so they match the satellite names in `config.toml`. Defaults reproduce the walker66 orbit (86.4° inclination, 14.35663288 rev/day).
     - CLI: `python3 Class/tle_generator.py 5 test/configs/plane5.tle` — options `--prefix`, `--first-index`, `--inclination`, `--raan`, `--altitude-km` (overrides `--mean-motion`), `--mean-motion`, `--phase-offset`, `--spacing-deg`, `--epoch`, `--overwrite`.
     - Python: `generate_tle_text(...)` returns the TLE text; `write_tle(path, ...)` writes it (refuses to overwrite unless `overwrite=True`).
   - **Related Files**:
     - Backs the `generate_tle` tool in `mcpServer.py`.
