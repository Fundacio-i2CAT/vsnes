---
title: Routing protocol
nav_order: 2
parent: Configuration
---

```toml
[Routing]
	protocol = 'olsrd'   # olsrd | babel | none
```

Selects which mesh routing daemon VSNES gates and manages inside every container node. Only ONE protocol's firewall rules and daemon are ever installed — switching protocols (or to `none`) between runs always converges cleanly, even without a clean stop first. `none` applies netem channel shaping only, with no routing daemon and no per-pair firewall gating. Missing the `[Routing]` section defaults to `none` (with a warning).

Protocols are a small registry in `Class/routing.py` — see the module docstring ("Adding a routing protocol") to add one (e.g. an experimental QUIC/DTN router): each entry declares its firewall binary/chain/gating-port and daemon start/stop commands, and Channel.py drives any entry generically.
