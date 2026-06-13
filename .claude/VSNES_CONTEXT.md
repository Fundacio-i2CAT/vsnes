# VSNES Context — Architecture, Delay Matrix, and tc/netem Injection

> Written 2026-06-13. Updated 2026-06-18 (Docker shaping now filters by L2
> dst-MAC for OLSRd multi-hop; added OLSR topology sync, mesh/k3s, and scope
> limitations). For future sessions that need to understand how VSNES simulates
> and emulates a satellite network.

---

## 1. High-Level Architecture

```
config.toml  ──►  Scenario  ──►  Channel  ──►  tc/netem (Linux kernel)
                     │                │
                   Satellite       delay matrix N×N
                   GroundStation   precomputed timeline _delays[T][N][N]
```

- **`Scenario`** (`Class/Scenario.py`) loads the TOML config, creates Satellite and GroundStation objects, owns the simulation loop.
- **`Channel`** (`Class/Channel.py`) owns the N×N delay matrix and applies it to the network stack via `tc`.
- **`Satellite`** uses TLE + skyfield to compute ECI/ECEF positions at every time step.
- **`GroundStation`** has a fixed ECEF position + lat/lon/alt.

### Simulation loop (`Scenario._run`)

1. `write_bash()` generates `runtime_bash.sh` / `shutdown_bash.sh` and the four batch files.
2. `runtime_bash.sh` runs once: sets up IFB devices and the full HTB+netem tree.
3. Every tick (`time_parameters.get_TimeInterval()` seconds of sim time):
   - `scenario.step(EMU=True)` → `channel.update(…, EMU=True)`
   - `channel.update()` diffs old vs new matrix → emits only changed `tc` lines → `tc -force -batch`
   - Sleeps the remainder of the wall-clock interval, adjusted by playback speed.

---

## 2. Delay Matrix

### Structure

```python
self._delay_matrix  # list-of-lists N×N, live state
self._delays        # numpy array (T, N, N), precomputed at load time
```

`_delays` is built once by `channel.precompute()` after all nodes are loaded.
During emulation `channel.update()` reads `_delays[marker][n][j]` directly (no
recalculation per tick).

### Sentinel values

| Value | Meaning                                         | tc effect               |
|-------|-------------------------------------------------|-------------------------|
| `-2`  | Pair not defined in config (diagonal + unknowns)| Skipped entirely — no tc class is changed |
| `-1`  | Defined pair but no LOS / out of range          | `netem loss 100%`       |
| `0`   | Defined, in range, but Latency=False            | `netem delay 0ms ...`   |
| `>0`  | Propagation delay in milliseconds               | `netem delay Xms loss P% C%` |

---

## 3. Delay Calculation

### Constants

```python
a_Earth  = 6371000.0        # Earth radius [m]
c        = 3e8              # Speed of light [m/s]
C_INV_MS = 1000.0 / c      # = 3.3356e-6  ms/m  (precomputed)
```

### Satellite-to-Satellite (`_Satellite2Satellite`)

Uses ECI (Earth-Centred Inertial) positions.

```
theta = arcsin(a_Earth / |ECI1|)   ← half-angle of Earth's obstruction cone
diff_vec  = ECI1 - ECI2
diff_norm = |diff_vec|
diff_angle = arccos(|dot(diff_vec_unit, ECI1_unit)|)
```

Decision logic:

```
if diff_angle > theta AND diff_norm < threshold:
    # Clear LOS — not blocked by Earth, within range
    delay = diff_norm * C_INV_MS

elif diff_norm < threshold:
    # Within range but angle check failed — secondary check
    distance_tangent = |ECI1| * cos(theta)
    if diff_norm <= distance_tangent:
        delay = diff_norm * C_INV_MS  # still LOS (satellite above horizon)
    else:
        delay = -1  # Earth-blocked

else:
    delay = -1  # out of threshold range
```

### Ground Station to Satellite (`_GroundBase2Satellite`)

Uses ECEF positions and elevation angle.

```
p   = ECEF_SAT - ECEF_GS          # vector GS→SAT in ECEF
NED = ECEF2NED(p, LLH_GS)         # rotate to North-East-Down frame
beta = arcsin(-NED[D] / |NED|)    # elevation angle above horizon (degrees)

if beta >= Min_elevation_angle AND |p| < threshold:
    delay = |p| * C_INV_MS   (or 0 if Latency=False)
else:
    delay = -1
```

