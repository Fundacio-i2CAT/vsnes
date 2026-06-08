#!/bin/bash
# k3s-join.sh — Join a k3s HA cluster
#
# Usage:
#   As master:  sudo /opt/k3s/k3s-join.sh master <SERVER_IP> [TOKEN]
#   As worker:  sudo /opt/k3s/k3s-join.sh worker <SERVER_IP> [TOKEN]
#   Init first: sudo /opt/k3s/k3s-join.sh init [TOKEN]
#
# Environment variables:
#   K3S_TOKEN     — cluster token (default: satnet-ha-2026)
#   K3S_IFACE     — flannel interface (default: eth0)
#   K3S_DATA_DIR  — data directory (default: /var/lib/rancher/k3s)

TOKEN="${K3S_TOKEN:-satnet-ha-2026}"
IFACE="${K3S_IFACE:-eth0}"
DATA_DIR="${K3S_DATA_DIR:-/var/lib/rancher/k3s}"
MY_IP="$(ip -4 addr show ${IFACE} | grep -oP '(?<=inet )\S+' | cut -d/ -f1)"
K3S_BIN="/opt/k3s/k3s"
LOG="/tmp/k3s.log"

# Common server args
COMMON_ARGS="--token=${TOKEN} --flannel-iface=${IFACE} --data-dir=${DATA_DIR} --write-kubeconfig-mode=644 --snapshotter=native --kubelet-arg=cgroups-per-qos=false --kubelet-arg=enforce-node-allocatable="

ensure_kmsg() {
    sudo rm -f /dev/kmsg 2>/dev/null || true
    sudo ln -s /dev/null /dev/kmsg 2>/dev/null || true
}

kill_existing() {
    pkill -f "${K3S_BIN}" 2>/dev/null || true
    sleep 2
}

case "${1}" in
    init)
        echo "=== Initializing k3s HA cluster (first master) ==="
        ensure_kmsg
        kill_existing
        nohup ${K3S_BIN} server \
            --cluster-init \
            --tls-san=${MY_IP} \
            ${COMMON_ARGS} \
            >> ${LOG} 2>&1 &
        echo "k3s master-init started (PID $!), logging to ${LOG}"
        echo "Wait ~60s then run: kubectl get nodes"
        ;;

    master)
        SERVER="${2:?Usage: k3s-join.sh master <SERVER_IP> [TOKEN]}"
        [ -n "${3}" ] && TOKEN="${3}"
        echo "=== Joining k3s cluster as master (server: ${SERVER}) ==="
        ensure_kmsg
        kill_existing
        nohup ${K3S_BIN} server \
            --server=https://${SERVER}:6443 \
            --tls-san=${MY_IP} \
            ${COMMON_ARGS} \
            >> ${LOG} 2>&1 &
        echo "k3s master-join started (PID $!), logging to ${LOG}"
        ;;

    worker)
        SERVER="${2:?Usage: k3s-join.sh worker <SERVER_IP> [TOKEN]}"
        [ -n "${3}" ] && TOKEN="${3}"
        echo "=== Joining k3s cluster as worker (server: ${SERVER}) ==="
        ensure_kmsg
        kill_existing
        nohup ${K3S_BIN} agent \
            --server=https://${SERVER}:6443 \
            --token=${TOKEN} \
            --flannel-iface=${IFACE} \
            --data-dir=${DATA_DIR} \
            --snapshotter=native \
            --kubelet-arg=cgroups-per-qos=false \
            --kubelet-arg=enforce-node-allocatable= \
            >> ${LOG} 2>&1 &
        echo "k3s worker-join started (PID $!), logging to ${LOG}"
        ;;

    status)
        if pgrep -f "${K3S_BIN}" > /dev/null; then
            echo "k3s is running (PID: $(pgrep -f ${K3S_BIN} | head -1))"
            ${K3S_BIN} kubectl --kubeconfig /etc/rancher/k3s/k3s.yaml get nodes 2>/dev/null || echo "API not ready yet"
        else
            echo "k3s is NOT running"
        fi
        ;;

    stop)
        echo "Stopping k3s..."
        kill_existing
        echo "k3s stopped."
        ;;

    *)
        echo "k3s-join.sh — Join or initialize a k3s HA cluster"
        echo ""
        echo "Usage:"
        echo "  sudo /opt/k3s/k3s-join.sh init [TOKEN]           — Initialize first master"
        echo "  sudo /opt/k3s/k3s-join.sh master <IP> [TOKEN]    — Join as master"
        echo "  sudo /opt/k3s/k3s-join.sh worker <IP> [TOKEN]    — Join as worker"
        echo "  sudo /opt/k3s/k3s-join.sh status                 — Check status"
        echo "  sudo /opt/k3s/k3s-join.sh stop                   — Stop k3s"
        echo ""
        echo "Defaults: TOKEN=satnet-ha-2026, IFACE=eth0"
        ;;
esac
