#!/bin/bash
# k3s.sh — manage k3s clusters on VSNES satellite containers
#
# Modes:
#   single   One master (default SAT-1) + all others as workers (one cluster)
#   ha       Three masters (SAT-3, SAT-6, SAT-9) + nine workers (one cluster)
#   uniq     Each SAT runs its OWN independent single-node cluster (N clusters)
#
# Usage:
#   ./scripts/k3s.sh single start [MASTER]   Start single-master cluster
#   ./scripts/k3s.sh single stop             Stop (preserves state)
#   ./scripts/k3s.sh single clean            Stop + wipe state on all nodes
#   ./scripts/k3s.sh single status           Show nodes and pods
#
#   ./scripts/k3s.sh uniq start              Start a standalone cluster on each SAT
#   ./scripts/k3s.sh uniq stop               Stop every per-node cluster
#   ./scripts/k3s.sh uniq clean              Stop + wipe state on all nodes
#   ./scripts/k3s.sh uniq status             Show each SAT's own cluster status
#
#   ./scripts/k3s.sh ha start                Start HA cluster (3 masters)
#   ./scripts/k3s.sh ha stop                 Stop (preserves etcd state)
#   ./scripts/k3s.sh ha restart              Stop then start
#   ./scripts/k3s.sh ha clean                Stop + wipe state on all nodes
#   ./scripts/k3s.sh ha status               Show nodes and pods
#
#   ./scripts/k3s.sh olsr                    Start OLSRd on all nodes (if needed)
#   ./scripts/k3s.sh olsr-status             Show OLSRd neighbour table on every node
#   ./scripts/k3s.sh clean                   Wipe k3s state on ALL nodes
#   ./scripts/k3s.sh status                  Show cluster status (auto-detect mode)
#
# OLSRd + k3s:
#   OLSRd runs on eth0 inside each container and installs multi-hop Linux routes
#   for satellite pairs that are not in direct LOS.  k3s control-plane and flannel
#   traffic automatically follow these routes because k3s uses the 172.27.x
#   management address (OLSRd-announced), not the flat 10.0.0.x emulated address.
#   Start OLSRd first with `./scripts/k3s.sh olsr`, then start the cluster.

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────

ALL_NODES=(SAT-1 SAT-2 SAT-3 SAT-4 SAT-5 SAT-6 SAT-7 SAT-8 SAT-9 SAT-10 SAT-11 SAT-12)
ALL_GS=(Ibi_ES Foggia_IT)   # ground stations — included in olsr start/status

# Single-master: who is the master (positional arg or default)
SINGLE_MASTER="${3:-SAT-1}"

# HA: fixed masters and workers
HA_MASTERS=(SAT-3 SAT-6 SAT-9)
HA_WORKERS=(SAT-1 SAT-2 SAT-4 SAT-5 SAT-7 SAT-8 SAT-10 SAT-11 SAT-12)
declare -A HA_MASTER_IP
HA_MASTER_IP[SAT-3]="172.27.12.103"
HA_MASTER_IP[SAT-6]="172.27.12.106"
HA_MASTER_IP[SAT-9]="172.27.12.109"
HA_BOOTSTRAP="${HA_MASTERS[0]}"
HA_BOOTSTRAP_IP="${HA_MASTER_IP[$HA_BOOTSTRAP]}"

OLSR_CONVERGE_SECS=30    # seconds to wait for OLSRd to populate routing tables
MASTER_READY_SECS=120    # seconds to wait for k3s API to become ready

# ── Shared helpers ─────────────────────────────────────────────────────────────

log() { echo "[$(date +%H:%M:%S)] $*"; }

node_ip() {
    docker inspect "$1" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
}

is_api_ready() {
    docker exec "$1" k3s kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml \
        get nodes 2>/dev/null | grep -q "Ready"
}

