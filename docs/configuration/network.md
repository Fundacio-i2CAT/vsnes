---
title: Network
nav_order: 1
parent: Configuration
---

- **`network`**: Specifies the subnet for the emulated network (in CIDR notation) — the flat `10.0.0.x`-style address every node gets as its per-scenario emulated IP.
- **`network_ext`**: Specifies the subnet of the network that hosts the nodes' management/external addresses (`ip_ext`, in CIDR notation) — the Docker bridge or host-reachable network for classic-VM/external nodes.
- **`unicast_flooding`**: If `1`, the virtual switch of brSATEMU will not logically map MAC addresses with ports. This means that all the traffic received from one port will be broadcasted to all the other ports. If `0`, the virtual switch will map MAC addresses and forward traffic only to the correct destination port.
- **`host_interface`** *(optional)*: The host NIC used for classic-VM vxlan tunnels. Auto-detected (first non-loopback, non-libvirt interface) if omitted.