### Ground-to-Ground

Always returns `0` — no delay modelled between ground stations.

### Vectorized variants

`_Satellite2Satellite_vec` and `_GroundBase2Satellite_vec` operate on the full
`(T, 3)` position arrays (numpy broadcast) to build `_delays` in one pass at
load time instead of looping over T steps.

---

## 4. tc/netem Injection — Docker IFB Mode

This is the mode used when satellites run as Docker containers (detected via
`node._is_docker_container()`).

### Setup (runs once via `runtime_bash.sh`)

```
Container (SAT-N)  — outgoing traffic
    veth_host (host side of container's veth pair)
         │  ingress qdisc ffff: + u32 mirred redirect
         │  (veth_host ingress = the container's OUTGOING/egress traffic)
         ▼
    ifb{n}   (IFB = Intermediate Functional Block — a virtual device)
         │  HTB root qdisc  1:
         ├── class 1:1  htb rate R mbit  → netem 1{1}: delay Xms loss P% C%
         ├── class 1:2  htb rate R mbit  → netem 1{2}: delay Xms loss P% C%
         │    …
         └── class 1:N  htb rate R mbit  → netem 1{N}: delay Xms loss P% C%
              flower filters: dst MAC (L2 next-hop) → classid 1:j
```

Key commands emitted by `write_bash()`:

```sh
# Create IFB and redirect container ingress into it
ip link add ifb{n} type ifb
ip link set dev ifb{n} up
tc qdisc add dev veth_host ingress handle ffff:
tc filter add dev veth_host parent ffff: protocol all u32 match u32 0 0 \
    action mirred egress redirect dev ifb{n}

# HTB root on IFB
tc qdisc add dev ifb{n} root handle 1: htb

# Per-destination class j:
tc class add dev ifb{n} parent 1: classid 1:{j} htb rate {rate}mbit
tc qdisc add dev ifb{n} parent 1:{j} handle 1{j}: netem delay {delay}ms loss {P}% {C}%

# Filter: Ethernet destination MAC (L2 next-hop) → class
tc filter add dev ifb{n} parent 1:0 protocol all prio 1 \
    flower dst_mac {peer_mac} classid 1:{j}
```

One MAC filter per peer replaces the old two-per-peer u32 dst-IP filters; it
covers both the 172.27.x management IP and the 10.0.0.x emulated IP (same eth0
MAC). Non-Docker fallback still uses `u32 match ip dst` (see `write_bash` Phase 2).

**Why IFB?** Docker containers attach to a shared bridge via veth pairs; there
is no per-node VLAN to shape on (contrast §5). The host-side veth's *ingress* is
the container's *outgoing* traffic — but an ingress qdisc can't do classful
HTB+netem. So the veth ingress is `mirred`-redirected into a per-container IFB,
where a normal egress-style HTB+netem tree applies. The IFB `ifb{n}` is the
Docker equivalent of the VM's VLAN sub-interface `eth0.N`.

**Why dst-MAC, not dst-IP? (multi-hop fix, 2026-06-18)** The containers run
OLSRd and route multi-hop over the flat /24 mesh. Filtering by the packet's
final *destination IP* breaks this: a packet SAT-4→SAT-1 routed `via SAT-3`
still carries IP dst = SAT-1, so it hit SAT-1's `loss 100%` (no-LOS) class and
was dropped at the sender. Filtering by the frame's *destination MAC* (the L2
next-hop) instead means a multi-hop packet carries the intermediate node's MAC
→ lands in that hop's per-link delay class. No-LOS enforcement is preserved
because OLSRd only forms adjacencies over LOS links, so every routed hop's
next-hop is a LOS neighbour; direct emulated-IP traffic to a no-LOS peer still
resolves to that peer's MAC → `loss 100%`. `get_docker_mac()` (Node.py) reads
each container's eth0 MAC at setup.

### Per-tick update (`channel.update` → `_batch_update_netem`)

Only pairs where the delay value changed emit a command:

```sh
# No LOS / node killed:
qdisc change dev ifb{n} parent 1:{j} handle 1{j}: netem loss 100%

# LOS with propagation delay:
qdisc change dev ifb{n} parent 1:{j} handle 1{j}: netem delay {X}ms loss {P}% {C}%
```

