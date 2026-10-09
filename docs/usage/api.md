---
title: API mode
nav_order: 2
parent: Usage
---

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
