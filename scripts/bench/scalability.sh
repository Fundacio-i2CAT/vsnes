#!/usr/bin/env bash
# scalability.sh — Network reliability & scalability sweep.
#
#   ./scalability.sh [count_per_pair] [node ...]
#
# Probes every ordered pair among the target nodes and aggregates delivery and
# delay into a single reliability snapshot for the *current* network size. All
# pairs run in parallel so the sweep completes in one probe-window rather than
# pairs × window. Re-run as you scale the constellation up to see how mean PDR
# and RTT degrade with density — that trend is the scalability result.
#
#   --quick  5 probes per pair (faster; use for interactive checks)
#
# Examples:
#   ./scalability.sh                       # all running SATs
#   ./scalability.sh 20 SAT-1 SAT-2 SAT-3 SAT-4
#   ./scalability.sh --quick
set -uo pipefail
. "$(dirname "$0")/lib.sh"

COUNT=20
case "${1:-}" in
    --quick) COUNT=5; shift ;;
    [0-9]*)  COUNT="$1"; shift ;;
esac
NODES=("$@"); [ ${#NODES[@]} -eq 0 ] && mapfile -t NODES < <(sat_nodes)
N=${#NODES[@]}
[ "$N" -ge 2 ] || die "need >=2 nodes"

log "scalability sweep: $N nodes, $COUNT probes/pair, $((N*(N-1))) ordered pairs (parallel)"

pair_csv="$RESULTS_DIR/scalability_pairs_${RUN_STAMP}.csv"
[ -f "$pair_csv" ] || echo "timestamp,proto,n_nodes,src,dst,pdr_pct,rtt_avg_ms" >"$pair_csv"

TMPDIR_PAIRS=$(mktemp -d)
cleanup() { rm -rf "$TMPDIR_PAIRS"; }
trap cleanup EXIT

# Launch all pairs in parallel.
for s in "${NODES[@]}"; do
    is_up "$s" || continue
    for d in "${NODES[@]}"; do
        [ "$s" = "$d" ] && continue
        is_up "$d" || continue
        (
            dip=$(node_ip "$d") || exit 0
            read -r sent recv loss _ ravg _ _ <<<"$(ping_stats "$s" "$dip" "$COUNT" 0.1)"
            pdr=$(awk -v sv="$sent" -v r="$recv" \
                'BEGIN{ if(sv>0) printf "%.2f", r/sv*100; else print "0" }')
            printf '%s %s %s %s %s %s\n' "$s" "$d" "$sent" "$recv" "$pdr" "${ravg:-NA}" \
                >"$TMPDIR_PAIRS/${s}__${d}"
        ) &
    done
done

# Progress bar while waiting.
total_pairs=$((N*(N-1))); done_pairs=0
while [ "$done_pairs" -lt "$total_pairs" ]; do
    done_pairs=$(ls "$TMPDIR_PAIRS" 2>/dev/null | wc -l)
    printf '\r  probing pairs: %d/%d' "$done_pairs" "$total_pairs" >&2
    sleep 0.5
done
wait
printf '\n' >&2

# Collect results.
sum_pdr=0; sum_rtt=0; reach=0; pairs=0
for f in "$TMPDIR_PAIRS"/*; do
    [ -f "$f" ] || continue
    read -r s d sent recv pdr ravg <"$f"
    echo "$(date -Iseconds),$VS_PROTO,$N,$s,$d,$pdr,$ravg" >>"$pair_csv"
    pairs=$((pairs+1))
    sum_pdr=$(awk -v a="$sum_pdr" -v b="$pdr" 'BEGIN{print a+b}')
    if [ "$ravg" != "NA" ] && [ "${recv:-0}" -gt 0 ] 2>/dev/null; then
        reach=$((reach+1))
        sum_rtt=$(awk -v a="$sum_rtt" -v b="$ravg" 'BEGIN{print a+b}')
    fi
done

mean_pdr=$(awk -v s="$sum_pdr" -v p="$pairs" \
    'BEGIN{ if(p>0) printf "%.2f", s/p; else print "0" }')
mean_rtt=$(awk -v s="$sum_rtt" -v r="$reach" \
    'BEGIN{ if(r>0) printf "%.3f", s/r; else print "NA" }')
conn=$(awk -v r="$reach" -v p="$pairs" \
    'BEGIN{ if(p>0) printf "%.1f", r/p*100; else print "0" }')

sum_csv="$RESULTS_DIR/scalability_summary_${RUN_STAMP}.csv"
[ -f "$sum_csv" ] || echo "timestamp,proto,n_nodes,pairs,mean_pdr_pct,connectivity_pct,mean_rtt_ms" >"$sum_csv"
echo "$(date -Iseconds),$VS_PROTO,$N,$pairs,$mean_pdr,$conn,$mean_rtt" >>"$sum_csv"

printf '\n  nodes=%s pairs=%s\n' "$N" "$pairs"
printf '  mean PDR       = %s%%\n' "$mean_pdr"
printf '  connectivity   = %s%% of pairs reachable\n' "$conn"
printf '  mean RTT       = %s ms\n' "$mean_rtt"
printf '  -> %s\n  -> %s\n' "$sum_csv" "$pair_csv"
