---
title: Notes
nav_order: 7
parent: Configuration
---

- Ensure that the TLE file specified in the `SpaceSegment` section exists and contains valid TLE data. `sample.tle` contains a sample TLE file. To build a synthetic single-plane constellation, use `python3 Class/tle_generator.py <N> <output.tle>` (see `Class/README.md`) or the MCP `generate_tle` tool.
- The `clone_VM` section is only required for `type = 'vm'` nodes.
- The `Channels` section allows you to define multiple communication links between nodes.
- libvirt implements DHCP, so if you want to avoid modifying the configuration of each VM to allocate a static IP:
  - Get the MAC address of the VM: `$ virsh domiflist <VM_name>`
  - Apply the DHCP rule: `$ virsh net-edit default`
  ```xml
  <dhcp>
  ...
  <host mac="<VM_MAC>" name="VM_name" ip="<VM_static_IP>"/>
  ```
  - Restart the network, in this example `default`: `$ virsh net-destroy default` and `$ virsh net-start default`
  - Reboot the VM: `$ virsh shutdown <VM_name>` and `$ virsh start <VM_name>`
- Be careful if a kernel-level VPN is up in the host, as it will affect the routing table and make VMs not reachable. In that case, consider disabling the VPN.
