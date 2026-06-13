#!/bin/bash
# k3s-ctl — start/stop k3s on this node in one of several roles.
# By default the container runs plain Debian + SSH; k3s only runs when started
# here.
#
#   k3s-ctl single                      Standalone single-node cluster
#   k3s-ctl master                      Single control-plane (hardcoded token);
#                                        workers join it
#   k3s-ctl distributed-master          First HA master (embedded etcd, cluster-init)
#   k3s-ctl distributed-master <ip>     Additional HA master joining <ip>
#   k3s-ctl worker <master-ip>          Join an existing cluster as a worker/agent
#   k3s-ctl status
#   k3s-ctl stop
#   k3s-ctl clean                       Stop k3s and wipe all state so the next
#                                        start is fully fresh (data-dir, logs,
#                                        pid file, stale k8s.io cgroup)
#
# Env overrides:
#   K3S_TOKEN     cluster token   (default: vsnes-cluster-2026)
#                 For HA joins, pass the FULL token from the master's
#                 node-token file (includes CA hash prefix like K10...).
#                 Use: docker exec -e K3S_TOKEN="$(docker exec MASTER cat /var/lib/rancher/k3s/server/node-token)" SAT-N k3s-ctl distributed-master MASTER_IP
#   K3S_IFACE     flannel iface   (default: eth0)
#   K3S_NODE_IP   node IP         (default: the node's 10.0.0.x mesh address,
#                                  else the primary eth0 address)
#   K3S_DATA_DIR  data dir        (default: /var/lib/rancher/k3s)

set -u

TOKEN="${K3S_TOKEN:-vsnes-cluster-2026}"
IFACE="${K3S_IFACE:-eth0}"
DATA_DIR="${K3S_DATA_DIR:-/var/lib/rancher/k3s}"
K3S_BIN="/usr/local/bin/k3s"
LOG="/var/log/k3s.log"
K3S_PID="/run/k3s.pid"
K3S_CMD="/run/k3s-cmd"
SUP_PID="/run/supervisor.pid"

# Prefer the management address (172.27.x) because that is the network OLSRd
# actually announces and installs multi-hop routes for. The emulated 10.0.0.x
# address is a flat /24 with NO mesh routing (and no-LOS pairs drop it), so a
# worker that is multi-hop from the master cannot reach the master's 10.0.0.x
# endpoint once their direct LOS breaks. Riding 172.27.x makes k3s control-plane
# and flannel traffic follow the OLSRd-computed mesh paths. Fall back to the
# primary eth0 address if no 172.27.x is present.
detect_ip() {
    local ip
    ip="$(ip -4 -o addr show dev "${IFACE}" 2>/dev/null | grep -oE '172\.27\.[0-9]+\.[0-9]+' | head -n1)"
    [ -n "$ip" ] || ip="$(ip -4 -o addr show dev "${IFACE}" 2>/dev/null | grep -oP '(?<=inet )\S+' | cut -d/ -f1 | head -n1)"
    echo "$ip"
}
MY_IP="${K3S_NODE_IP:-$(detect_ip)}"

# Shared server flags. The kubelet/snapshotter tweaks are what let k3s run inside
# an unprivileged-ish container on the VSNES bridge.
server_args() {
    echo "--token=${TOKEN} \
--node-ip=${MY_IP} --advertise-address=${MY_IP} --tls-san=${MY_IP} \
--flannel-iface=${IFACE} --data-dir=${DATA_DIR} \
--write-kubeconfig-mode=644 --snapshotter=native \
--kubelet-arg=cgroups-per-qos=false --kubelet-arg=enforce-node-allocatable="
}

ensure_kmsg() {
    [ -e /dev/kmsg ] || ln -s /dev/null /dev/kmsg 2>/dev/null || true
}

is_running() { pgrep -f "${K3S_BIN} " >/dev/null 2>&1; }

kill_existing() {
    pkill -f "${K3S_BIN} " 2>/dev/null || true
    # Best-effort cleanup of the workload runtime k3s spawns.
    pkill -f 'containerd-shim' 2>/dev/null || true
    rm -f "${K3S_PID}"
    sleep 2
}

