#!/usr/bin/env bash
# lib.sh — shared helpers for the VSNES routing-protocol measurement suite.
#
# Source this from the metric scripts:  . "$(dirname "$0")/lib.sh"
#
# Everything runs against the live Docker containers via `docker exec`, so the
# sim can be running while you measure. The only scripts that mutate state are
# overhead.sh (adds counting-only iptables rules) and convergence.sh (adds a
# temporary DROP); both clean up after themselves.

set -uo pipefail

# ── Tunables (override via env) ──────────────────────────────────────────────
VS_PREFIX="${VS_PREFIX:-SAT-}"          # satellite container name prefix
VS_GS="${VS_GS:-Ibi_ES}"                # ground-station container name
VS_NET_HINT="${VS_NET_HINT:-172.27.}"   # pick the bridge IP that starts with this
VS_PROTO="${VS_PROTO:-olsrd}"           # olsrd | babel  (selects the control port)
VS_TXTINFO_PORT="${VS_TXTINFO_PORT:-2006}"

# Control-plane UDP port per daemon (for routing-overhead accounting).
ctrl_port() {
    case "${1:-$VS_PROTO}" in
        olsrd|olsr) echo 698  ;;
        babel|babeld) echo 6696 ;;
        *) echo 698 ;;
    esac
}

# ── Results directory ────────────────────────────────────────────────────────
BENCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${RESULTS_DIR:-$BENCH_DIR/results}"
RUN_STAMP="${RUN_STAMP:-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$RESULTS_DIR"

log()  { printf '%s %s\n' "$(date +%H:%M:%S)" "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

# ── Node / IP helpers ────────────────────────────────────────────────────────

# Resolve a container's bridge IP (the 172.27.x address OLSRd routes on).
node_ip() {
    local name="$1" ip
    ip=$(docker inspect "$name" \
        --format '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' \
        2>/dev/null) || return 1
    for a in $ip; do
        case "$a" in "$VS_NET_HINT"*) echo "$a"; return 0;; esac
    done
    # Fallback: first non-empty address.
    set -- $ip; [ -n "${1:-}" ] && { echo "$1"; return 0; }
    return 1
}

# Is a container running?
is_up() { [ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null)" = true ]; }

# List running satellite containers, numerically sorted (SAT-1..SAT-12).
sat_nodes() {
    docker ps --format '{{.Names}}' \
        | grep -E "^${VS_PREFIX}[0-9]+$" \
        | sort -t- -k2 -n
}

# Run a command inside a container.
inx() { docker exec "$@"; }

# Confirm a tool exists in a container.
has_tool() { inx "$1" sh -c "command -v $2 >/dev/null 2>&1"; }

# Ensure iperf3 is present in a container.
# The vsnes-mesh image ships it; older containers may need it installed on demand.
ensure_iperf3() {
    local n="$1"
    has_tool "$n" iperf3 && return 0
    log "iperf3 missing in $n — installing via apt-get (needs network)..."
    if inx "$n" sh -c 'apt-get update -qq && apt-get install -y -qq iperf3' >/dev/null 2>&1; then
        has_tool "$n" iperf3 && { log "iperf3 installed in $n"; return 0; }
    fi
    die "iperf3 unavailable in $n — rebuild the image (docker/Dockerfile already includes it)"
}

# ── Ping → parse: prints  'sent recv loss_pct rtt_min rtt_avg rtt_max rtt_mdev'
# RTT fields are ms; loss_pct is a number without the % sign. Unreachable → loss 100.
ping_stats() {
    local src="$1" dst_ip="$2" count="${3:-20}" interval="${4:-0.2}"
    local out
    out=$(inx "$src" ping -n -q -c "$count" -i "$interval" -W 1 "$dst_ip" 2>/dev/null)
    local sent recv loss rmin ravg rmax rmdev
    sent=$(printf '%s\n' "$out" | grep -oE '[0-9]+ packets transmitted' | grep -oE '^[0-9]+')
    recv=$(printf '%s\n' "$out" | grep -oE '[0-9]+ received'            | grep -oE '^[0-9]+')
    loss=$(printf '%s\n' "$out" | grep -oE '[0-9]+(\.[0-9]+)?% packet loss' | grep -oE '^[0-9.]+')
    local rttline
    rttline=$(printf '%s\n' "$out" | grep -E 'rtt|round-trip')
    if [ -n "$rttline" ]; then
        # rtt min/avg/max/mdev = 1.234/2.345/3.456/0.456 ms
        IFS=/ read -r rmin ravg rmax rmdev <<<"$(echo "$rttline" | sed -E 's#.*= ##; s# ms##')"
    fi
    echo "${sent:-0} ${recv:-0} ${loss:-100} ${rmin:-} ${ravg:-} ${rmax:-} ${rmdev:-}"
}

# txtinfo query via curl (olsrd_txtinfo answers HTTP GET on :2006).
# usage: txtinfo <node> <neigh|links|routes|topology>
txtinfo() {
    inx "$1" curl -s "http://127.0.0.1:${VS_TXTINFO_PORT}/$2" 2>/dev/null
}

# Count kernel routes installed by the mesh daemon (rough route-table size).
route_count() { inx "$1" ip route 2>/dev/null | grep -c . ; }
