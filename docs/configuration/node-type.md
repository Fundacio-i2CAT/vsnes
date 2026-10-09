---
title: Node type
nav_order: 4
parent: Configuration
---

Every satellite and ground station carries one required **`type`** key — the single switch that decides how VSNES creates it, reaches it, and tears it down. There is no back-compat with older `isVM`/`is_external_vm`/`is_docker` flags; a config using them is rejected at `load-config` with a clear per-node error.

| `type` | Lifecycle | Reached via |
|---|---|---|
| `vm` | Internal libvirt VM: cloned from `clone_VM.name_VM` with `virt-clone` (machine-id reset before first boot so DHCP leases don't collide), started/resumed with `virsh` | SSH, for configuration only |
| `vm_external` | Never created/destroyed by VSNES — must already be running | SSH; init fails fast (~seconds, not a blind multi-minute retry) if unreachable |
| `container` | Local Docker container: VSNES generates `docker-compose.yml` and brings up exactly the missing services (`--no-recreate --no-build` — a live cluster inside is never disturbed) | `docker exec` |
| `container_external` | A container on another host — never created/removed by VSNES | validated over the network like `vm_external` |

Required keys per type:
- **`ip_ext`**: required for every type except `vm` (internal VMs get their address from `virsh domifaddr`).
- **`clone_VM.name_VM`**: required only for `type = 'vm'` — the base libvirt domain to clone.
- **`interface`**: always required — the node's NIC (`eth0` for containers, the VM's real NIC name, e.g. `enp1s0`, for VMs).

Mixed scenarios are supported (e.g. a container constellation with one `vm_external` ground station) — VSNES configures each node type appropriately in the same run, including data-plane shaping (netem) across both the Docker/IFB path and the classic VLAN+vxlan path.
