#!/bin/bash
# Container supervisor — PID 1.
#
# Manages sshd and (optionally) k3s. k3s is launched as a direct child of this
# supervisor so it lives in the container's main cgroup, not in a transient
# docker-exec cgroup. This is what lets k3s survive after `docker exec` exits.
#
# Control API (used by k3s-ctl):
#   Write args (one per line) to /run/k3s-cmd, then send SIGUSR1  → start k3s
#   Send SIGUSR2                                                    → stop  k3s

K3S_BIN=/usr/local/bin/k3s
K3S_PID=/run/k3s.pid
K3S_LOG=/var/log/k3s.log
K3S_CMD=/run/k3s-cmd
SUP_PID=/run/supervisor.pid

[ -e /dev/kmsg ] || ln -s /dev/null /dev/kmsg 2>/dev/null || true

_start_k3s() {
    if [ ! -f "$K3S_CMD" ]; then
        echo "supervisor: k3s-cmd not found — nothing to start" >&2
        return
    fi
    # Read args (one per line) into an array, then remove the command file
    mapfile -t k3s_args < "$K3S_CMD"
    rm -f "$K3S_CMD"
    # Stop any existing k3s before launching.
    # Trailing space in the pattern prevents matching "k3s-ctl" (which also
    # contains "/usr/local/bin/k3s" as a substring).
    pkill -f "${K3S_BIN} " 2>/dev/null || true
    pkill -f 'containerd-shim' 2>/dev/null || true
    sleep 1
    # Launch k3s as a child of this supervisor — fully outside any exec cgroup
    "$K3S_BIN" "${k3s_args[@]}" >>"$K3S_LOG" 2>&1 </dev/null &
    echo $! > "$K3S_PID"
    echo "supervisor: k3s started (PID $!)"
}

_stop_k3s() {
    pkill -f "${K3S_BIN} " 2>/dev/null || true
    pkill -f 'containerd-shim' 2>/dev/null || true
    rm -f "$K3S_PID"
    echo "supervisor: k3s stopped"
}

trap _start_k3s USR1
trap _stop_k3s  USR2

# Start SSH daemon in background (supervisor stays as PID 1)
/usr/sbin/sshd &

# Write our PID so k3s-ctl can signal us
echo $$ > "$SUP_PID"
echo "supervisor: ready (PID $$)"

# Wait loop — traps fire here; restart sshd if it ever dies
while true; do
    wait || true
    pgrep -x sshd > /dev/null 2>&1 || /usr/sbin/sshd &
done
