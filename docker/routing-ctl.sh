#!/bin/bash
# routing-ctl — start/stop the OLSR (olsrd) or Babel (babeld) routing daemon
# on this node.
#
#   routing-ctl start   {olsrd|babel}
#   routing-ctl stop    {olsrd|babel}
#   routing-ctl restart {olsrd|babel}
#   routing-ctl off                     (mesh off: stop both daemons)
#   routing-ctl status
#
# olsrd and babeld both install routes into the kernel table, so running them
# at the same time would fight over the FIB. Starting one therefore stops the
# other first. Override the mesh interface with MESH_IFACE (default eth0).

set -u

IFACE="${MESH_IFACE:-eth0}"
OLSRD_CONF="${OLSRD_CONF:-/etc/olsrd/olsrd.conf}"
BABELD_PID="/run/babeld.pid"

usage() {
    echo "usage: routing-ctl {start|stop|restart|status} [olsrd|babel]" >&2
    exit 1
}

is_running() { pgrep -x "$1" >/dev/null 2>&1; }

stop_one() {
    if is_running "$1"; then
        pkill -x "$1" && echo "$1 stopped"
    else
        echo "$1 not running"
    fi
}

# Keep olsrd.conf's LoadPlugin line in sync with the plugin filename that was
# actually compiled into this image (the .so carries a version suffix).
sync_txtinfo_plugin() {
    local so
    so=$(ls /usr/lib/olsrd_txtinfo.so.* 2>/dev/null | head -n1)
    [ -n "$so" ] || return 0
    so=$(basename "$so")
    sed -i "s|^LoadPlugin \"olsrd_txtinfo.so[^\"]*\"|LoadPlugin \"$so\"|" "$OLSRD_CONF"
}

start_olsrd() {
    is_running olsrd && { echo "olsrd already running"; return 0; }
    is_running babeld && { echo "babeld is running — stopping it first"; stop_one babeld; sleep 1; }
    sync_txtinfo_plugin
    # Interface comes from olsrd.conf (Interface "eth0"); -d 0 => daemonize.
    olsrd -f "$OLSRD_CONF" -d 0
    sleep 1
    if is_running olsrd; then
        echo "olsrd started on $IFACE (txtinfo on tcp/2006)"
    else
        echo "olsrd failed to start" >&2; return 1
    fi
}

start_babel() {
    is_running babeld && { echo "babeld already running"; return 0; }
    is_running olsrd && { echo "olsrd is running — stopping it first"; stop_one olsrd; sleep 1; }
    # -D => daemonize, -I => pidfile, -g => local monitoring server (tcp/33123).
    # skip-kernel-setup: don't touch /proc/sys (read-only inside the container,
    # which babeld otherwise treats as a fatal kernel_setup error).
    # Monitor binds to IPv6 localhost; query with:
    #   exec 3<>/dev/tcp/::1/33123; cat <&3
    babeld -D -I "$BABELD_PID" -g 33123 -C 'skip-kernel-setup true' "$IFACE"
    sleep 1
    if is_running babeld; then
        echo "babeld started on $IFACE (monitor on [::1]:33123)"
    else
        echo "babeld failed to start" >&2; return 1
    fi
}

status() {
    for d in olsrd babeld; do
        is_running "$d" && echo "$d: running" || echo "$d: stopped"
    done
    echo "--- ip route ---"
    ip route
}

cmd="${1:-}"
svc="${2:-}"

case "$cmd" in
    start)
        case "$svc" in
            olsrd)        start_olsrd ;;
            babel|babeld) start_babel ;;
            *) usage ;;
        esac ;;
    stop)
        case "$svc" in
            olsrd)        stop_one olsrd ;;
            babel|babeld) stop_one babeld ;;
            *) usage ;;
        esac ;;
    restart)
        case "$svc" in
            olsrd)        stop_one olsrd;  sleep 1; start_olsrd ;;
            babel|babeld) stop_one babeld; sleep 1; start_babel ;;
            *) usage ;;
        esac ;;
    off)
        stop_one olsrd
        stop_one babeld
        echo "mesh off" ;;
    status) status ;;
    *) usage ;;
esac
