<img src="https://wikifab.org/images/b/b6/Group-i2CAT_logo-color-alta.jpg" width=25% height=25%>

[![Maintenance](https://img.shields.io/badge/Status-Maintained-green.svg)]()
[![made-with-python](https://img.shields.io/badge/Made%20with-Python-blue)](https://www.python.org/)
[![GPLv2 license](https://img.shields.io/badge/License-GPLv2-blue.svg)](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html)


# Virtual Satellite Network Emulator (vsnes)

vsnes is a Python-based emulator for satellite networks. It reads a scenario from a TOML configuration file, propagates satellite orbits in real time, and shapes traffic between nodes using Linux `tc netem` rules running inside QEMU/libvirt virtual machines. An optional CesiumJS visualization shows satellite positions and link states in a browser.

## Architecture

```
SatelliteEmulator.py       ← entry point / interactive CLI
└── Class/
    ├── Scenario.py        ← loads config, manages nodes and channels, drives emulation loop
    ├── Node.py            ← base class: VM lifecycle (clone/start/delete), SSH config, VLAN setup
    ├── Satellite.py       ← extends Node; holds orbit, ECI/ECEF position vectors
    ├── Ground_Station.py  ← extends Node; fixed geodetic position
    ├── Orbit.py           ← base orbit class
    ├── SGP4.py            ← SGP4 orbit propagator (wraps skyfield)
    ├── TwoBody.py         ← simplified two-body propagator
    ├── Channel.py         ← delay/LoS matrix; updates tc netem rules live
    ├── channel_threshold.py
    ├── Time_parameters.py ← simulation clock, time stepping, speed multipliers
    └── Server.py          ← Flask server serving CesiumJS visualization
```

### How it works

1. **Load scenario** — `Scenario` reads the TOML file, instantiates `Satellite` and `GroundStation` nodes, and builds a delay matrix via `Channel`.
2. **Orbit propagation** — each `Satellite` pre-computes ECI/ECEF position vectors for every time step using SGP4 or a Two-Body model.
3. **Channel computation** — `Channel` calculates propagation delay (distance / *c*) for every node pair. Satellite-to-satellite uses ECI coordinates with Earth-occlusion check; ground-to-satellite uses ECEF + NED frame elevation-angle check.
4. **VM emulation** — each node maps to a libvirt VM cloned from a base image. The host creates one VLAN per node on a shared bridge (`brSATEMU`). `tc htb + netem` rules enforce per-pair data rate, delay, packet loss, and burst loss.
5. **Live update** — the emulation loop steps through time, recomputes delays, and updates `tc netem` rules on the fly via SSH.
6. **Visualization** — an optional Flask + CesiumJS server reads a CZML file to animate satellite orbits and link state in the browser at `http://localhost:5000/`.

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.8+ | Tested with CPython 3.8 |
| QEMU + libvirt | `qemu-system`, `libvirt-daemon-system` |
| `virt-clone` | Part of `virtinst` / `virt-manager` |
| `bridge-utils` | `brctl` for bridge setup |
| `sshpass` | Passwordless SSH to VMs |
| Base VM images | Ubuntu 20.04 and/or Alpine images registered in libvirt |

Python packages: `skyfield`, `toml`, `czml`, `flask`, `julian`, `astropy`, `paramiko`, `sgp4`, `numpy`

## Install

Run the provided install script (requires `sudo`):

```bash
chmod +x install.sh
./install.sh
```

This installs system packages (`qemu`, `libvirt`, `virt-manager`, `bridge-utils`, `sshpass`, `pip`) and Python packages (`skyfield`, `toml`, `czml`, `flask`, `julian`, `astropy`), then starts the libvirt default network.

To install Python dependencies manually:

```bash
pip install skyfield toml czml flask julian astropy paramiko sgp4 numpy
```

## Configuration

Scenarios are defined in TOML files. See `test.toml` for a minimal example and `config.toml` for a full multi-constellation example.

```toml
network = '10.0.0.0/24'       # IP pool for node VMs

[Time]
  TimeInterval   = 0.5        # simulation step [min]
  Contact_speed  = 5          # clock speed multiplier when links exist
  Non_contact_speed = 60      # clock speed multiplier when no links exist
  start_datetime = '2022-04-13 07:31:31'
  end_datetime   = '2022-04-13 07:32:30'

[SpaceSegment]
  [[SpaceSegment.SatelliteSistem]]
    TLE        = 'test.tle'   # path to TLE file (one or more satellites)
    propagator = 'SGP4'       # 'SGP4' or 'TwoBody'
    group      = 'IntelSat'   # group name referenced in Channels
    Service    = 'Standard'   # 'Standard' or 'Relay'
    [SpaceSegment.SatelliteSistem.clone_VM]
      name_VM   = 'ubuntu20.04'
      OS        = 'ubuntu'    # 'ubuntu' or 'alpine'
      username  = 'ubuntu'
      password  = 'ubuntu'
      interface = 'enp1s0'

[GroundSegment]
  [[GroundSegment.GroundSistem]]
    name      = 'i2cat'
    group     = 'i2cat'
    latitude  = 41.387
    longitude = 2.112
    height    = 150           # [m]
    [GroundSegment.GroundSistem.clone_VM]
      name_VM   = 'ubuntu20.04'
      OS        = 'ubuntu'
      username  = 'ubuntu'
      password  = 'ubuntu'
      interface = 'enp1s0'

[Channels]
  [[Channels.Channel]]
    Node1               = 'IntelSat'  # group names from Space/GroundSegment
    Node2               = 'i2cat'
    Min_elevation_angle = 5           # minimum elevation angle [deg]
    Threshold           = 10e6        # maximum range [m]
    Data_rate           = 100         # [Mbit/s]
    Packet_loss         = 0           # [%]
    Correlated_losses   = 0           # burst loss correlation [%]
```

TLE files use standard two-line element format. Multiple satellites in one file are all added to the same constellation group.

## Build & Execute

No compilation step is required. Run directly with Python 3.

### 1. Start the emulator

```bash
python3 SatelliteEmulator.py
```

You are prompted for a config file name (press Enter to use `config.toml`).

### 2. Interactive commands

Once loaded, the emulator accepts the following commands:

| Command | Description |
|---|---|
| `help` | List all commands |
| `scenario` | Print loaded nodes and types |
| `start_VMs` | Clone and start a VM for every node |
| `write_czml` | Generate the CesiumJS visualization file |
| `run_all` | Start emulation + open Cesium in browser |
| `run_emulator` | Start emulation only (no visualization) |
| `run_CESIUM` | Start Cesium only (no emulation) |
| `delete_VM` | Delete a specific VM or all VMs |
| `ssh_connection` | Open SSH terminal to a node's VM |
| `exit` | Shut down VMs and quit |

### 3. Typical workflow

```bash
# 1. install dependencies (once)
./install.sh

# 2. prepare base VM images in libvirt (ubuntu20.04, alpine)

# 3. run with the test scenario
python3 SatelliteEmulator.py
# > Insert config file: test.toml
# > start_VMs          (waits for VMs to boot and configures VLANs)
# > write_czml         (generates Cesium orbit data)
# > run_all            (starts emulation and opens browser at http://localhost:5000/)
# > exit               (shuts down VMs)
```

### Running without VMs (orbit/delay inspection only)

Load the scenario and use `scenario` or `write_czml` without calling `start_VMs`. The delay matrix and CZML visualization work without running VMs.

## Source

Developed within i2-22-RDI-IoT A2 DSS Sim.
Aquest projecte ha rebut finançament per part del Govern de la Generalitat de Catalunya dins del marc de l'estrategia [NewSpace](https://www.accio.gencat.cat/ca/serveis/banc-coneixement/cercador/BancConeixement/new_space_a_catalunya) a Catalunya.

## Copyright

Developed by Fundació Privada Internet i Innovació Digital a Catalunya (i2CAT).
Find more information at https://i2cat.net/tech-transfer/

## Licence

Licensed under the GNU AFFERO GENERAL PUBLIC LICENSE. See https://www.gnu.org/licenses/agpl-3.0.en.html.

For licensing enquiries: techtransfer@i2cat.net
