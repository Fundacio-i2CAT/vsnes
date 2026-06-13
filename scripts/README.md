# VSNES k3s Orchestration Scripts

This directory contains scripts to manage k3s Kubernetes clusters on VSNES satellites — with and without mesh routing (OLSRd). Choose your scenario based on whether you need multi-hop routing or a flat, fully-connected network.

---

## Prerequisites

1. **VSNES containers running** (12 SAT containers started via `docker-compose up`)
2. **In WSL/Linux terminal** — all commands run inside the emulator's Linux environment
3. **From the vsnes repo root** — run scripts as `./scripts/<script.sh>`
4. **PowerShell on Windows?** — prefix each command with `wsl -d Ubuntu-22.04 --` to enter WSL first

---

## Scenario 1: k3s Single-Master (No OLSRd)

**Use this when:** satellites are fully connected (no topology gaps), you want a simple flat cluster.

```bash
# Start single-master cluster
./scripts/k3s-single.sh start

# Verify cluster is Ready
docker exec SAT-1 k3s kubectl get nodes -o wide

# View logs
docker exec SAT-1 tail -f /var/log/k3s.log

# Stop cluster (preserves state)
./scripts/k3s-single.sh stop

# Full reset (wipe all k3s state, ready for fresh start)
for i in $(seq 1 12); do docker exec SAT-$i k3s-ctl clean; done
```

**What it does:**
- Ensures OLSRd is OFF on all nodes (no mesh)
- Starts master on SAT-1 (172.27.12.101)
- Joins SAT-2 through SAT-12 as workers
- All use the flat 172.27.12.0/24 bridge; no multi-hop routing

**Expected output:**
```
SAT-1:   Ready    master        172.27.12.101
SAT-2:   Ready    worker        172.27.12.102
...
SAT-12:  Ready    worker        172.27.12.112
```

---

## Scenario 2: k3s with OLSRd (Single-Master + Mesh)

**Use this when:** satellites have line-of-sight (LOS) topology gaps, you need multi-hop routing to reach distant workers.

```bash
# Start cluster WITH OLSRd mesh routing
./scripts/k3s-single.sh start

# This script:
#   1. Starts OLSRd on all nodes
#   2. Waits ~30s for mesh to converge
#   3. Starts k3s master on SAT-1
#   4. Joins all workers
#   5. Multi-hop workers reach the master via intermediate nodes

# Verify cluster is Ready
docker exec SAT-1 k3s kubectl get nodes

# Check mesh convergence (multi-hop routes)
docker exec SAT-4 ip route | grep "metric 2"  # 2-hop routes visible after ~30s
docker exec SAT-1 routing-ctl status

# Test multi-hop connectivity (e.g., SAT-4 → SAT-1 via SAT-3)
docker exec SAT-4 ping -c 3 172.27.12.101

# Stop cluster
./scripts/k3s-single.sh stop

# Full reset
for i in $(seq 1 12); do docker exec SAT-$i k3s-ctl clean; done
```

**Why OLSRd?**
- On a simulated satellite constellation, not all nodes are LOS to all others
- OLSRd discovers neighbors and computes multi-hop routes around LOS gaps
- k3s control-plane uses the 172.27.x mesh address (detected by `k3s-ctl detect_ip()`)
- Workers that can't reach the master directly (no LOS) still work via routed hops

**Key point:** the cluster works because k3s uses the **OLSRd-routed 172.27.x network**, not the flat 10.0.0.x emulated IPs.

---

## Scenario 3: k3s HA (High Availability) with OLSRd

**Use this when:** you need a resilient control plane (3 masters, 9 workers), all over multi-hop mesh.

```bash
# Start HA cluster (3 masters, 9 workers, all on OLSRd mesh)
./scripts/k3s-ha.sh start

# What it does:
#   1. Ensures OLSRd is running on all nodes
#   2. Initializes SAT-3, SAT-6, SAT-9 as etcd-backed masters (cluster-init)
#   3. Joins remaining masters to the cluster
#   4. Joins SAT-1,2,4,5,7,8,10,11,12 as workers
#   5. Waits for all nodes to register

# Verify cluster status (all 12 nodes Ready)
./scripts/k3s-ha.sh status

# Or manually from a master
docker exec SAT-3 k3s kubectl get nodes -o wide

# View HA master layout
docker exec SAT-3 k3s kubectl get nodes -L kubernetes.io/hostname

# Stop HA cluster (preserves state in etcd)
./scripts/k3s-ha.sh stop

# Restart (rejoins existing etcd cluster without re-init)
./scripts/k3s-ha.sh start

# Full reset (wipe etcd, fresh cluster on next start)
for i in $(seq 1 12); do docker exec SAT-$i k3s-ctl clean; done
./scripts/k3s-ha.sh start
```

**Master layout:**
- SAT-3 (172.27.12.103) — primary / bootstrap master
- SAT-6 (172.27.12.106) — secondary master (joins SAT-3)
- SAT-9 (172.27.12.109) — tertiary master (joins SAT-3)
- Rest are workers

**Key insight:** with HA + OLSRd, even if one master loses LOS to another, etcd quorum (2/3) is maintained via multi-hop routes, so the cluster stays operational.

---

## Manual k3s Control (without scripts)

If you want to manage individual nodes by hand:

### Start OLSRd (all nodes)
```bash
# Start mesh routing on all nodes
for i in $(seq 1 12); do docker exec SAT-$i routing-ctl start olsrd; done

# Wait for convergence (~30s)
sleep 30

# Verify neighbors and routes
docker exec SAT-1 routing-ctl status
docker exec SAT-4 ip route | grep "172.27"
```

