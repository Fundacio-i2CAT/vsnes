#!/usr/bin/env bash
# pdr.sh — Packet Delivery Ratio (PDR) and Packet Loss Rate between two nodes.
#
#   ./pdr.sh <SRC> <DST> [count] [interval]
#
#   PDR (%)        = received / sent * 100
#   Loss rate (%)  = 100 - PDR
#
# Uses ICMP echo as the probe stream. For an application-traffic PDR under load,
# pair this with throughput.sh --udp (iperf3 UDP reports datagram loss directly).
#
# Examples:
#   ./pdr.sh Ibi_ES SAT-1 100 0.1         # 100 probes at 10 Hz
set -uo pipefail
. "$(dirname "$0")/lib.sh"

SRC="${1:?usage: pdr.sh <SRC> <DST> [count] [interval]}"
DST="${2:?usage: pdr.sh <SRC> <DST> [count] [interval]}"
COUNT="${3:-100}"
INTERVAL="${4:-0.1}"

is_up "$SRC" || die "$SRC not running"
is_up "$DST" || die "$DST not running"
DST_IP=$(node_ip "$DST") || die "no IP for $DST"

log "PDR $SRC -> $DST ($DST_IP), $COUNT probes @ ${INTERVAL}s"
read -r sent recv loss _ _ _ _ <<<"$(ping_stats "$SRC" "$DST_IP" "$COUNT" "$INTERVAL")"

pdr=$(awk -v s="$sent" -v r="$recv" 'BEGIN{ if(s>0) printf "%.2f", r/s*100; else print "0.00" }')

csv="$RESULTS_DIR/pdr_${RUN_STAMP}.csv"
[ -f "$csv" ] || echo "timestamp,proto,src,dst,dst_ip,sent,recv,pdr_pct,loss_pct" >"$csv"
echo "$(date -Iseconds),$VS_PROTO,$SRC,$DST,$DST_IP,$sent,$recv,$pdr,$loss" >>"$csv"

printf '\n  sent=%s recv=%s\n' "$sent" "$recv"
printf '  PDR        = %s%%\n' "$pdr"
printf '  loss rate  = %s%%\n' "$loss"
printf '  -> %s\n' "$csv"