wait_for_node() {
    local node="$1" timeout="${2:-$MASTER_READY_SECS}" elapsed=0
    log "Waiting for $node API server (up to ${timeout}s)..."
    while [ "$elapsed" -lt "$timeout" ]; do
        if is_api_ready "$node" 2>/dev/null; then
            log "$node is Ready."
            return 0
        fi
        sleep 5; elapsed=$((elapsed + 5)); echo -n "."
    done
    echo ""
    log "ERROR: $node did not become ready in ${timeout}s"
    log "  Check logs: docker exec $node tail -50 /var/log/k3s.log"
    return 1
}

read_token() {
    docker exec "$1" cat /var/lib/rancher/k3s/server/node-token 2>/dev/null
}

# ── OLSRd commands (shared) ───────────────────────────────────────────────────

_olsr_start_node() {
    local node="$1"
    # pgrep returns exit 1 when no match; || true prevents set -e from aborting.
    local procs
    procs=$(docker exec "$node" pgrep olsrd 2>/dev/null | wc -l) || true
    if [ "$procs" -eq 0 ]; then
        docker exec "$node" routing-ctl start olsrd 2>/dev/null || true
        echo "  $node: olsrd started"
    else
        echo "  $node: olsrd already running"
    fi
}

_olsr_status_node() {
    local node="$1"
    echo -n "  $node: "
    local neigh
    neigh=$(docker exec "$node" curl -s http://127.0.0.1:2006/neighbours 2>/dev/null \
        | awk '/^Table: Neighbors/{found=1;next} found && /^[0-9]/{print $1} found && /^$/{exit}' \
        | tr '\n' ' ')
    echo "${neigh:-(no olsrd / no neighbours)}"
}

cmd_olsr_start() {
    log "Ensuring OLSRd is running on all SATs and ground stations..."
    for node in "${ALL_NODES[@]}" "${ALL_GS[@]}"; do
        docker inspect "$node" --format '{{.State.Running}}' 2>/dev/null | grep -q true \
            && _olsr_start_node "$node" \
            || echo "  $node: not running — skipped"
    done
    log "Waiting ${OLSR_CONVERGE_SECS}s for OLSRd to converge and install routes..."
    sleep "$OLSR_CONVERGE_SECS"
    log "OLSRd ready."
}

cmd_olsr_status() {
    log "=== OLSRd neighbour tables ==="
    for node in "${ALL_NODES[@]}" "${ALL_GS[@]}"; do
        docker inspect "$node" --format '{{.State.Running}}' 2>/dev/null | grep -q true \
            && _olsr_status_node "$node" \
            || echo "  $node: not running"
    done
}

# ── Clean (shared) ────────────────────────────────────────────────────────────

cmd_clean_all() {
    log "Wiping k3s state on all ${#ALL_NODES[@]} nodes..."
    for node in "${ALL_NODES[@]}"; do
        log "  $node: k3s-ctl clean"
        docker exec "$node" k3s-ctl clean 2>/dev/null || true
    done
    log "All nodes clean."
}

# ── Single-master mode ────────────────────────────────────────────────────────

single_start() {
    local mip
    mip="$(node_ip "$SINGLE_MASTER")"
    log "Mode: single-master  |  master: $SINGLE_MASTER ($mip)"

    log "Starting k3s master on $SINGLE_MASTER (node-ip $mip)..."
    # Pin node-ip from docker inspect (stable 172.27.x) rather than letting the
    # in-container detect_ip race the sim's eth0 reconfiguration, which can fall
    # back to the unrouted 10.0.0.x flat address.
    docker exec -e K3S_NODE_IP="$mip" "$SINGLE_MASTER" k3s-ctl master
    wait_for_node "$SINGLE_MASTER"

    local token
    token="$(read_token "$SINGLE_MASTER")"
    log "Got cluster token."

    log "Joining workers in parallel..."
    for node in "${ALL_NODES[@]}"; do
        [ "$node" = "$SINGLE_MASTER" ] && continue
        local wip; wip="$(node_ip "$node")"
        log "  $node ($wip) → $SINGLE_MASTER ($mip)"
        docker exec -e K3S_TOKEN="$token" -e K3S_NODE_IP="$wip" \
            "$node" k3s-ctl worker "$mip" &
    done
    wait

    log "Waiting 30s for workers to register..."
    sleep 30
    single_status
}