### Start k3s Single-Master (manual)
```bash
# 1. Start master on SAT-1
docker exec SAT-1 k3s-ctl master

# 2. Wait for API to be Ready
docker exec SAT-1 k3s kubectl get nodes

# 3. Get the token from master
TOKEN=$(docker exec SAT-1 cat /var/lib/rancher/k3s/server/node-token)

# 4. Join workers (SAT-2 through SAT-12)
for i in $(seq 2 12); do
  docker exec -e K3S_TOKEN="$TOKEN" SAT-$i k3s-ctl worker 172.27.12.101
done

# 5. Verify
docker exec SAT-1 k3s kubectl get nodes -o wide
```

### Start k3s HA (manual)
```bash
# 1. Initialize first master (SAT-3)
docker exec SAT-3 k3s-ctl distributed-master

# 2. Wait for it to be Ready
sleep 30

# 3. Get token from SAT-3
TOKEN=$(docker exec SAT-3 cat /var/lib/rancher/k3s/server/node-token)

# 4. Join other masters (SAT-6, SAT-9)
docker exec -e K3S_TOKEN="$TOKEN" SAT-6 k3s-ctl distributed-master 172.27.12.103
docker exec -e K3S_TOKEN="$TOKEN" SAT-9 k3s-ctl distributed-master 172.27.12.103

# 5. Join workers
for i in 1 2 4 5 7 8 10 11 12; do
  docker exec -e K3S_TOKEN="$TOKEN" SAT-$i k3s-ctl worker 172.27.12.103
done

# 6. Verify
docker exec SAT-3 k3s kubectl get nodes -o wide
```

### Stop and Clean (manual)
```bash
# Stop k3s on all nodes (preserves state)
for i in $(seq 1 12); do docker exec SAT-$i k3s-ctl stop; done

# Full reset (wipe k3s and mesh)
for i in $(seq 1 12); do
  docker exec SAT-$i k3s-ctl clean
  docker exec SAT-$i routing-ctl off
done
```

---

## Node-by-Node Inspection

### View k3s status on a node
```bash
docker exec SAT-1 k3s-ctl status
```

Output:
```
k3s: running (PID 42), node-ip 172.27.12.101
NAME   STATUS   ROLES    AGE   VERSION
sat-1  Ready    <none>   2m    v1.31.4+k3s1
...
```

### View routing status on a node
```bash
docker exec SAT-4 routing-ctl status
```

Output:
```
olsrd: running
babeld: stopped
--- ip route ---
172.27.12.0/24 dev eth0 proto kernel scope link src 172.27.12.104
172.27.12.101 via 172.27.12.103 dev eth0 metric 2
172.27.12.106 via 172.27.12.103 dev eth0 metric 2
...
```

### View OLSRd neighbors
```bash
docker exec SAT-1 curl -s http://127.0.0.1:2006/neighbours
```

(txtinfo plugin must be loaded in olsrd.conf; check `routing-ctl start olsrd` for confirmation.)

---

## Troubleshooting

### Nodes stuck in `NotReady`
```bash
# Check if k3s is running
docker exec SAT-N k3s-ctl status

# Check logs
docker exec SAT-N tail -50 /var/log/k3s.log

# If using OLSRd: verify mesh convergence
docker exec SAT-N routing-ctl status
docker exec SAT-N ip route

# If the node is multi-hop from master: ensure OLSRd discovered the route
sleep 30  # Give OLSRd ~30s to converge
docker exec SAT-1 k3s kubectl get nodes
```

### Can't reach master from a worker
```bash
# 1. Check if master is reachable at all
docker exec SAT-N ping -c 1 172.27.12.101

# 2. If no LOS, check if OLSRd has a route
docker exec SAT-N routing-ctl status | grep "172.27.12.101"

# 3. If no route, wait longer (convergence ~30s)
sleep 30 && docker exec SAT-N routing-ctl status
```

### Cluster won't start after restart
```bash
# HA clusters check for stale etcd state. If etcd is corrupted:
docker exec SAT-3 k3s-ctl clean  # wipes /var/lib/rancher/k3s
./scripts/k3s-ha.sh start        # fresh init
```

---

## Summary: Which Script to Use?

| Scenario | Script | Command |
|----------|--------|---------|
| Flat k3s, no routing | `k3s-single.sh` | `./scripts/k3s-single.sh start` |
| k3s + OLSRd mesh (single master) | `k3s-single.sh` | `./scripts/k3s-single.sh start` |
| k3s HA + OLSRd mesh (3 masters) | `k3s-ha.sh` | `./scripts/k3s-ha.sh start` |
| Manual per-node control | `k3s-ctl` (inside container) | `docker exec SAT-N k3s-ctl ...` |
| Manual mesh control | `routing-ctl` (inside container) | `docker exec SAT-N routing-ctl ...` |

---

## Environment Variables

You can override defaults per-node by setting env vars on `docker exec`:

```bash
# Use a different cluster token
docker exec -e K3S_TOKEN="my-custom-token" SAT-1 k3s-ctl master

# Use a different node IP (normally auto-detected from 172.27.x)
docker exec -e K3S_NODE_IP="192.168.1.100" SAT-1 k3s-ctl master

# Use a different data directory
docker exec -e K3S_DATA_DIR="/mnt/my-data" SAT-1 k3s-ctl master
```

See `docker/k3s-ctl.sh` for all available env vars and defaults.

---

## Next Steps

1. **Start a cluster:** `./scripts/k3s-single.sh start`
2. **Deploy a test app:** `docker exec SAT-1 k3s kubectl apply -f ...`
3. **Monitor convergence:** `docker exec SAT-1 k3s kubectl get nodes -w`
4. **Inspect multi-hop routes:** `docker exec SAT-4 ip route`
5. **Check mesh neighbors:** `docker exec SAT-1 curl -s http://127.0.0.1:2006/neighbours`

