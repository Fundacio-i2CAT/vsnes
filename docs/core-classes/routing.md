---
title: Routing (routing.py)
nav_order: 1
parent: Core classes
---

1. **`routing.py`**
   - **Purpose**: Registry of mesh routing protocols. Exactly one is active per scenario, selected with `[Routing] protocol = 'olsrd' | 'babel' | 'none'` in `config.toml` (`none` = netem shaping only, no daemon).
   - **Usage**:
     - `get_protocol(name)` returns the `RoutingProtocol` entry, `None` for `'none'`, and raises on unknown names so config errors surface at load time.
     - Each `RoutingProtocol` declares its firewall binary, dedicated chain (`VSNES_OLSR`, `VSNES_BABEL`), how out-of-LOS peers are dropped (`src_ip` for OLSR, `src_mac` for babel's IPv6 link-local hellos), the gated UDP port (698 / 6696), and the `routing-ctl` start/stop commands.
     - Its methods build the shell lines that set up/tear down the chain, add/remove per-peer DROP rules, and start/stop the daemon; `Channel.py` batches them into one `docker exec` per node.
     - To add a protocol, add one entry to `PROTOCOLS` (plus `routing-ctl` support in the node image) — see the module docstring, "Adding a routing protocol".
   - **Related Files**:
     - Used by `Scenario.py` (validates the protocol at load) and `Channel.py` (applies the gating and manages the daemon lifecycle).