single_stop() {
    log "Stopping single-master cluster (workers first)..."
    for node in "${ALL_NODES[@]}"; do
        [ "$node" = "$SINGLE_MASTER" ] && continue
        log "  $node: stop"
        docker exec "$node" k3s-ctl stop 2>/dev/null || true
    done
    log "  $SINGLE_MASTER: stop"
    docker exec "$SINGLE_MASTER" k3s-ctl stop 2>/dev/null || true
    log "Cluster stopped (state preserved)."
}

single_status() {
    log "=== Cluster status (single: master=$SINGLE_MASTER) ==="
    if ! docker exec "$SINGLE_MASTER" k3s kubectl get nodes -o wide 2>/dev/null; then
        log "API not ready — try again in a few seconds."
        return 1
    fi
    echo ""
    docker exec "$SINGLE_MASTER" k3s kubectl get pods -A 2>/dev/null || true
}

# ── Uniq mode (independent single-node cluster on every satellite) ────────────
#
# Each SAT runs its own standalone single-node k3s cluster — no master/worker
# relationship, no shared etcd, no mesh dependency. Useful for testing per-node
# workloads or when you want N isolated clusters instead of one joined cluster.

uniq_start() {
    log "Mode: uniq  |  starting an independent single-node cluster on each SAT"
    for node in "${ALL_NODES[@]}"; do
        local ip; ip="$(node_ip "$node")"
        log "  $node ($ip): k3s-ctl single"
        docker exec -e K3S_NODE_IP="$ip" "$node" k3s-ctl single &
    done
    wait

    log "Waiting 30s for each node's API to come up..."
    sleep 30
    uniq_status
}

uniq_stop() {
    log "Stopping the single-node cluster on every SAT..."
    for node in "${ALL_NODES[@]}"; do
        log "  $node: stop"
        docker exec "$node" k3s-ctl stop 2>/dev/null || true
    done
    log "All per-node clusters stopped (state preserved)."
}

uniq_status() {
    log "=== Per-node cluster status (uniq: each SAT is its own cluster) ==="
    for node in "${ALL_NODES[@]}"; do
        local line
        line=$(docker exec "$node" k3s kubectl get nodes -o wide --no-headers 2>/dev/null \
            | awk '{printf "%s (%s)", $2, $6}')
        printf "  %-7s %s\n" "$node:" "${line:-not ready / not running}"
    done
}

# ── HA mode ───────────────────────────────────────────────────────────────────

ha_get_token() {
    local token=""
    for m in "${HA_MASTERS[@]}"; do
        token=$(docker exec "$m" cat /var/lib/rancher/k3s/server/node-token 2>/dev/null) && break
    done
    if [ -z "$token" ]; then
        log "ERROR: Could not read node-token from any HA master."
        log "  Is the cluster running? Run: ./scripts/k3s.sh ha start"
        exit 1
    fi
    echo "$token"
}

