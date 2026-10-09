---
title: Home
nav_order: 1
---

[![Maintenance](https://img.shields.io/badge/Status-Maintained-green.svg)]()
[![made-with-python](https://img.shields.io/badge/Made%20with-Python-blue)](https://www.python.org/)
[![AGPLv3 license](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0.en.html)


# Virtual Satellite Network Emulator System (VSNES)

The Virtual Satellite Network Emulator System (VSNES) is a Python-based tool designed to simulate satellite networks, including satellite orbits, ground stations, and communication channels. It provides tools for visualizing scenarios in Cesium, managing virtual machines (VMs) and containers for emulation, and propagating satellite orbits using TLE data. VSNES can be integrated into AI workflows by exposing a [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server, enabling AI agents such as Claude to autonomously configure, launch, and monitor satellite network emulations.

<iframe allowfullscreen src="{{ site.baseurl }}/assets/cesium/demo.html"
        width="100%" height="650" style="border:1px solid #ccc" loading="lazy"
        title="VSNES Cesium static demo"></iframe>
        
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

## Where to start

- [Installation]({{ site.baseurl }}/installation/)
- [Usage]({{ site.baseurl }}/usage/) — CLI, REST API and MCP workflows
- [Components]({{ site.baseurl }}/components/) — API server, MCP server, NTP, dashboard
- [Configuration]({{ site.baseurl }}/configuration/) — the `config.toml` reference
- [Core classes]({{ site.baseurl }}/core-classes/) — Python modules, routing registry, TLE generator

---

### Source

Developed within i2-22-RDI-IoT A2 DSS Sim.
Aquest projecte ha rebut finançament per part del Govern de la Generalitat de Catalunya dins del marc de l'estrategia [NewSpace](https://www.accio.gencat.cat/ca/serveis/banc-coneixement/cercador/BancConeixement/new_space_a_catalunya) a Catalunya.

### Copyright

Developed by Fundació Privada Internet i Innovació Digital a Catalunya (i2CAT).
Find more information at https://i2cat.net/tech-transfer/

### Licence

Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE. See https://www.gnu.org/licenses/agpl-3.0.en.html.

For licensing enquiries: techtransfer@i2cat.net