launch() {
    # launch <role-label> <k3s subcommand + args...>
    # Delegates to the container supervisor (entrypoint.sh / PID 1 child) via
    # SIGUSR1. The supervisor starts k3s as its own child, which lives in the
    # container's main cgroup — not in the transient docker-exec cgroup — so k3s
    # survives after this script (and its exec session) exits.
    local label="$1"; shift
    ensure_kmsg

    local sup_pid
    sup_pid=$(cat "${SUP_PID}" 2>/dev/null) || {
        echo "error: supervisor not running (${SUP_PID} not found)" >&2
        return 1
    }

    # Write one arg per line; supervisor reads with mapfile
    printf '%s\n' "$@" > "${K3S_CMD}"

    # Signal supervisor to read the command and launch k3s
    kill -USR1 "${sup_pid}" || { echo "error: could not signal supervisor (PID ${sup_pid})" >&2; return 1; }

    sleep 2
    local pid
    pid=$(cat "${K3S_PID}" 2>/dev/null || true)
    echo "k3s ${label} started (PID ${pid:-?}); node-ip=${MY_IP}; logs=${LOG}"
}

require_ip() {
    [ -n "${1:-}" ] || { echo "error: this mode needs a master IP" >&2; usage; exit 1; }
}

usage() {
    sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
}

case "${1:-}" in
    single)
        launch "single-node" server $(server_args)
        ;;
    master)
        launch "single-master" server $(server_args)
        FULL_TOKEN=$(cat "${DATA_DIR}/server/node-token" 2>/dev/null || echo "${TOKEN}")
        echo "Workers join with:"
        echo "  docker exec -e K3S_TOKEN='${FULL_TOKEN}' SAT-N k3s-ctl worker ${MY_IP}"
        ;;
    distributed-master)
        if [ -n "${2:-}" ]; then
            launch "ha-master (join ${2})" server --server="https://${2}:6443" $(server_args)
        else
            launch "ha-master (cluster-init)" server --cluster-init $(server_args)
            FULL_TOKEN=$(cat "${DATA_DIR}/server/node-token" 2>/dev/null || echo "${TOKEN}")
            echo "Add masters:"
            echo "  docker exec -e K3S_TOKEN='${FULL_TOKEN}' SAT-N k3s-ctl distributed-master ${MY_IP}"
            echo "Add workers:"
            echo "  docker exec -e K3S_TOKEN='${FULL_TOKEN}' SAT-N k3s-ctl worker ${MY_IP}"
        fi
        ;;
    worker)
        require_ip "${2:-}"
        launch "worker (join ${2})" agent \
            --server="https://${2}:6443" --token="${TOKEN}" \
            --node-ip="${MY_IP}" --flannel-iface="${IFACE}" --data-dir="${DATA_DIR}" \
            --snapshotter=native --kubelet-arg=cgroups-per-qos=false \
            --kubelet-arg=enforce-node-allocatable=
        ;;
    status)
        if is_running; then
            echo "k3s: running (PID $(pgrep -f "${K3S_BIN} " | head -1)), node-ip ${MY_IP}"
            "${K3S_BIN}" kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml get nodes 2>/dev/null \
                || echo "API not ready yet (give it ~30-60s)"
        else
            echo "k3s: stopped"
        fi
        ;;
    stop)
        echo "stopping k3s..."
        _sp=$(cat "${SUP_PID}" 2>/dev/null) && kill -USR2 "${_sp}" 2>/dev/null || kill_existing
        sleep 2
        echo "k3s stopped"
        ;;
    clean)
        echo "=== k3s clean: stop + wipe state ==="
        # 1. Stop k3s via supervisor (or fallback to direct kill)
        if is_running; then
            echo "  stopping k3s..."
            _sp=$(cat "${SUP_PID}" 2>/dev/null) && kill -USR2 "${_sp}" 2>/dev/null || kill_existing
            sleep 3
        else
            echo "  k3s not running"
        fi
        # 2. Force-kill anything still alive (containerd shim, etc.)
        pkill -9 -f "${K3S_BIN} "    2>/dev/null || true
        pkill -9 -f 'containerd-shim' 2>/dev/null || true
        sleep 1
        # 3. Wipe data dir (volume is kept, only contents removed)
        echo "  wiping ${DATA_DIR}..."
        rm -rf "${DATA_DIR:?}/"*
        # 4. Remove log and pid file
        rm -f "${LOG}" "${K3S_PID}" "${K3S_CMD}"
        # 5. Remove stale cgroupv2 hierarchy left by previous run.
        #    An "invalid state" cgroup causes pod scheduling failures on next start.
        if [ -d /sys/fs/cgroup/k8s.io ]; then
            echo "  removing stale /sys/fs/cgroup/k8s.io..."
            find /sys/fs/cgroup/k8s.io -depth -mindepth 1 -type d \
                -exec rmdir {} + 2>/dev/null || true
            rmdir /sys/fs/cgroup/k8s.io 2>/dev/null || true
        fi
        echo "=== clean done — safe to run k3s-ctl single/master/worker ==="
        ;;
    *)
        usage
        ;;
esac
