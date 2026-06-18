#!/usr/bin/env bash
# run-all.sh — run the full metric suite for one source/destination pair and a
# scalability snapshot, into a single timestamped results set.
#
#   ./run-all.sh [SRC] [DST]
#
# Defaults: SRC=ground station ($VS_GS), DST=SAT-1. Skips throughput if iperf3
# can't be provisioned. Convergence needs a multi-hop alternate path to be
# meaningful (see convergence.sh).
#
#   VS_PROTO=olsrd ./run-all.sh Ibi_ES SAT-1
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/lib.sh"

SRC="${1:-$VS_GS}"
DST="${2:-${VS_PREFIX}1}"
export RUN_STAMP   # share one timestamp across all sub-scripts

log "=== VSNES routing-metric suite  proto=$VS_PROTO  $SRC -> $DST  stamp=$RUN_STAMP ==="

log "--- [1/6] Round-trip / end-to-end delay ---";  "$HERE/delay.sh"      "$SRC" "$DST" 30 0.2  || true
log "--- [2/6] PDR / packet loss ---";              "$HERE/pdr.sh"        "$SRC" "$DST" 100 0.1 || true
log "--- [3/6] Throughput ---";                     "$HERE/throughput.sh" "$SRC" "$DST" 10      || log "throughput skipped"
log "--- [4/6] Routing overhead ---";               "$HERE/overhead.sh"   20                   || true
log "--- [5/6] Convergence / route repair ---";     "$HERE/convergence.sh" "$SRC" "$DST" 5 0.2  || true
log "--- [6/6] Reliability & scalability ---";       "$HERE/scalability.sh" 20                   || true

log "=== done. results in: $RESULTS_DIR (stamp $RUN_STAMP) ==="
ls -1 "$RESULTS_DIR"/*"$RUN_STAMP"* 2>/dev/null | sed 's/^/  /' >&2
