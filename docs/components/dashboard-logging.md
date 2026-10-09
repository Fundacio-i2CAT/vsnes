---
title: Web dashboard & logging
nav_order: 5
parent: Components
---

A new browser-based control panel is served by the Cesium visualization server (`Class/static/`). It includes a custom design system with Orbitron and Lato fonts, icon set, and a responsive layout. The frontend communicates with the REST API to load configs, manage VMs, and control the simulation without using the CLI.

---

### Structured Logging
All server components write structured logs to `/tmp/log/snes.log` with timestamps and severity levels, in addition to console output.
