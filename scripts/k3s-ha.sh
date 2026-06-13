#!/bin/bash
# k3s-ha.sh — manage the VSNES k3s HA cluster (3 masters + workers)
#
# Usage:
#   ./scripts/k3s-ha.sh start    # Start masters then workers (preserves state)
#   ./scripts/k3s-ha.sh stop     # Stop workers then masters (preserves state)
#   ./scripts/k3s-ha.sh status   # Show node status from any available master
#   ./scripts/k3s-ha.sh restart  # Stop + start
#
# State is preserved across stop/start as long as k3s-data volumes are intact.
# Do NOT use k3s-ctl clean if you want to keep state.
#
# To do a full reset instead: docker exec <SAT> k3s-ctl clean

set -euo pipefail

# === Configuration ===

MASTERS=("SAT-3" "SAT-6" "SAT-9")
WORKERS=("SAT-1" "SAT-2" "SAT-4" "SAT-5" "SAT-7" "SAT-8" "SAT-10" "SAT-11" "SAT-12")

# Master IPs (must match docker-compose.yml)
declare -A MASTER_IP
MASTER_IP[SAT-3]="172.27.12.103"
MASTER_IP[SAT-6]="172.27.12.106"
MASTER_IP[SAT-9]="172.27.12.109"

JOIN_MASTER="${MASTERS[0]}"   # first master is the bootstrap node
JOIN_IP="${MASTER_IP[$JOIN_MASTER]}"

# === Helpers ===

log() { echo "[$(date +%H:%M:%S)] $*"; }

get_token() {
    local token=""
    for m in "${MASTERS[@]}"; do
        token=$(docker exec "$m" cat /var/lib/rancher/k3s/server/node-token 2>/dev/null) && break
    done
    if [ -z "$token" ]; then
        echo "ERROR: Could not read node-token from any master." >&2
        echo "Is the cluster running? Use 'start' to initialize a fresh cluster." >&2
        exit 1
    fi
    echo "$token"
}

wait_ready() {
    local sat="$1" timeout="${2:-60}" elapsed=0
    while [ "$elapsed" -lt "$timeout" ]; do
        if docker exec "$sat" k3s-ctl status 2>/dev/null | grep -q "Ready"; then
            return 0
        fi
        sleep 5
        elapsed=$((elapsed + 5))
        echo -n "."
    done
    echo " TIMEOUT"
    return 1
}

# === Commands ===

cmd_stop() {
    log "Stopping workers..."
    for sat in "${WORKERS[@]}"; do
        log "  stopping $sat"
        docker exec "$sat" k3s-ctl stop 2>/dev/null || true
    done

    log "Stopping masters (last to preserve quorum)..."
    for sat in "${MASTERS[@]}"; do
        log "  stopping $sat"
        docker exec "$sat" k3s-ctl stop 2>/dev/null || true
    done

    log "Cluster stopped. State preserved in k3s-data volumes."
}

cmd_start() {
    # Check if first master already has etcd state (restart) or needs init (fresh)
    local has_state="no"
    if docker exec "$JOIN_MASTER" test -d /var/lib/rancher/k3s/server/db/etcd/member 2>/dev/null; then
        has_state="yes"
    fi

    if [ "$has_state" = "yes" ]; then
        log "Existing etcd state found on $JOIN_MASTER — restarting cluster..."

        # On restart, masters must NOT use --cluster-init. They should start as
        # server nodes that rejoin the existing etcd cluster. We start the
        # bootstrap master first (plain server), then the rest join it.
        log "Starting bootstrap master ($JOIN_MASTER)..."
        docker exec "$JOIN_MASTER" k3s-ctl master
        log "Waiting for $JOIN_MASTER to be Ready..."
        wait_ready "$JOIN_MASTER" 120 || { log "ERROR: $JOIN_MASTER did not become ready"; exit 1; }

        local token
        token=$(get_token)

        log "Starting remaining masters..."
        for m in "${MASTERS[@]:1}"; do
            log "  starting $m → join $JOIN_MASTER"
            docker exec -e K3S_TOKEN="$token" "$m" k3s-ctl distributed-master "${JOIN_IP}"
        done
        for m in "${MASTERS[@]:1}"; do
            wait_ready "$m" 90 || log "WARNING: $m not ready yet"
        done
    else
        log "No existing state — initializing fresh cluster on $JOIN_MASTER..."
        docker exec "$JOIN_MASTER" k3s-ctl distributed-master
        log "Waiting for $JOIN_MASTER to be Ready..."
        wait_ready "$JOIN_MASTER" 90 || { log "ERROR: $JOIN_MASTER did not become ready"; exit 1; }

        local token
        token=$(get_token)

        log "Joining remaining masters..."
        for m in "${MASTERS[@]:1}"; do
            log "  starting $m → join $JOIN_MASTER"
            docker exec -e K3S_TOKEN="$token" "$m" k3s-ctl distributed-master "${JOIN_IP}"
        done
        for m in "${MASTERS[@]:1}"; do
            wait_ready "$m" 60 || log "WARNING: $m not ready yet (may still be syncing etcd)"
        done
    fi

    local token
    token=$(get_token)

    log "Starting workers..."
    for sat in "${WORKERS[@]}"; do
        log "  starting $sat → join $JOIN_MASTER"
        docker exec -e K3S_TOKEN="$token" "$sat" k3s-ctl worker "${JOIN_IP}" 2>/dev/null || true
    done

    log "Waiting for workers to register..."
    sleep 30

    log "Cluster status:"
    docker exec "$JOIN_MASTER" k3s kubectl get nodes 2>/dev/null || \
        log "API not ready yet — check with: docker exec $JOIN_MASTER k3s-ctl status"

    log "Done."
}

cmd_status() {
    for m in "${MASTERS[@]}"; do
        if docker exec "$m" k3s kubectl get nodes 2>/dev/null; then
            echo "---"
            docker exec "$m" k3s kubectl get pods -A 2>/dev/null
            return 0
        fi
    done
    echo "No master available — cluster is stopped."
    return 1
}

cmd_restart() {
    cmd_stop
    echo
    cmd_start
}

# === Main ===

case "${1:-}" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    status)  cmd_status ;;
    restart) cmd_restart ;;
    *)
        echo "Usage: $0 {start|stop|status|restart}"
        echo ""
        echo "Commands:"
        echo "  start   Initialize or resume the HA cluster (masters first, then workers)"
        echo "  stop    Stop the cluster preserving state (workers first, then masters)"
        echo "  status  Show nodes and pods from any available master"
        echo "  restart Stop + start"
        exit 1
        ;;
esac
