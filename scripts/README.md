# VSNES k3s Orchestration

All k3s operations go through a single script: `scripts/k3s.sh`

---

## Prerequisites

1. **VSNES containers running** (`docker-compose up -d`)
2. **WSL/Linux terminal** — all commands run inside the emulator's Linux environment
3. **From the repo root** — run as `./scripts/k3s.sh`
4. **PowerShell on Windows?** — prefix with `wsl -d Ubuntu-22.04 --`

---

## Quick Reference

```
./scripts/k3s.sh single start [MASTER]   Single-master cluster (default: SAT-1)
./scripts/k3s.sh single stop             Stop (preserves state)
./scripts/k3s.sh single clean            Stop + wipe all k3s state
./scripts/k3s.sh single status           Show nodes and pods

./scripts/k3s.sh uniq start              Independent single-node cluster on EACH SAT
./scripts/k3s.sh uniq stop               Stop every per-node cluster
./scripts/k3s.sh uniq clean              Stop + wipe all k3s state
./scripts/k3s.sh uniq status             Show each SAT's own cluster status

./scripts/k3s.sh ha start                HA cluster (3 masters: SAT-3, SAT-6, SAT-9)
./scripts/k3s.sh ha stop                 Stop (preserves etcd state)
./scripts/k3s.sh ha restart              Stop + start
./scripts/k3s.sh ha clean                Stop + wipe all k3s state
./scripts/k3s.sh ha status               Show nodes and pods

./scripts/k3s.sh olsr                    Start OLSRd on all nodes (+ wait convergence)
./scripts/k3s.sh olsr-status             Show OLSRd neighbour table on every node
./scripts/k3s.sh clean                   Wipe k3s state on ALL nodes
./scripts/k3s.sh status                  Auto-detect running cluster and show status
```

---

## Scenario 1: k3s Single-Master (No OLSRd)

**Use this when:** all satellites are fully connected (no topology gaps), you want a simple flat cluster.

```bash
# Start single-master cluster (SAT-1 as master, rest as workers)
./scripts/k3s.sh single start

# Or choose a different master
./scripts/k3s.sh single start SAT-2

# Verify
docker exec SAT-1 k3s kubectl get nodes -o wide

# Stop (preserves state)
./scripts/k3s.sh single stop

# Full reset
./scripts/k3s.sh clean
```

**What it does:** starts k3s on SAT-1 as master, joins all others as workers over the flat 172.27.12.0/24 bridge. No routing daemon needed since every node is directly reachable.

**Expected output:**
```
SAT-1:   Ready    master   172.27.12.101
SAT-2:   Ready    worker   172.27.12.102
...
SAT-12:  Ready    worker   172.27.12.112
```

---

## Scenario 1b: k3s Uniq — One Standalone Cluster per Satellite

**Use this when:** you want each satellite to be its **own** independent single-node Kubernetes cluster — no master/worker relationship, no shared etcd, no mesh dependency. Good for per-node workload testing, or N isolated clusters for experiments.

```bash
# Start an independent single-node cluster on every SAT (in parallel)
./scripts/k3s.sh uniq start

# Each SAT is its own cluster — query any one directly
docker exec SAT-5 k3s kubectl get nodes

# Compact status across all per-node clusters
./scripts/k3s.sh uniq status

# Stop them all (state preserved)
./scripts/k3s.sh uniq stop

# Full reset
./scripts/k3s.sh clean
```

**What it does:** runs `k3s-ctl single` on every node (node-ip pinned to its `172.27.x` address). There are **12 separate clusters**, each with one node that is its own control-plane. They do not know about each other and need no routing between them.

**`uniq status` output:**
```
=== Per-node cluster status (uniq: each SAT is its own cluster) ===
  SAT-1:  Ready (172.27.12.101)
  SAT-2:  Ready (172.27.12.102)
  ...
  SAT-12: Ready (172.27.12.112)
```

> Note: `uniq` and `single`/`ha` are mutually exclusive — they all use the same per-node k3s state. Switching between them needs a `clean` first.

---

## Scenario 2: k3s Single-Master + OLSRd Mesh

**Use this when:** the active satellite topology has LOS gaps — some workers can't reach the master directly.

```bash
# 1. Start OLSRd mesh on all nodes and wait for convergence (~30s)
./scripts/k3s.sh olsr

# 2. Check mesh is working (multi-hop routes should appear)
./scripts/k3s.sh olsr-status
docker exec SAT-4 ip route | grep "metric 2"

# 3. Start cluster
./scripts/k3s.sh single start

# Verify
docker exec SAT-1 k3s kubectl get nodes

# Stop
./scripts/k3s.sh single stop
```

**Why it works:** `k3s-ctl` inside each container detects the 172.27.x management address — the network OLSRd announces — so k3s control-plane and flannel traffic follow mesh routes. Workers multi-hop to the master via intermediate nodes even when there's no direct LOS.

