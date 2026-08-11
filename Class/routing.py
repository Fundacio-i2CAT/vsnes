#!/usr/bin/env python3
"""Routing-protocol registry for VSNES.

The emulator gates mesh routing daemons with per-pair firewall DROP rules so
each daemon only discovers in-LOS neighbours, and it owns the daemon lifecycle
(start after the rules are in place, restart on container restart, stop on
cleanup). Exactly ONE protocol is active per scenario, selected in the toml:

    [Routing]
        protocol = 'olsrd'    # or 'none' (netem shaping only, no daemon)

Adding a protocol = adding one RoutingProtocol entry here (plus support in the
node image's routing-ctl if it needs a daemon). Experimental QUIC/DTN routing
slot in the same way as new entries without touching Channel.py.

Adding a routing protocol
-------------------------
1. Teach the node image's `routing-ctl` to start/stop the daemon, e.g.
       routing-ctl start <svc>   /   routing-ctl off
   (a single `off` that stops every daemon keeps _sanitize_previous_gating
   able to switch protocols cleanly).
2. Add one RoutingProtocol(...) entry to PROTOCOLS below. It must define:
     - fw_bin     : iptables-legacy (IPv4) or ip6tables-legacy (IPv6). Use the
                    legacy (xtables) binary — Debian-12 nft mode fights Docker's
                    own nft rules.
     - chain      : a dedicated chain (VSNES_<PROTO>) so cleanup is one flush and
                    _sanitize_previous_gating can tear it down by iterating here.
     - match_mode : how a no-LOS peer is identified in the DROP rule —
                      'src_ip'  when the daemon's hellos carry a unique routable
                                source IP (e.g. OLSR broadcasts).
                      'src_mac' when the daemon speaks link-local IPv6 multicast
                                (e.g. babel's ff02::1:6) — the source IP is a
                                non-unique fe80:: link-local, so gate on the peer's
                                Ethernet source MAC instead (needs -m mac). Channel
                                discovers/derives the peer MACs automatically for
                                src_mac protocols.
     - gate_port  : UDP port of the hello/control traffic jumped into the chain.
     - start_cmd / stop_cmd : the routing-ctl invocations from step 1.
     - pre_start (optional) : idempotent shell run before start_cmd for image
                    quirks (config fixups etc.); leave '' if none.
3. That's the whole change — Channel.py is protocol-neutral and drives any entry.
   IPv6 src_mac protocols additionally need the host sysctl
   net.bridge.bridge-nf-call-ip6tables=0 so bridged IPv6 frames aren't eaten by
   the host ip6tables FORWARD policy (Scenario.write_bash already emits it).
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RoutingProtocol:
	name: str
	fw_bin: str        # firewall binary inside the node (iptables-legacy | ip6tables-legacy)
	chain: str         # dedicated chain, e.g. VSNES_OLSR — single flush cleanup
	match_mode: str    # 'src_ip' | 'src_mac' — how a no-LOS peer is identified
	gate_port: int     # UDP port of the protocol's hello/control traffic
	start_cmd: str     # daemon start (inside the node)
	stop_cmd: str      # daemon stop
	# Idempotent shell run before start_cmd (e.g. config fixups for quirks in
	# the baked image). Empty for protocols that need none.
	pre_start: str = ''
	# Optional shell template (with a {iface} placeholder) that points the
	# daemon at a non-default mesh interface. Containers mesh on eth0 (the
	# default), but VM constellations mesh on the VLAN subinterface
	# (e.g. enp1s0.3) — conf-file daemons (olsrd) need their Interface line
	# rewritten; env-driven ones (babel via routing-ctl's MESH_IFACE) don't.
	iface_fixup: str = ''

	# ── firewall rule builders (shell lines, batched into ONE exec/node) ──
	# All builders return plain shell lines; Channel concatenates every line
	# a node needs (sanitize + chain + all its pair rules + daemon) and runs
	# them in a single `docker exec <node> sh -c '<script>'`. Idempotence is
	# per-line (`|| true`) so one failing line never aborts the rest.
	def chain_setup_lines(self):
		'''Create the chain if missing, flush it, and (idempotently) jump the
		protocol's control traffic from INPUT into it.'''
		return [
			f'{self.fw_bin} -N {self.chain} 2>/dev/null || true',
			f'{self.fw_bin} -F {self.chain}',
			f'{self.fw_bin} -C INPUT -p udp --dport {self.gate_port} -j {self.chain} 2>/dev/null '
			f'|| {self.fw_bin} -I INPUT 1 -p udp --dport {self.gate_port} -j {self.chain}',
		]

	def pair_rule_line(self, action, peer_ip=None, peer_mac=None):
		'''One block/unblock rule for a no-LOS peer. action is -A or -D.
		-D on an absent rule must not fail the batch.'''
		if self.match_mode == 'src_ip':
			rule = f'{self.fw_bin} {action} {self.chain} -s {peer_ip} -j DROP'
		else:
			rule = f'{self.fw_bin} {action} {self.chain} -m mac --mac-source {peer_mac} -j DROP'
		return rule if action == '-A' else f'{rule} 2>/dev/null || true'

	def chain_teardown_lines(self):
		'''Unhook and delete the chain (safe if it never existed).'''
		return [
			f'{self.fw_bin} -D INPUT -p udp --dport {self.gate_port} -j {self.chain} 2>/dev/null || true',
			f'{self.fw_bin} -F {self.chain} 2>/dev/null || true',
			f'{self.fw_bin} -X {self.chain} 2>/dev/null || true',
		]

	# ── daemon lifecycle (shell lines, appended to the same batch) ────────
	def daemon_start_script(self, iface=None):
		'''Start the daemon; with iface, retarget it at that mesh interface
		(VM constellations mesh on the VLAN subinterface, not eth0).'''
		parts = [self.pre_start]
		start = self.start_cmd
		if iface:
			if self.iface_fixup:
				parts.append(self.iface_fixup.format(iface=iface))
			# routing-ctl reads MESH_IFACE (default eth0) for CLI-driven daemons.
			start = f'MESH_IFACE={iface} {start}'
		parts.append(start)
		return ' && '.join(p for p in parts if p)

	def daemon_stop_script(self):
		return f'{self.stop_cmd} 2>/dev/null || true'


PROTOCOLS = {
	'olsrd': RoutingProtocol(
		name='olsrd',
		fw_bin='iptables-legacy',   # Debian-12 nft mode conflicts with Docker's nft rules
		chain='VSNES_OLSR',
		match_mode='src_ip',        # OLSR hellos broadcast with a unique source IP
		gate_port=698,
		start_cmd='routing-ctl start olsrd',
		stop_cmd='routing-ctl off',
		# The image's baked olsrd.conf carries a LinkQualityWinSize line this
		# olsrd build rejects ("Config line 24: syntax error"); comment it out
		# before every start (idempotent, no-op once fixed).
		pre_start="sed -i 's/^LinkQualityWinSize/#LinkQualityWinSize/' /etc/olsrd/olsrd.conf",
		# olsrd binds the interface named in its conf — rewrite it when the
		# mesh interface isn't eth0 (VM constellations use the VLAN subif).
		iface_fixup='sed -i \'s/^Interface .*/Interface "{iface}"/\' /etc/olsrd/olsrd.conf',
	),
	'babel': RoutingProtocol(
		name='babel',
		fw_bin='ip6tables-legacy',  # babel is IPv6; legacy mode avoids Docker's nft
		chain='VSNES_BABEL',
		# babel speaks IPv6 link-local multicast (ff02::1:6) with a non-unique
		# fe80:: source, so IPv4/IPv6 src-IP gating can't tell peers apart — gate
		# on each peer's Ethernet source MAC instead. Requires the host sysctl
		# net.bridge.bridge-nf-call-ip6tables=0 (Scenario.write_bash emits it) so
		# bridged IPv6 frames aren't dropped by the host ip6tables FORWARD policy.
		match_mode='src_mac',
		# babeld binds its RFC-8966 default udp/6696 (Dockerfile EXPOSEs 6696/udp;
		# routing-ctl.sh start_babel passes no -c/port, so no override). NOT 698 —
		# that is OLSR's port; jumping the chain on 698 would never match babel
		# traffic and the MAC DROP rules would silently never fire.
		gate_port=6696,
		start_cmd='routing-ctl start babel',   # routing-ctl.sh: 'babel' (or 'babeld')
		stop_cmd='routing-ctl off',
		# No pre_start: babeld takes -C 'skip-kernel-setup true' on the CLI (see
		# docker/routing-ctl.sh start_babel), so there is no baked-config fixup.
	),
	# 'quic', 'dtn': planned experimental entries (see "Adding a routing protocol").
}


def get_protocol(name):
	'''Registry lookup. Returns None for "none" (valid: shaping only), raises
	for unknown names so config errors surface at load time, not mid-run.'''
	if name in (None, '', 'none'):
		return None
	try:
		return PROTOCOLS[name]
	except KeyError:
		raise ValueError(f"Unknown routing protocol '{name}' — "
		                 f"valid: none, {', '.join(sorted(PROTOCOLS))}")
