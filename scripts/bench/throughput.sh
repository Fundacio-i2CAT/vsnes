#!/usr/bin/env bash
# throughput.sh — data-rate (Mbps) between two nodes using iperf3.
#
#   ./throughput.sh <SRC> <DST> [seconds] [--udp [BW]] [--port N]
#
# Runs an iperf3 server in DST and a client in SRC, parses the JSON result.
# TCP by default (capacity). --udp adds datagram-loss + jitter (BW default 100M).
#
# iperf3 is pre-installed in the vsnes-mesh image (docker/Dockerfile).
#
# Examples:
#   ./throughput.sh Ibi_ES SAT-1 10
#   ./throughput.sh SAT-1 SAT-7 10 --udp 50M
set -uo pipefail
. "$(dirname "$0")/lib.sh"

SRC="${1:?usage: throughput.sh <SRC> <DST> [seconds] [--udp [BW]] [--port N]}"
DST="${2:?usage: throughput.sh <SRC> <DST> [seconds] [--udp [BW]] [--port N]}"
shift 2
SECS=10; UDP=0; UDP_BW=100M; PORT=5201
while [ $# -gt 0 ]; do
    case "$1" in
        --udp)  UDP=1; case "${2:-}" in [0-9]*) UDP_BW="$2"; shift;; esac ;;
        --port) PORT="${2:?}"; shift ;;
        [0-9]*) SECS="$1" ;;
        *) die "unknown arg: $1" ;;
    esac
    shift
done

is_up "$SRC" || die "$SRC not running"
is_up "$DST" || die "$DST not running"
DST_IP=$(node_ip "$DST") || die "no IP for $DST"

ensure_iperf3 "$SRC" || die "iperf3 unavailable in client $SRC"
ensure_iperf3 "$DST" || die "iperf3 unavailable in server $DST"

log "starting iperf3 server in $DST on :$PORT"
inx "$DST" pkill -f "iperf3 -s -p $PORT" 2>/dev/null; sleep 0.3
inx "$DST" iperf3 -s -1 -p "$PORT" -D 2>/dev/null   # -D daemonises inside the container
# Wait until the server port is actually open (up to 5 s) before running the client.
for _i in 1 2 3 4 5 6 7 8 9 10; do
    inx "$DST" bash -c "echo '' >/dev/tcp/127.0.0.1/$PORT" 2>/dev/null && break
    sleep 0.5
done

cli=(iperf3 -c "$DST_IP" -p "$PORT" -t "$SECS" -J)
[ "$UDP" = 1 ] && cli+=(-u -b "$UDP_BW")
log "client $SRC -> $DST_IP  ($([ "$UDP" = 1 ] && echo "UDP $UDP_BW" || echo TCP), ${SECS}s)"
json=$(inx "$SRC" "${cli[@]}" 2>/dev/null) || die "iperf3 client failed (server up? path reachable?)"

# Parse without jq (not in image): pull end-summary fields with grep/sed.
get() { printf '%s\n' "$json" | grep -oE "\"$1\":[ ]*[0-9.eE+-]+" | tail -n1 | grep -oE '[0-9.eE+-]+$'; }
if [ "$UDP" = 1 ]; then
    bps=$(get bits_per_second); lost=$(get lost_packets); tot=$(get packets); jit=$(get jitter_ms)
    mbps=$(awk -v b="${bps:-0}" 'BEGIN{printf "%.2f", b/1e6}')
    lossp=$(awk -v l="${lost:-0}" -v t="${tot:-0}" 'BEGIN{ if(t>0) printf "%.2f", l/t*100; else print "NA"}')
    extra="udp,${jit:-NA},${lossp:-NA}"
    printf '\n  throughput = %s Mbps (UDP)\n  jitter=%s ms  datagram loss=%s%%\n' "$mbps" "${jit:-NA}" "${lossp:-NA}"
else
    bps=$(get bits_per_second); retr=$(get retransmits)
    mbps=$(awk -v b="${bps:-0}" 'BEGIN{printf "%.2f", b/1e6}')
    extra="tcp,${retr:-NA},NA"
    printf '\n  throughput = %s Mbps (TCP)\n  retransmits=%s\n' "$mbps" "${retr:-NA}"
fi

csv="$RESULTS_DIR/throughput_${RUN_STAMP}.csv"
[ -f "$csv" ] || echo "timestamp,proto,src,dst,dst_ip,secs,mbps,mode,retr_or_jitter,udp_loss_pct" >"$csv"
echo "$(date -Iseconds),$VS_PROTO,$SRC,$DST,$DST_IP,$SECS,$mbps,$extra" >>"$csv"
printf '  -> %s\n' "$csv"