All changed lines are written to `/tmp/batch_tc_update.txt` and applied in a
single `sudo tc -force -batch` call. `-force` means a single bad line does not
abort the remaining commands.

### Kill node feature

```python
channel.kill_node("SAT-3")   # adds "SAT-3" to _killed set
```

In `channel.update()`, any pair where either endpoint is in `_killed` has its
delay forced to `-1` before the diff check. This triggers `netem loss 100%` on
the kill tick. `revive_node()` removes from the set and restores real delays.

### OLSR topology sync (container mesh)

When containers run OLSRd, netem `loss 100%` alone is not enough to hide a
no-LOS neighbour: OLSRd HELLO is a broadcast and would still be heard. So VSNES
also blocks HELLO per no-LOS pair with iptables **inside each container**:

- `init_olsr_rules()` (Channel.py, called by `write_bash`) creates a dedicated
  `VSNES_OLSR` chain in every container (jumped from INPUT for UDP/698 only) and
  adds `-s <peer_ip> -j DROP` rules for every initially no-LOS pair.
- Must use **`iptables-legacy`** inside Debian-12 containers (the default nft
  backend conflicts with Docker's own nftables). Constant `OLSR_IPTABLES`.
- Each tick, `update()` collects `_sync_olsr_pair()` commands and only toggles a
  DROP when a pair crosses the LOS↔no-LOS boundary (mirrors the netem diff).
- A background `docker events` watcher thread (`_start_olsr_event_watcher`)
  re-applies a container's chain + current blocks within ~2s of any restart
  (WSL2 network resets bounce `unless-stopped` containers and wipe iptables).
- `cleanup_olsr_rules()` flushes and removes the chains on shutdown.

Net effect: OLSRd discovers only in-range neighbours, computes multi-hop routes
over the LOS graph, and the dst-MAC netem (above) shapes each hop correctly.

---

## 5. tc/netem Injection — Classic VM Mode (VLAN + iptables MARK)

Used for real or libvirt VMs (not Docker containers).

```
host bridge (brSATEMU)
    eth0.N  (VLAN subinterface, VLAN id = N)
        │   HTB root 1:
        ├── class 1:1 → netem (delay or 100% loss)
        │    …
        └── class 1:N → netem
    iptables PREROUTING mangle: physdev-in eth0.N → MARK N
    tc filter: handle N fw → flowid 1:j
```

`iptables MARK` identifies the source node; `tc fw` filter matches the mark to
pick the correct HTB class.

---

## 6. Batch Files Generated by `write_bash()`

| File               | Content                                    | Executed by         |
|--------------------|--------------------------------------------|---------------------|
| `ip_setup.batch`   | `ip link add/set` for IFB devices         | `ip -force -batch`  |
| `tc_setup.batch`   | Full HTB + netem + filter tree            | `tc -force -batch`  |
| `tc_teardown.batch`| `tc qdisc del` for ingress qdiscs         | `tc -force -batch`  |
| `ip_teardown.batch`| `ip link del` for IFB devices             | `ip -force -batch`  |

---

## 7. TOML Config Keys Relevant to Channels

```toml
[[Channels.Channel]]
Node1 = "SAT"            # group name of node 1
Node2 = "GS"             # group name of node 2
Threshold = 2000000      # max range [m] — beyond this → -1 (no contact)
Data_rate = 100.0        # HTB class rate [Mbit/s]
Packet_loss = 0.1        # netem base loss [%]
Correlated_losses = 25   # netem correlated loss [%]
Latency = "True"         # "False" → delay=0, LOS check still applies
Min_elevation_angle = 5  # GS-to-sat only: minimum elevation [deg]
```

Channel matching uses `frozenset({node1.group, node2.group})` so order does
not matter and the lookup is O(1).

---

## 8. Node Position Files

Every tick `channel._write_positions()` writes `Positions/nodes.json` with
current lat/lon/alt + ECEF for each node. A web server (served by VSNES) makes
this available to nodes at runtime (e.g. for neighbour-aware routing).

---

## 9. CZML (Cesium Visualization)

`Scenario.write_czml()` generates `Class/templates/ScenarioCZML.czml`:
- One packet per node (orbit path as sampled ECEF positions).
- One polyline packet per defined channel pair, with `show` intervals covering
  only the periods when the link has LOS.
- The document (clock) packet is rewritten every tick during emulation to
  advance `currentTime` in the Cesium viewer.

Atomic write: the file is written to a `.tmp` first, then `os.replace()` to
avoid the Cesium viewer reading a half-written file.

---

## 10. Key File Locations

| Path                                    | Purpose                                   |
|-----------------------------------------|-------------------------------------------|
| `Class/Channel.py`                      | Delay matrix + tc injection + OLSR sync   |
| `Class/Scenario.py`                     | Orchestration, loop, bash generation      |
| `Class/Node.py`                         | Base node; veth/MAC/IP discovery helpers  |
| `Class/Satellite.py`                    | TLE propagation, ECI/ECEF/LLH             |
| `Class/Ground_Station.py`               | Fixed ground node                         |
| `config.toml`                           | Main simulation config                    |
| `ip_setup.batch` / `tc_setup.batch`     | Generated at scenario start (gitignored)  |
| `/tmp/batch_tc_update.txt`              | Per-tick tc batch (overwritten each tick) |
| `Positions/nodes.json`                  | Live node positions (per tick)            |
| `Class/templates/ScenarioCZML.czml`     | Cesium visualization document             |
| `simulation_time.txt`                   | Current sim time (for external tools)     |
| `docker/Dockerfile`                     | Satellite image (olsrd+babeld+k3s)        |
| `docker/k3s-ctl.sh`                     | In-container per-node k3s role control    |
| `docker/routing-ctl.sh` / `olsrd.conf`  | Mesh routing daemon control + config      |
| `docker/registries.yaml`                | k3s mirror → vsnes-registry (172.27.12.200)|
| `scripts/k3s-single.sh` / `k3s-ha.sh`   | Host orchestrators (single-master / HA)   |
| `scripts/populate-registry.sh`          | Seed the registry with k3s + nginx images |

---

## 11. Mesh + k3s (container scenarios)

The satellite image bakes in OLSRd (compiled from source) + babeld + k3s
v1.31.4. A PID-1 supervisor (`entrypoint.sh`) launches k3s as its own child via
SIGUSR1/USR2 so it survives `docker exec` exits.

- **Routing**: OLSRd/babeld run on `eth0` over the flat `172.27.12.0/24` bridge;
  VSNES's per-pair iptables (§4) gate which neighbours each node can hear, so the
  daemons compute multi-hop routes that match the simulated LOS topology.
- **k3s node-ip**: `k3s-ctl detect_ip()` uses the **172.27.x management IP**, not
  the 10.0.0.x emulated address. OLSRd only routes 172.27.x; 10.0.0.x is a flat
  /24 with no mesh routing (and no-LOS pairs drop it), so a multi-hop worker on
  10.0.0.x would lose the master. Flannel/control-plane traffic rides 172.27.x.
- **Images**: after `k3s-ctl clean` (wipes each node's containerd cache) all
  images must come from `vsnes-registry` at `172.27.12.200:5000`; populate it
  first. The registry is infra (not a satellite) — outside the mesh and the tc
  filter set, reached directly on the bridge. Deploy with an explicit tag that
  the registry holds (e.g. `nginx:alpine`, not `nginx:latest`).

---

## 12. Scope & Limitations

- **Docker shaping is host-local.** `get_docker_veth()`/`get_docker_mac()`/
  `_is_docker_container()` and all `tc`/`docker exec` calls target the **local**
  daemon and the host's own veth/IFB. A container on **another machine** is not
  shaped (its veth/tc live on that host). No `DOCKER_HOST`/ssh remoting exists.
- **Remote VMs do work** via VXLAN: `is_external_vm=1` nodes get a
  `vxlan ... remote <ip_ext>` tunnel onto the central `brSATEMU` bridge and are
  shaped centrally (§5). This is the only built-in "another machine" mechanism.
- **VM and container data planes are separate.** `write_bash()` runs both blocks
  in one scenario (delays are computed for every pair), but containers live on
  the Docker bridge and VMs on `brSATEMU` — two L2 segments with no glue. So
  VM↔container links are *computed but not connected*; within-type links
  (VM↔VM, container↔container) work. Bridging the two would need extra wiring.
- **The OLSRd mesh spans containers only**; VMs are not mesh members.
