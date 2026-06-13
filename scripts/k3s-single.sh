#!/bin/bash
# k3s-single.sh — single-master k3s cluster over the VSNES OLSRd mesh
#
# Usage:
#   ./scripts/k3s-single.sh start [MASTER]   Start cluster (default master: SAT-1)
#   ./scripts/k3s-single.sh stop             Stop all k3s processes (preserves state)
#   ./scripts/k3s-single.sh clean            Stop + wipe state on every node
#   ./scripts/k3s-single.sh status           Show cluster nodes and pods
#   ./scripts/k3s-single.sh olsr             Show OLSRd neighbour table on every node
#
# How it works:
#   OLSRd runs on eth0 inside each container and installs multi-hop Linux routes
#   for satellite pairs that are not in direct LOS.  netem already drops 100% of
#   traffic on no-LOS pairs, so k3s control-plane + flannel traffic is forced
#   through the OLSRd-computed mesh paths.

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
MASTER="${2:-SAT-1}"
ALL_NODES=(SAT-1 SAT-2 SAT-3 SAT-4 SAT-5 SAT-6 SAT-7 SAT-8 SAT-9 SAT-10 SAT-11 SAT-12)
OLSR_CONVERGE_SECS=30   # seconds to wait for OLSRd to populate routing tables
MASTER_READY_SECS=120   # seconds to wait for k3s API to become ready

# ── Helpers ───────────────────────────────────────────────────────────────────
log() { echo "[$(date +%H:%M:%S)] $*"; }

master_ip() {
    docker inspect "$MASTER" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
}

is_k3s_api_ready() {
    local m="$1"
    docker exec "$m" k3s kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml \
        get nodes 2>/dev/null | grep -q "Ready"
}

wait_for_master() {
    local elapsed=0
    log "Waiting for $MASTER API server (up to ${MASTER_READY_SECS}s)..."
    while [ "$elapsed" -lt "$MASTER_READY_SECS" ]; do
        if is_k3s_api_ready "$MASTER" 2>/dev/null; then
            log "$MASTER is Ready."
            return 0
        fi
        sleep 5; elapsed=$((elapsed + 5)); echo -n "."
    done
    echo ""
    log "ERROR: $MASTER did not become ready in ${MASTER_READY_SECS}s"
    log "Check logs: docker exec $MASTER tail -50 /var/log/k3s.log"
    return 1
}

get_token() {
    docker exec "$MASTER" cat /var/lib/rancher/k3s/server/node-token 2>/dev/null
}

ensure_olsrd() {
    log "Ensuring OLSRd is running on all nodes..."
    for node in "${ALL_NODES[@]}"; do
        procs=$(docker exec "$node" pgrep olsrd 2>/dev/null | wc -l)
        if [ "$procs" -eq 0 ]; then
            docker exec -d "$node" olsrd -f /etc/olsrd/olsrd.conf 2>/dev/null || true
            echo "  $node: olsrd started"
        else
            echo "  $node: olsrd already running"
        fi
    done
    log "Waiting ${OLSR_CONVERGE_SECS}s for OLSRd to converge and install routes..."
    sleep "$OLSR_CONVERGE_SECS"
}

# ── Commands ──────────────────────────────────────────────────────────────────

cmd_clean() {
    log "Cleaning k3s state on all nodes..."
    for node in "${ALL_NODES[@]}"; do
        log "  $node: k3s-ctl clean"
        docker exec "$node" k3s-ctl clean 2>/dev/null || true
    done
    log "All nodes clean."
}

cmd_stop() {
    log "Stopping k3s — workers first, then master..."
    for node in "${ALL_NODES[@]}"; do
        [ "$node" = "$MASTER" ] && continue
        log "  $node: stop"
        docker exec "$node" k3s-ctl stop 2>/dev/null || true
    done
    log "  $MASTER: stop"
    docker exec "$MASTER" k3s-ctl stop 2>/dev/null || true
    log "Cluster stopped (state preserved)."
}

cmd_start() {
    local mip
    mip="$(master_ip)"
    log "Master: $MASTER ($mip)"
    log "Workers: ${ALL_NODES[*]/$MASTER/} (all others)"

    # 1 — OLSRd
    ensure_olsrd

    # 2 — start master
    log "Starting k3s master on $MASTER..."
    docker exec "$MASTER" k3s-ctl master

    # 3 — wait for master API
    wait_for_master

    # 4 — get join token
    local token
    token="$(get_token)"
    log "Got cluster token."

    # 5 — join workers
    log "Joining workers..."
    for node in "${ALL_NODES[@]}"; do
        [ "$node" = "$MASTER" ] && continue
        log "  $node → join $MASTER ($mip)"
        docker exec -e K3S_TOKEN="$token" "$node" k3s-ctl worker "$mip" &
    done
    wait

    log "Waiting 30s for workers to register..."
    sleep 30

    # 6 — status
    cmd_status
}

cmd_status() {
    log "=== Cluster status ==="
    if ! docker exec "$MASTER" k3s kubectl get nodes -o wide 2>/dev/null; then
        log "API not ready — try again in a few seconds."
        return 1
    fi
    echo ""
    docker exec "$MASTER" k3s kubectl get pods -A 2>/dev/null || true
}

cmd_olsr() {
    log "=== OLSRd neighbour tables ==="
    for node in "${ALL_NODES[@]}"; do
        echo -n "  $node: "
        neigh=$(docker exec "$node" curl -s http://127.0.0.1:2006/neighbours 2>/dev/null \
            | awk '/^Table: Neighbors/{found=1;next} found && /^[0-9]/{print $1} found && /^$/{exit}' \
            | tr '\n' ' ')
        echo "${neigh:-(no olsrd / no neighbours)}"
    done
}

# ── Main ──────────────────────────────────────────────────────────────────────
case "${1:-}" in
    start)  cmd_start  ;;
    stop)   cmd_stop   ;;
    clean)  cmd_clean  ;;
    status) cmd_status ;;
    olsr)   cmd_olsr   ;;
    *)
        echo "Usage: $0 {start|stop|clean|status|olsr} [MASTER_NODE]"
        echo ""
        echo "  start [MASTER]  Start single-master cluster (default: SAT-1)"
        echo "  stop            Stop k3s on all nodes (preserves state)"
        echo "  clean           Stop + wipe k3s state on all nodes"
        echo "  status          Show nodes and pods via master"
        echo "  olsr            Show OLSRd neighbour table on every node"
        exit 1
        ;;
esac