---

## Scenario 3: k3s HA + OLSRd Mesh

**Use this when:** you need a resilient control plane. 3 etcd-backed masters survive individual master failures; multi-hop mesh handles LOS gaps.

```bash
# 1. Start mesh
./scripts/k3s.sh olsr

# 2. Start HA cluster
./scripts/k3s.sh ha start

# Verify all 12 nodes Ready
./scripts/k3s.sh ha status

# Stop (preserves etcd state)
./scripts/k3s.sh ha stop

# Restart without losing state
./scripts/k3s.sh ha restart

# Full reset (wipe etcd, fresh init on next start)
./scripts/k3s.sh ha clean
./scripts/k3s.sh ha start
```

**Master layout:**
| Node | IP | Role |
|------|----|------|
| SAT-3 | 172.27.12.103 | bootstrap master (etcd leader) |
| SAT-6 | 172.27.12.106 | secondary master |
| SAT-9 | 172.27.12.109 | tertiary master |
| rest | — | workers |

**etcd state detection:** `ha start` checks whether `/var/lib/rancher/k3s/server/db/etcd/member` exists on SAT-3. If it does, masters rejoin the existing cluster (no `--cluster-init`). If not, fresh `--cluster-init` is run.

---

## Manual Per-Node Control

All orchestration is thin wrappers around two in-container helpers.

### OLSRd (mesh routing)
```bash
docker exec SAT-N routing-ctl start olsrd    # start mesh daemon
docker exec SAT-N routing-ctl status         # daemons + ip route
docker exec SAT-N routing-ctl off            # stop all routing daemons
docker exec SAT-N curl -s http://127.0.0.1:2006/neighbours  # live neighbour table
```

### k3s
```bash
docker exec SAT-N k3s-ctl master                              # start as single master
docker exec SAT-N k3s-ctl distributed-master                  # HA master (cluster-init)
docker exec SAT-N k3s-ctl distributed-master 172.27.12.103    # HA master (join existing)
docker exec -e K3S_TOKEN="$TOKEN" SAT-N k3s-ctl worker IP     # join as worker
docker exec SAT-N k3s-ctl status                              # status + node list
docker exec SAT-N k3s-ctl stop                                # stop k3s (preserve state)
docker exec SAT-N k3s-ctl clean                               # stop + wipe state
```

---

## Troubleshooting

### Nodes stuck in `NotReady`
```bash
# 1. Check k3s is running
docker exec SAT-N k3s-ctl status

# 2. Check logs
docker exec SAT-N tail -50 /var/log/k3s.log

# 3. Check OLSRd has a route to the master
docker exec SAT-N ip route | grep 172.27.12.101

# 4. If no route: OLSRd may still be converging — wait ~30s
./scripts/k3s.sh olsr-status
```

### Can't reach master from a worker
```bash
# Direct LOS check
docker exec SAT-N ping -c 1 172.27.12.101

# Multi-hop route check
docker exec SAT-N routing-ctl status | grep 172.27.12.101
# If no route appears after 30s, check VSNES no-LOS iptables:
docker exec SAT-N iptables-legacy -L VSNES_OLSR -n
```

### HA cluster won't start (etcd corrupted)
```bash
./scripts/k3s.sh ha clean   # wipes etcd on all nodes
./scripts/k3s.sh ha start   # fresh cluster-init
```

### Check cluster from any node
```bash
./scripts/k3s.sh status     # auto-detects single or HA master
```

---

## Summary

| Goal | Command |
|------|---------|
| Flat k3s (no mesh) | `./scripts/k3s.sh single start` |
| One cluster per SAT (isolated) | `./scripts/k3s.sh uniq start` |
| k3s + OLSRd (single master) | `./scripts/k3s.sh olsr && ./scripts/k3s.sh single start` |
| k3s HA + OLSRd (3 masters) | `./scripts/k3s.sh olsr && ./scripts/k3s.sh ha start` |
| Stop everything | `./scripts/k3s.sh single stop` or `./scripts/k3s.sh ha stop` |
| Full wipe | `./scripts/k3s.sh clean` |
| Check cluster | `./scripts/k3s.sh status` |
| Check mesh | `./scripts/k3s.sh olsr-status` |

---

## Environment Variable Overrides

Passed to `docker exec -e VAR=value`:

| Variable | Default | Description |
|----------|---------|-------------|
| `K3S_TOKEN` | `vsnes-cluster-2026` | Shared cluster token |
| `K3S_NODE_IP` | auto-detected 172.27.x | Advertise/node IP for k3s |
| `K3S_IFACE` | `eth0` | Flannel interface |
| `K3S_DATA_DIR` | `/var/lib/rancher/k3s` | k3s data directory |

See [`docker/k3s-ctl.sh`](../docker/k3s-ctl.sh) for full details.

