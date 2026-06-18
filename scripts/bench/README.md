# VSNES routing-protocol measurement suite

Scripts to evaluate a mesh routing protocol (OLSRd / Babel) running on the
VSNES Docker satellites. Everything works by `docker exec` into the running
containers, so the simulation can be live while you measure. Results are written
as CSV under `scripts/bench/results/`.

All scripts use what the container image actually ships (`ping`, `ip`,
`iptables-legacy`, `curl`) — **no tcpdump, no netcat required**. `iperf3` is the
only external need (throughput) and is auto-installed on demand where possible.

## The metrics

| Script | Metric | How it's measured |
|--------|--------|-------------------|
| `delay.sh`       | End-to-end delay / RTD            | `ping` RTT min/avg/max/mdev; one-way ≈ RTT/2 |
| `pdr.sh`         | Packet Delivery Ratio / loss      | `ping` sent vs received |
| `throughput.sh`  | Throughput (Mbps)                 | `iperf3` TCP (or `--udp` for loss+jitter) |
| `overhead.sh`    | Routing control overhead          | iptables packet/byte counters on UDP/698 (OLSR) or /6696 (Babel) |
| `convergence.sh` | Convergence / route-repair time   | break the active next hop, time the ping-stream outage |
| `scalability.sh` | Reliability & scalability         | all-pairs PDR + RTT aggregate; re-run at increasing node counts |
| `run-all.sh`     | everything                        | one pass for a SRC/DST pair + a scalability snapshot |

## Quick start

```bash
cd scripts/bench

# individual metrics (SRC and DST are container names)
./delay.sh        Ibi_ES SAT-1
./pdr.sh          Ibi_ES SAT-1 100 0.1
./throughput.sh   Ibi_ES SAT-1 10
./overhead.sh     20                       # 20 s window, all running SATs
./convergence.sh  SAT-1 SAT-7              # needs a multi-hop alternate path
./scalability.sh  20                       # all-pairs over running SATs

# full suite into one timestamped result set
./run-all.sh Ibi_ES SAT-1
```

## Choosing the protocol

The control-plane overhead measurement needs to know which daemon is running.
Default is OLSRd (UDP/698). For Babel (UDP/6696):

```bash
VS_PROTO=babel ./overhead.sh 20
VS_PROTO=babel ./run-all.sh  Ibi_ES SAT-1
```

Start/stop the daemons with the in-container helper (see `scripts/README.md`):

```bash
docker exec SAT-1 routing-ctl start olsrd     # or: start babel
```

## How each measurement works (and its caveats)

- **delay / pdr** — straightforward ICMP. For PDR of *application* traffic under
  load, use `throughput.sh --udp`, which reports datagram loss directly.

- **throughput** — runs a one-shot `iperf3 -s` in the destination and a client in
  the source. `iperf3` is pre-installed in the vsnes-mesh image. A near-bridge
  number (Gbps) means the sim isn't shaping that path; apply a contact/rate
  window to see netem take effect.

- **overhead** — installs *counting-only* iptables jumps (empty target chain, so
  packet flow is unchanged), samples packet/byte deltas over the window, and
  removes them on exit. **OUTPUT** counters per node = control traffic that node
  generates; the **sum of OUTPUT across all nodes** is the total routing overhead
  injected into the mesh — the headline number. Babel often uses IPv6
  link-local; if so, this IPv4 accounting under-counts — run Babel over IPv4 for
  a clean comparison.

- **convergence** — finds the current next hop from SRC to DST, then drops all
  traffic to/from that neighbour (data *and* its HELLOs, so the daemon detects
  the link loss and reroutes). The gap in the timestamped ping stream is the
  repair time. **Requires an alternate path** — on a flat single-hop bridge there
  is no second route, so you'll see a permanent outage. Run it with OLSRd
  topology sync (`VSNES_OLSR`) and real LOS constraints active so the mesh is
  genuinely multi-hop.

- **scalability** — one run aggregates all-pairs PDR/RTT for the *current* set of
  running satellites. The scalability *trend* comes from re-running it as you
  scale up: start more SATs (or tighten LOS / increase mobility) and compare the
  `scalability_summary_*.csv` rows across sizes.

## Output

CSV files in `results/`, one per metric per run, suffixed with a shared
timestamp. `run-all.sh` exports a single `RUN_STAMP` so all six land in the same
set. Columns are self-describing (header row included). `results/` is git-ignored.

## Tips

- Pin the comparison: run the **same** SRC/DST and window under OLSRd, then under
  Babel (`VS_PROTO=babel`), then diff the CSVs.
- For an apples-to-apples scalability curve, keep probe count/interval fixed and
  only vary the number of running satellites.
- These are safe to run live, but `convergence.sh` briefly blackholes one
  neighbour on the SRC node — it's reverted on exit (including Ctrl-C).