ha_start() {
    # Detect whether etcd already has state (restart) or needs a fresh init
    if docker exec "$HA_BOOTSTRAP" test -d \
            /var/lib/rancher/k3s/server/db/etcd/member 2>/dev/null; then
        log "Existing etcd state on $HA_BOOTSTRAP — resuming cluster..."

        log "Starting bootstrap master ($HA_BOOTSTRAP)..."
        docker exec -e K3S_NODE_IP="$HA_BOOTSTRAP_IP" "$HA_BOOTSTRAP" k3s-ctl master
        wait_for_node "$HA_BOOTSTRAP" 120

        local token
        token=$(ha_get_token)

        log "Resuming remaining masters..."
        for m in "${HA_MASTERS[@]:1}"; do
            log "  $m (${HA_MASTER_IP[$m]}) → join $HA_BOOTSTRAP"
            docker exec -e K3S_TOKEN="$token" -e K3S_NODE_IP="${HA_MASTER_IP[$m]}" "$m" \
                k3s-ctl distributed-master "$HA_BOOTSTRAP_IP"
        done
    else
        log "No etcd state — initializing fresh HA cluster on $HA_BOOTSTRAP..."
        docker exec -e K3S_NODE_IP="$HA_BOOTSTRAP_IP" "$HA_BOOTSTRAP" k3s-ctl distributed-master
        wait_for_node "$HA_BOOTSTRAP" 90

        local token
        token=$(ha_get_token)

        log "Joining remaining masters..."
        for m in "${HA_MASTERS[@]:1}"; do
            log "  $m (${HA_MASTER_IP[$m]}) → join $HA_BOOTSTRAP"
            docker exec -e K3S_TOKEN="$token" -e K3S_NODE_IP="${HA_MASTER_IP[$m]}" "$m" \
                k3s-ctl distributed-master "$HA_BOOTSTRAP_IP"
        done
    fi

    # Wait for all masters to be Ready before joining workers
    for m in "${HA_MASTERS[@]:1}"; do
        wait_for_node "$m" 90 || log "WARNING: $m not ready yet (still syncing etcd)"
    done

    local token
    token=$(ha_get_token)

    log "Joining workers..."
    for node in "${HA_WORKERS[@]}"; do
        wip="$(node_ip "$node")"
        log "  $node ($wip) → $HA_BOOTSTRAP ($HA_BOOTSTRAP_IP)"
        docker exec -e K3S_TOKEN="$token" -e K3S_NODE_IP="$wip" "$node" \
            k3s-ctl worker "$HA_BOOTSTRAP_IP" 2>/dev/null || true &
    done
    wait

    log "Waiting 30s for workers to register..."
    sleep 30
    ha_status
}

ha_stop() {
    log "Stopping HA cluster (workers first, masters last)..."
    for node in "${HA_WORKERS[@]}"; do
        log "  $node: stop"
        docker exec "$node" k3s-ctl stop 2>/dev/null || true
    done
    for m in "${HA_MASTERS[@]}"; do
        log "  $m: stop"
        docker exec "$m" k3s-ctl stop 2>/dev/null || true
    done
    log "HA cluster stopped (etcd state preserved)."
}

ha_status() {
    log "=== Cluster status (HA: masters=${HA_MASTERS[*]}) ==="
    for m in "${HA_MASTERS[@]}"; do
        if docker exec "$m" k3s kubectl get nodes -o wide 2>/dev/null; then
            echo ""
            docker exec "$m" k3s kubectl get pods -A 2>/dev/null || true
            return 0
        fi
    done
    log "No HA master available — cluster may be stopped."
    return 1
}

# ── Auto-detect status ─────────────────────────────────────────────────────────

cmd_status_auto() {
    # Try single master first, then HA masters
    if is_api_ready "$SINGLE_MASTER" 2>/dev/null; then
        single_status
    else
        ha_status 2>/dev/null || log "No cluster running (tried single=$SINGLE_MASTER and HA masters)."
    fi
}

# ── Dispatch ──────────────────────────────────────────────────────────────────

usage() {
    sed -n '3,29p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
}

MODE="${1:-}"
CMD="${2:-}"

case "$MODE" in
    single)
        case "$CMD" in
            start)   single_start  ;;
            stop)    single_stop   ;;
            clean)   cmd_clean_all ;;
            status)  single_status ;;
            *) echo "Usage: $0 single {start [MASTER]|stop|clean|status}"; exit 1 ;;
        esac
        ;;
    uniq)
        case "$CMD" in
            start)   uniq_start  ;;
            stop)    uniq_stop   ;;
            clean)   cmd_clean_all ;;
            status)  uniq_status ;;
            *) echo "Usage: $0 uniq {start|stop|clean|status}"; exit 1 ;;
        esac
        ;;
    ha)
        case "$CMD" in
            start)   ha_start  ;;
            stop)    ha_stop   ;;
            restart) ha_stop; echo; ha_start ;;
            clean)   cmd_clean_all ;;
            status)  ha_status ;;
            *) echo "Usage: $0 ha {start|stop|restart|clean|status}"; exit 1 ;;
        esac
        ;;
    olsr)        cmd_olsr_start  ;;
    olsr-status) cmd_olsr_status ;;
    clean)       cmd_clean_all   ;;
    status)      cmd_status_auto ;;
    *)           usage ;;
esac
