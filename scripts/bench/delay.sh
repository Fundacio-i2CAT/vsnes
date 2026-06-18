#!/usr/bin/env bash
# delay.sh — End-to-End Delay / Round-Trip Delay (RTD) between two nodes.
#
#   ./delay.sh <SRC> <DST> [count] [interval]
#
# RTD is the ping RTT (min/avg/max/mdev). One-way end-to-end delay is reported
# as RTT_avg / 2 (a standard symmetric-path estimate). Results appended to CSV.
#
# Examples:
#   ./delay.sh Ibi_ES SAT-1
#   ./delay.sh SAT-1 SAT-7 50 0.2          # 50 probes, 5 Hz
set -uo pipefail
. "$(dirname "$0")/lib.sh"

SRC="${1:?usage: delay.sh <SRC> <DST> [count] [interval]}"
DST="${2:?usage: delay.sh <SRC> <DST> [count] [interval]}"
COUNT="${3:-30}"
INTERVAL="${4:-0.2}"

is_up "$SRC" || die "$SRC not running"
is_up "$DST" || die "$DST not running"
DST_IP=$(node_ip "$DST") || die "no IP for $DST"

log "RTD $SRC -> $DST ($DST_IP), $COUNT probes @ ${INTERVAL}s"
read -r sent recv loss rmin ravg rmax rmdev <<<"$(ping_stats "$SRC" "$DST_IP" "$COUNT" "$INTERVAL")"

owd=""
[ -n "$ravg" ] && owd=$(awk -v a="$ravg" 'BEGIN{printf "%.3f", a/2}')

csv="$RESULTS_DIR/delay_${RUN_STAMP}.csv"
[ -f "$csv" ] || echo "timestamp,proto,src,dst,dst_ip,count,recv,loss_pct,rtt_min_ms,rtt_avg_ms,rtt_max_ms,rtt_mdev_ms,owd_est_ms" >"$csv"
echo "$(date -Iseconds),$VS_PROTO,$SRC,$DST,$DST_IP,$sent,$recv,$loss,${rmin:-NA},${ravg:-NA},${rmax:-NA},${rmdev:-NA},${owd:-NA}" >>"$csv"

printf '\n  RTT  min/avg/max/mdev = %s/%s/%s/%s ms\n' "${rmin:-NA}" "${ravg:-NA}" "${rmax:-NA}" "${rmdev:-NA}"
printf '  one-way delay (est.)   = %s ms\n' "${owd:-NA}"
printf '  loss                   = %s%%\n' "$loss"
printf '  -> %s\n' "$csv"
