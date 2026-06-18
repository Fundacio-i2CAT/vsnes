#!/usr/bin/env bash
# convergence.sh — Convergence / route-repair time after an active link breaks.
#
#   ./convergence.sh <SRC> <DST> [warmup_s] [probe_interval]
#
# Method: run a continuous, timestamped ping SRC->DST; once a route exists, break
# the *current next hop* on SRC (drop all traffic to/from that neighbour, which
# also cuts its HELLOs so the daemon detects link loss and reroutes). Measure the
# outage gap in the ping stream = time for the protocol to install an alternate
# route. The break is reverted and all temp rules removed on exit.
#
# Needs a topology with an alternate path (multi-hop mesh). On a flat single-hop
# bridge there is no second path, so you'll see a permanent outage — run this
# with OLSRd topology sync (VSNES_OLSR) active and real LOS constraints.
#
# Examples:
#   ./convergence.sh SAT-1 SAT-7
#   ./convergence.sh Ibi_ES SAT-5 5 0.2
set -uo pipefail
. "$(dirname "$0")/lib.sh"

SRC="${1:?usage: convergence.sh <SRC> <DST> [warmup_s] [probe_interval]}"
DST="${2:?usage: convergence.sh <SRC> <DST> [warmup_s] [probe_interval]}"
WARMUP="${3:-5}"
IVAL="${4:-0.2}"
IPT=iptables-legacy

is_up "$SRC" || die "$SRC not running"
is_up "$DST" || die "$DST not running"
DST_IP=$(node_ip "$DST") || die "no IP for $DST"

PINGLOG=$(mktemp); NEXTHOP=""
cleanup() {
    [ -n "${PING_PID:-}" ] && kill "$PING_PID" 2>/dev/null
    inx "$SRC" pkill -f "ping -n -D .* $DST_IP" 2>/dev/null
    if [ -n "$NEXTHOP" ]; then
        inx "$SRC" $IPT -D OUTPUT -d "$NEXTHOP" -j DROP 2>/dev/null
        inx "$SRC" $IPT -D INPUT  -s "$NEXTHOP" -j DROP 2>/dev/null
    fi
    rm -f "$PINGLOG"
}
trap cleanup EXIT

# Start timestamped, gap-reporting ping (-D unix ts, -O 'no answer' lines).
log "starting continuous ping $SRC -> $DST_IP"
inx "$SRC" ping -n -D -O -i "$IVAL" -W 1 "$DST_IP" >"$PINGLOG" 2>/dev/null &
PING_PID=$!
sleep "$WARMUP"

# Determine the active next hop from SRC toward DST.
route=$(inx "$SRC" ip route get "$DST_IP" 2>/dev/null)
NEXTHOP=$(printf '%s' "$route" | grep -oE 'via [0-9.]+' | awk '{print $2}')
if [ -z "$NEXTHOP" ]; then
    log "WARNING: $DST_IP is directly connected from $SRC (no via hop)."
    log "There is no alternate route to repair to — measuring a direct-link break."
    NEXTHOP="$DST_IP"
fi
log "current next hop = $NEXTHOP"

# Break the link: drop everything to/from the next hop (data + its HELLOs).
T_BREAK=$(date +%s.%N)
inx "$SRC" $IPT -I OUTPUT 1 -d "$NEXTHOP" -j DROP
inx "$SRC" $IPT -I INPUT  1 -s "$NEXTHOP" -j DROP
log "link broken at $T_BREAK — waiting for reconvergence…"

# Wait until ping recovers (a reply with ts > T_BREAK) or timeout.
MAXWAIT=60; t_recover=""
for _ in $(seq 1 $((MAXWAIT*5))); do
    line=$(grep 'bytes from' "$PINGLOG" | tail -n1)
    ts=$(printf '%s' "$line" | grep -oE '^\[[0-9.]+\]' | tr -d '[]')
    if [ -n "$ts" ] && awk -v a="$ts" -v b="$T_BREAK" 'BEGIN{exit !(a>b+0.05)}'; then
        t_recover="$ts"; break
    fi
    sleep 0.2
done

if [ -z "$t_recover" ]; then
    log "no recovery within ${MAXWAIT}s — no alternate path, or convergence too slow."
    conv="NA"
else
    conv=$(awk -v r="$t_recover" -v b="$T_BREAK" 'BEGIN{printf "%.3f", r-b}')
    log "recovered at $t_recover"
fi

csv="$RESULTS_DIR/convergence_${RUN_STAMP}.csv"
[ -f "$csv" ] || echo "timestamp,proto,src,dst,dst_ip,broken_nexthop,t_break_epoch,t_recover_epoch,convergence_s" >"$csv"
echo "$(date -Iseconds),$VS_PROTO,$SRC,$DST,$DST_IP,$NEXTHOP,$T_BREAK,${t_recover:-NA},$conv" >>"$csv"

printf '\n  broke next hop : %s\n' "$NEXTHOP"
printf '  convergence    : %s s\n' "$conv"
printf '  -> %s\n' "$csv"
