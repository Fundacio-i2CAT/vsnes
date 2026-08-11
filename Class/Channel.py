#!/usr/bin/env python3
import subprocess
import threading
import logging
from concurrent.futures import ThreadPoolExecutor
from Class.Satellite import Satellite
from Class.routing import get_protocol
from czml import czml
import numpy as np
import json

# GLOBAL CONSTANTS
a_Earth = 6371000.0			 # Earth major semi axis [m]
c = 3e8						 # Speed of light [m/s]

# Precomputed constants
DEG_TO_RAD = np.pi / 180.0
RAD_TO_DEG = 180.0 / np.pi
C_INV_MS = 1000.0 / c		   # Precompute for delay calculation

TC_BATCH_FILE = '/tmp/batch_tc_update.txt'
POSITIONS_FILE = 'Positions/nodes.json'

class channel:
	'''A channel object defines the delays between nodes'''

	def __init__(self, channel):
		self._delay_matrix = []
		self._exist_channel = False
		self.channels = channel['Channel']
		# O(1) channel-definition lookup keyed by the unordered group pair.
		# Threshold is validated here (config-load time) instead of with an
		# interactive input() inside the simulation loop.
		self._def_map = {}
		for ch in self.channels:
			try:
				ch['Threshold'] = float(ch['Threshold'])
			except KeyError:
				raise ValueError(f"Channel {ch.get('Node1')}-{ch.get('Node2')}: missing 'Threshold'")
			except (TypeError, ValueError):
				raise ValueError(f"Channel {ch.get('Node1')}-{ch.get('Node2')}: invalid 'Threshold' value {ch.get('Threshold')!r}")
			self._def_map[frozenset((ch['Node1'], ch['Node2']))] = ch
		# Precomputed delay timeline: numpy array of shape (T, N, N), built by
		# precompute() once all nodes are loaded. None until then.
		self._delays = None
		# Last Data_rate applied per directed pair (set by write_bash at startup,
		# diffed at runtime to support dynamic rate changes). The timeline path
		# only re-scans rates when _rates_dirty is set (True initially so the
		# first tick records the baseline; see mark_rates_dirty()).
		self._applied_rates = {}
		self._rates_dirty = True
		# Names of nodes "killed" from the GUI. Every link touching a killed node
		# is forced to 100% loss next tick (the node is logically removed from the
		# matrix) while all other pairs keep working. Reversible via revive_node().
		self._killed = set()
		# Routing topology sync (see Class/routing.py): the active protocol and
		# the set of frozenset({n, j}) pairs currently blocked by its firewall
		# chain so the daemon only discovers in-range neighbours. Populated by
		# init_routing_rules() and updated each tick by update().
		self._proto = None
		self._routing_blocked_pairs = set()
		self._routing_enabled = False

	def kill_node(self, name):
		'''Logically remove a node: force all its links to 100% loss. Reversible.'''
		self._killed.add(name)

	def revive_node(self, name):
		'''Undo kill_node(): the node's real link delays resume next tick.'''
		self._killed.discard(name)

	def is_killed(self, name):
		return name in self._killed

	def AddNode(self, node_list, nNodes, marker):
		'''Add a new row and a new column to the matrix with one new node'''
		self._delays = None  # invalidate any precomputed timeline
		new_row = []
		for n in range(0, nNodes-1):
			delay = self._Define_Channel(node_list[n], node_list[nNodes-1], marker)
			if not self._exist_channel and delay > -1:
				self._exist_channel = True

			self._delay_matrix[n].append(delay)
			new_row.append(delay)

		new_row.append(-2)
		self._delay_matrix.append(new_row)

	def precompute(self, node_list, nNodes, n_markers):
		'''Precompute the full delay timeline delays[T][N][N] using vectorized
		numpy operations. Positions are already precomputed per node, so the
		whole contact-window calculation can be done once at scenario load.'''
		T = n_markers
		delays = np.full((T, nNodes, nNodes), -2.0)

		# Gather per-node position arrays once
		sat_eci = {}
		sat_ecef = {}
		for idx, node in enumerate(node_list):
			if isinstance(node, Satellite):
				sat_eci[idx] = np.asarray(node._ECI, dtype=float)	  # (T, 3)
				sat_ecef[idx] = np.asarray(node._ECEF, dtype=float)   # (T, 3)

		for i in range(nNodes):
			for j in range(i+1, nNodes):
				n1, n2 = node_list[i], node_list[j]
				Channel = self._Get_Channel_Definition(n1, n2)
				if Channel is None:
					continue
				threshold = Channel['Threshold']
				latency = Channel.get('Latency', 'True')
				is_sat_1 = i in sat_eci
				is_sat_2 = j in sat_eci

				if is_sat_1 and is_sat_2:
					series = self._Satellite2Satellite_vec(sat_eci[i], sat_eci[j], threshold)
				elif is_sat_1 != is_sat_2:
					sat_idx, gs = (i, n2) if is_sat_1 else (j, n1)
					min_el = Channel.get('Min_elevation_angle', 0) or 0
					series = self._GroundBase2Satellite_vec(
						sat_ecef[sat_idx], np.asarray(gs.get_ECEF(), dtype=float),
						gs.get_LLH(), float(min_el), threshold, latency)
				else:
					series = np.zeros(T)

				delays[:, i, j] = series
				delays[:, j, i] = series

		self._delays = delays
		logging.info(f"Delay timeline precomputed: {T} steps x {nNodes}x{nNodes} nodes")

	def update(self, node_list, nNodes, marker, EMU):
		# Snapshot of the previous state (real copy, not an alias) for diffing
		old_matrix = [row[:] for row in self._delay_matrix]
		script_lines = []
		routing_cmds = {}   # node -> [rule lines], flushed as 1 exec/node
		self._exist_channel = False

		node_cache = []
		for node in node_list:
			is_sat = isinstance(node, Satellite)
			# Docker containers use a pre-named IFB device (ifb<N>) set by
			# write_bash(); _get_Host_interface() returns it directly.  Classic
			# VMs return a base name (e.g. 'eth0') that Channel.update() extends
			# to 'eth0.N'.  The is_docker flag tells update() which path to use.
			iface_base = node._get_Host_interface()
			is_docker  = getattr(node, '_ifb_iface', None) is not None
			entry = {
				'obj': node,
				'name': node.name,
				'is_sat': is_sat,
				'interface_base': iface_base,
				'is_docker': is_docker,
				'eci': None,
				'ecef': None,
				'llh': None,
				'time': marker
			}
			if is_sat:
				entry['eci'] = node.get_ECI(marker)
				entry['ecef'] = node.get_ECEF(marker)
				entry['llh'] = node.get_POS(marker)
			else:
				entry['ecef'] = node.get_ECEF()
				entry['llh'] = node.get_LLH()
			node_cache.append(entry)

		self._write_positions(node_cache)

		use_timeline = self._delays is not None and marker < len(self._delays)

		if use_timeline:
			# Vectorized path: find the (typically few) changed pairs with one
			# numpy comparison instead of scanning all N² cells in Python.
			self._update_from_timeline(node_cache, node_list, nNodes, marker,
			                           EMU, old_matrix, script_lines, routing_cmds)
			if EMU and script_lines:
				self._batch_update_netem(script_lines)
			if EMU and routing_cmds:
				self._apply_node_scripts(
					{node: '\n'.join(lines) for node, lines in routing_cmds.items()})
			return

		for n in range(0, nNodes):
			node_n_data = node_cache[n]
			for j in range(0, nNodes):
				if old_matrix[n][j] == -2:
					continue
				if j < n:
					delay = self._delay_matrix[j][n]
				elif j > n:
					delay = self._calculate_delay_from_cache(node_n_data, node_cache[j])
				else:
					continue

				# Killed nodes: force every link touching them to 100% loss so the
				# node is effectively removed from the matrix, leaving all other
				# pairs untouched. The diff logic below emits the netem change on
				# the kill tick and restores the real delay on revive.
				if self._killed and (node_n_data['name'] in self._killed or node_cache[j]['name'] in self._killed):
					delay = -1

				if delay > -1 and not self._exist_channel:
					self._exist_channel = True

				# Traffic Control Logic: only emit a command when the value changed
				if EMU and old_matrix[n][j] != delay and n != j:
					interface = self._tc_iface(node_n_data, n)
					class_id = f"1:{j+1}"
					handle_id = f"1{j+1}:"

					if delay == -1:
						script_lines.append(f'qdisc change dev {interface} parent {class_id} handle {handle_id} netem loss 100%')
					elif delay != 0:
						Channel = self._Get_Channel_Definition(node_n_data['obj'], node_cache[j]['obj'])
						losses = f"{Channel['Packet_loss']}%"
						burst_losses = f"{Channel['Correlated_losses']}%"
						script_lines.append(f'qdisc change dev {interface} parent {class_id} handle {handle_id} netem delay {delay:f}ms loss {losses} {burst_losses}')

				# Dynamic Data_rate: re-shape the HTB class if the configured
				# rate differs from the one currently applied.
				if EMU and n != j:
					Channel = self._Get_Channel_Definition(node_n_data['obj'], node_cache[j]['obj'])
					if Channel is not None and 'Data_rate' in Channel:
						try:
							rate = float(Channel['Data_rate'])
						except (TypeError, ValueError):
							rate = None
						if rate is not None:
							applied = self._applied_rates.get((n, j))
							if applied is None:
								self._applied_rates[(n, j)] = rate
							elif applied != rate:
								iface_dr = self._tc_iface(node_n_data, n)
								script_lines.append(f'class change dev {iface_dr} parent 1: classid 1:{j+1} htb rate {rate:f}mbit')
								self._applied_rates[(n, j)] = rate

				# Routing topology sync: update firewall gating when LOS state changes.
				# Collect commands here; apply after the full matrix scan so we
				# don't fork iptables inside the inner loop.
				if EMU and old_matrix[n][j] != delay and n < j:
					self._sync_routing_pair(n, j, delay, node_list, routing_cmds)

				self._delay_matrix[n][j] = delay

		if EMU and script_lines:
			self._batch_update_netem(script_lines)
		if EMU and routing_cmds:
			self._apply_node_scripts(
				{node: '\n'.join(lines) for node, lines in routing_cmds.items()})

	def _update_from_timeline(self, node_cache, node_list, nNodes, marker,
	                          EMU, old_matrix, script_lines, routing_cmds):
		'''Per-tick matrix update when the precomputed delay timeline is
		available. Semantics match the scalar loop in update(): pairs whose
		previous value is -2 (no channel defined) are never touched, killed
		nodes force -1 on all their defined links, and tc/routing commands are
		emitted only for cells whose value actually changed.'''
		old_np = np.asarray(old_matrix, dtype=float)
		new_np = np.array(self._delays[marker], dtype=float, copy=True)

		if self._killed:
			kmask = np.fromiter((e['name'] in self._killed for e in node_cache),
			                    dtype=bool, count=nNodes)
			pair_kill = kmask[:, None] | kmask[None, :]
			new_np = np.where(pair_kill, -1.0, new_np)

		# Undefined pairs (old == -2) keep their old value forever.
		new_np = np.where(old_np == -2, old_np, new_np)
		self._exist_channel = bool((new_np > -1).any())

		if EMU:
			for n, j in np.argwhere(new_np != old_np):
				n, j = int(n), int(j)
				if n == j:
					continue
				delay = float(new_np[n][j])
				node_n_data = node_cache[n]
				interface = self._tc_iface(node_n_data, n)
				class_id = f"1:{j+1}"
				handle_id = f"1{j+1}:"
				if delay == -1:
					script_lines.append(f'qdisc change dev {interface} parent {class_id} handle {handle_id} netem loss 100%')
				elif delay != 0:
					Channel = self._Get_Channel_Definition(node_n_data['obj'], node_cache[j]['obj'])
					losses = f"{Channel['Packet_loss']}%"
					burst_losses = f"{Channel['Correlated_losses']}%"
					script_lines.append(f'qdisc change dev {interface} parent {class_id} handle {handle_id} netem delay {delay:f}ms loss {losses} {burst_losses}')
				if n < j:
					self._sync_routing_pair(n, j, delay, node_list, routing_cmds)

			# Data_rate reconciliation: rates never change unless something
			# calls mark_rates_dirty(), so the full O(N²) definition scan the
			# scalar loop pays every tick runs here only when flagged (and
			# once at start, to record the baseline applied by write_bash).
			if self._rates_dirty:
				for n in range(nNodes):
					for j in range(nNodes):
						if n == j:
							continue
						Channel = self._Get_Channel_Definition(node_cache[n]['obj'], node_cache[j]['obj'])
						if Channel is None or 'Data_rate' not in Channel:
							continue
						try:
							rate = float(Channel['Data_rate'])
						except (TypeError, ValueError):
							continue
						applied = self._applied_rates.get((n, j))
						if applied is None:
							self._applied_rates[(n, j)] = rate
						elif applied != rate:
							script_lines.append(f'class change dev {self._tc_iface(node_cache[n], n)} parent 1: classid 1:{j+1} htb rate {rate:f}mbit')
							self._applied_rates[(n, j)] = rate
				self._rates_dirty = False

		self._delay_matrix = new_np.tolist()

	def mark_rates_dirty(self):
		'''Signal that a channel Data_rate was mutated at runtime: the next
		tick re-scans all pair definitions and re-shapes changed HTB classes.'''
		self._rates_dirty = True

	@staticmethod
	def _mac_from_ip(ip_str):
		'''Reproduce generate_docker_compose's pinned-MAC convention
		(02:42:<o1>:<o2>:02:<o4>, octets hex) from a node's ip_ext. Used as a
		fallback when a live get_docker_mac() lookup fails, so src_mac gating
		(babel) still has a peer MAC to DROP on. Returns None on a bad IP.'''
		try:
			o = ip_str.split('.')
			return f"02:42:{int(o[0]):02x}:{int(o[1]):02x}:02:{int(o[3]):02x}"
		except Exception:
			return None

	@staticmethod
	def _tc_iface(node_data, n):
		'''Resolve the host tc interface for a node. Docker containers shape on
		a pre-named IFB device (ifb<N>, already in interface_base); classic VMs
		shape on the VLAN sub-interface eth0.<n+1>.'''
		base = node_data['interface_base']
		return base if node_data['is_docker'] else f"{base}.{n+1}"

	def _write_positions(self, node_cache):
		'''Write current node positions for the per-node position API.
		One compact file per tick; the web server serves it to node VMs.'''
		try:
			data = []
			for entry in node_cache:
				data.append({
					'name': entry['name'],
					'marker': entry['time'],
					'llh': [float(v) for v in entry['llh']] if entry['llh'] is not None else None,
					'ecef': [float(v) for v in entry['ecef']] if entry['ecef'] is not None else None,
				})
			with open(POSITIONS_FILE, 'w') as file:
				json.dump(data, file)
		except Exception as e:
			logging.error(f'Error writing node positions to {POSITIONS_FILE}: {e}')

	def _calculate_delay_from_cache(self, n1_data, n2_data):
		"""Helper to calculate delay using pre-calculated coordinates"""
		Channel = self._Get_Channel_Definition(n1_data['obj'], n2_data['obj'])
		if Channel is None:
			return -2

		threshold = Channel['Threshold']
		latency = Channel.get('Latency', 'True')
		min_el = float(Channel.get('Min_elevation_angle', 0) or 0)
		if n1_data['is_sat'] and n2_data['is_sat']:
			return float(self._Satellite2Satellite(n1_data['eci'], n2_data['eci'], threshold))
		elif not n1_data['is_sat'] and n2_data['is_sat']:
			return float(self._GroundBase2Satellite(n2_data['ecef'], n1_data['ecef'], n1_data['llh'], min_el, threshold, latency))
		elif n1_data['is_sat'] and not n2_data['is_sat']:
			return float(self._GroundBase2Satellite(n1_data['ecef'], n2_data['ecef'], n2_data['llh'], min_el, threshold, latency))
		else:
			return self._GroundBase2GroundBase()

	# ── Routing topology sync ────────────────────────────────────────────────
	# Gates the SELECTED routing protocol (Class/routing.py registry) with
	# firewall rules INSIDE each Docker container (via docker exec) so its
	# daemon only discovers in-LOS neighbours. Each container gets one
	# dedicated chain (e.g. VSNES_OLSR) jumped from INPUT, so cleanup is a
	# single flush rather than per-rule deletes — and only the active
	# protocol's rules exist, never two protocols' rules at once.

	def init_routing_rules(self, node_list, nNodes, protocol_name):
		'''Gate the selected routing protocol: create its firewall chain inside
		every container, install DROP rules for all no-LOS pairs, then start
		the daemon (rules FIRST so there is no discovery-leak window). Exactly
		one protocol's rules are ever installed. protocol_name='none' -> no-op
		(netem shaping only). Called by write_bash().'''
		docker_nodes = [nd for nd in node_list
		                if getattr(nd, 'ip_ext', None) and nd.is_container]
		# Internal VMs mesh over per-node VLAN subinterfaces on brSATEMU: the
		# host-side netem (loss 100% on no-LOS pairs) already gates their
		# hellos, so VMs get NO firewall rules — only the daemon lifecycle,
		# delivered over SSH via the same exec_shell transport.
		vm_nodes = [nd for nd in node_list if getattr(nd, 'node_type', '') == 'vm']
		total = len(docker_nodes)
		proto = get_protocol(protocol_name)

		if proto is None:
			# 'none': just remove any previous protocol's gating — one batched
			# sanitize exec per node, in parallel.
			logging.info("Routing: protocol 'none' — removing any previous gating "
			             "(no rules, no daemon)")
			sanitize = '\n'.join(self._sanitize_lines())
			self._apply_node_scripts({nd: sanitize for nd in docker_nodes + vm_nodes})
			return

		self._proto = proto
		self._routing_blocked_pairs = set()
		self._routing_node_list = node_list

		# Peer MACs are only needed for src_mac-gated protocols (e.g. babel).
		self._node_macs = {}
		if proto.match_mode == 'src_mac':
			for idx, nd in enumerate(node_list):
				if getattr(nd, 'ip_ext', None) and nd.is_container:
					mac = None
					try:
						mac = nd.get_docker_mac()
					except Exception:
						mac = None
					# Fallback: containers get a deterministic MAC pinned by
					# generate_docker_compose, so if the live lookup fails (e.g.
					# container not up yet) we can derive it from ip_ext.
					self._node_macs[idx] = mac or self._mac_from_ip(nd.ip_ext)

		# Pre-compute each node's blocked peers so the whole setup — sanitize
		# of any previous protocol, chain creation, ALL of the node's DROP
		# rules, and the daemon start (last, so the exit code reflects it and
		# a booting daemon can never discover an out-of-LOS neighbour) — is
		# ONE `docker exec sh -c` per node, run in parallel. At 64 nodes this
		# replaces thousands of serial execs with 64 parallel ones.
		by_node = {}
		for n in range(nNodes):
			for j in range(n + 1, nNodes):
				delay = self._delay_matrix[n][j]
				# -1 = no LOS now; -2 = pair has NO channel definition, which
				# must mean "no link, ever" — without a permanent DROP their
				# broadcast hellos leak past the per-MAC tc filters and the
				# daemons form phantom adjacencies (e.g. GS-GS, observed as
				# fake 1-hop OLSR neighbours between all ground stations).
				# -2 pairs never change state, so the rule installed here is
				# permanent: update()/_sync_routing_pair() skip -2 by design.
				if delay >= 0:
					continue
				self._register_pair('-A', n, j, node_list, by_node)
		blocked_peers = {nd.name: by_node.get(nd, []) for nd in docker_nodes}

		scripts = {}
		for nd in docker_nodes:
			lines = self._sanitize_lines()
			lines += proto.chain_setup_lines()
			lines += blocked_peers[nd.name]
			lines.append(proto.daemon_start_script())
			scripts[nd] = '\n'.join(lines)
		for nd in vm_nodes:
			# daemon retargeted at the VM's mesh VLAN (e.g. enp1s0.3); netem
			# on the bridge does the LOS gating, so no chain/rules here.
			iface = f"{nd._VM_interface}.{nd._nodeNumber}"
			scripts[nd] = '\n'.join(
				[proto.daemon_stop_script(), proto.daemon_start_script(iface=iface)])

		n_rules = sum(len(v) for v in blocked_peers.values())
		logging.info(f"Routing[{proto.name}]: applying chain + {n_rules} DROP rules "
		             f"+ daemon in {total} containers"
		             + (f" + daemon in {len(vm_nodes)} VMs" if vm_nodes else "")
		             + " (1 exec each, parallel)...")
		failed = self._apply_node_scripts(scripts, warn_on_error=True)
		self._routing_enabled = True
		logging.info(f"Routing[{proto.name}]: topology sync enabled; "
		             f"{len(self._routing_blocked_pairs)} pairs blocked"
		             + (f"; {failed} node script(s) reported errors" if failed else ""))
		self._start_routing_event_watcher()

	@staticmethod
	def _sanitize_lines():
		'''Shell lines removing every registered protocol's chain and stopping
		every routing daemon. Idempotent (each line || true); prepended to the
		per-node setup script so switching protocol between runs can never
		leave two protocols' rules behind.'''
		from Class.routing import PROTOCOLS
		lines = []
		for p in PROTOCOLS.values():
			lines += p.chain_teardown_lines()
		for stop in {p.daemon_stop_script() for p in PROTOCOLS.values()}:
			lines.append(stop)
		return lines

	def _apply_node_scripts(self, per_node, warn_on_error=False, timeout=60):
		'''Run each node's batched script in PARALLEL (ThreadPoolExecutor)
		through node.exec_shell — docker exec for containers, SSH for VMs.
		per_node maps node OBJECT -> script. This is the only way
		firewall/daemon commands reach nodes — never one exec per rule.
		Returns the number of nodes whose script exited non-zero.'''
		if not per_node:
			return 0
		def _run(item):
			node, script = item
			rc, out = node.exec_shell(script, timeout=timeout)
			if rc != 0:
				msg = out[:300]
				if warn_on_error:
					logging.warning(f"routing[{node.name}]: script exit {rc}: {msg}")
				else:
					logging.debug(f"routing[{node.name}]: {msg}")
				return 1
			return 0
		with ThreadPoolExecutor(max_workers=min(16, len(per_node))) as ex:
			return sum(ex.map(_run, per_node.items()))

	def cleanup_routing_rules(self):
		'''Stop the daemon and remove the active protocol's chain from every
		container. Safe to call even if init_routing_rules() never ran.'''
		if not self._routing_enabled:
			return
		proto = self._proto
		self._routing_enabled = False  # signal watcher thread to stop
		proc = getattr(self, '_routing_watcher_proc', None)
		if proc:
			try:
				proc.terminate()
			except Exception:
				pass
		node_list = getattr(self, '_routing_node_list', [])
		script = '\n'.join([proto.daemon_stop_script()] + proto.chain_teardown_lines())
		per_node = {node: script for node in node_list
		            if getattr(node, 'ip_ext', None) and node.is_container}
		per_node.update({node: proto.daemon_stop_script() for node in node_list
		                 if getattr(node, 'node_type', '') == 'vm'})
		self._apply_node_scripts(per_node)
		self._routing_blocked_pairs = set()
		logging.info(f"Routing[{proto.name}]: topology sync disabled; chain and daemon removed")

	def _register_pair(self, action, n, j, node_list, out):
		'''Record the (n, j) LOS transition and append the two per-node rule
		LINES (one inside each endpoint) to `out` ({node: [lines]}).
		The lines are batched with everything else headed to that node into a
		single exec — 2 rule lines per pair, never 2 processes per pair.'''
		proto = self._proto
		node_n = node_list[n]
		node_j = node_list[j]
		ip_n = getattr(node_n, 'ip_ext', None)
		ip_j = getattr(node_j, 'ip_ext', None)
		if not (ip_n and ip_j):
			return
		macs = getattr(self, '_node_macs', {})
		if proto.match_mode == 'src_mac' and not (macs.get(n) and macs.get(j)):
			return
		pair = frozenset((n, j))
		# Inside node-n: drop protocol traffic arriving from node-j (and vice versa)
		out.setdefault(node_n, []).append(
			proto.pair_rule_line(action, peer_ip=ip_j, peer_mac=macs.get(j)))
		out.setdefault(node_j, []).append(
			proto.pair_rule_line(action, peer_ip=ip_n, peer_mac=macs.get(n)))
		if action == '-A':
			self._routing_blocked_pairs.add(pair)
		else:
			self._routing_blocked_pairs.discard(pair)

	def _sync_routing_pair(self, n, j, new_delay, node_list, out):
		'''Append the rule lines reflecting the new delay for (n,j) to `out`
		({node: [lines]}). Only acts when the pair crosses the
		LOS/no-LOS boundary; update() flushes `out` as one exec per changed
		node after the full matrix scan.'''
		if not self._routing_enabled:
			return
		if self._delay_matrix[n][j] == -2:
			return  # pair not defined — skip
		pair = frozenset((n, j))
		should_block = new_delay < 0
		is_blocked   = pair in self._routing_blocked_pairs
		if should_block == is_blocked:
			return
		action = '-A' if should_block else '-D'
		self._register_pair(action, n, j, node_list, out)

	def _reinit_container_routing(self, n, node, node_list):
		'''Re-install the chain, all current block rules, AND the routing
		daemon for a single container. Called automatically when a container
		restart is detected by the event watcher (a restarted container loses
		both its firewall rules and its daemon).'''
		proto = self._proto
		name = node.name
		if not (getattr(node, 'ip_ext', None) and node.is_container):
			return
		macs = getattr(self, '_node_macs', {})
		lines = proto.chain_setup_lines()
		n_rules = 0
		for j, peer in enumerate(node_list):
			if j == n:
				continue
			if frozenset((n, j)) in self._routing_blocked_pairs:
				ip_peer = getattr(peer, 'ip_ext', None)
				if proto.match_mode == 'src_ip' and ip_peer:
					lines.append(proto.pair_rule_line('-A', peer_ip=ip_peer))
					n_rules += 1
				elif proto.match_mode == 'src_mac' and macs.get(j):
					lines.append(proto.pair_rule_line('-A', peer_mac=macs.get(j)))
					n_rules += 1
		lines.append(proto.daemon_start_script())
		failed = self._apply_node_scripts({node: '\n'.join(lines)}, warn_on_error=True)
		logging.info(f"Routing[{proto.name}]: {name} restarted — rules + daemon "
		             f"restored ({n_rules} block(s))"
		             + ("; script reported errors" if failed else ""))

	def _start_routing_event_watcher(self):
		'''Spawn a daemon thread that watches `docker events` for container
		start events. When a managed container restarts, its firewall chain and
		routing daemon are re-applied automatically so the topology is never
		stale and the mesh never silently loses a router.'''
		def _watch():
			proc = subprocess.Popen(
				['docker', 'events',
				 '--filter', 'type=container',
				 '--filter', 'event=start',
				 '--format', '{{.Actor.Attributes.name}}'],
				stdout=subprocess.PIPE, text=True
			)
			self._routing_watcher_proc = proc
			try:
				for line in proc.stdout:
					if not self._routing_enabled:
						break
					name = line.strip()
					node_list = getattr(self, '_routing_node_list', [])
					for i, node in enumerate(node_list):
						if node.name == name and node.is_container:
							self._reinit_container_routing(i, node, node_list)
							break
			except Exception as exc:
				if self._routing_enabled:
					logging.warning(f"routing event watcher: {exc}")

		threading.Thread(target=_watch, daemon=True, name='routing-event-watcher').start()

	# ─────────────────────────────────────────────────────────────────────────

	def _batch_update_netem(self, script_lines):
		'''Apply all tc changes of this tick in a single `tc -batch` call.
		-force keeps applying the remaining commands if one fails (a single
		bad line must not desynchronize the rest of the emulated channels).'''
		try:
			with open(TC_BATCH_FILE, 'w') as f:
				f.write('\n'.join(script_lines) + '\n')
			proc = subprocess.run(['sudo', 'tc', '-force', '-batch', TC_BATCH_FILE],
								  capture_output=True, text=True)
			if proc.returncode != 0 or proc.stderr:
				logging.error(f"tc batch update reported errors: {proc.stderr.strip()}")
		except Exception as e:
			logging.error(f"Failed to run tc batch update: {e}")

	def possible_channels(self):
		channels = []
		rows = len(self._delay_matrix)
		for n in range(rows):
			for j in range(n+1, rows):
				if self._delay_matrix[n][j] > -1:
					channels.append(f'{n}/{j}')
		return channels

	def delete(self):
		self.cleanup_routing_rules()
		self._delay_matrix = []
		self._exist_channel = False
		self._delays = None
		self._applied_rates = {}

	def get_channel(self, node1=None, node2=None):
		if node1 is None and node2 is None:
			return self._delay_matrix
		elif node2 is None:
			return self._delay_matrix[node1]
		elif node1 is None:
			return [row[node2] for row in self._delay_matrix]
		return self._delay_matrix[node1][node2]

	def get_exist(self):
		return self._exist_channel

	def _Define_Channel(self, node, other, marker):
		"""Non-cached single-pair delay (used at node-add time and as fallback)"""
		Channel = self._Get_Channel_Definition(node, other)
		if Channel is None:
			return -2

		is_sat_1 = isinstance(node, Satellite)
		is_sat_2 = isinstance(other, Satellite)
		latency = Channel.get('Latency', 'True')
		min_el = float(Channel.get('Min_elevation_angle', 0) or 0)

		if is_sat_1 and is_sat_2:
			return float(self._Satellite2Satellite(node.get_ECI(marker), other.get_ECI(marker), Channel['Threshold']))
		elif not is_sat_1 and is_sat_2:
			return float(self._GroundBase2Satellite(other.get_ECEF(marker), node.get_ECEF(), node.get_LLH(), min_el, Channel['Threshold'], latency))
		elif is_sat_1 and not is_sat_2:
			return float(self._GroundBase2Satellite(node.get_ECEF(marker), other.get_ECEF(), other.get_LLH(), min_el, Channel['Threshold'], latency))
		else:
			return self._GroundBase2GroundBase()

	def _Get_Channel_Definition(self, node1, node2):
		return self._def_map.get(frozenset((node1.group, node2.group)))

	def _ECEF2NED(self, pseudoDistance, LLH):
		x, y, z = pseudoDistance[0], pseudoDistance[1], pseudoDistance[2]
		lat = LLH[0] * DEG_TO_RAD
		long = LLH[1] * DEG_TO_RAD

		sin_lat = np.sin(lat)
		cos_lat = np.cos(lat)
		sin_lon = np.sin(long)
		cos_lon = np.cos(long)

		N = -sin_lat*cos_lon*x - sin_lat*sin_lon*y + cos_lat*z
		E = -sin_lon*x + cos_lon*y
		D = -cos_lat*cos_lon*x - cos_lat*sin_lon*y - sin_lat*z

		return np.array([N, E, D])

	def _NED2AzimuthElevationDistance(self, NED):
		d = np.linalg.norm(NED)

		if d == 0:
			return 0.0, 0.0, 0.0

		alpha = np.arctan2(NED[1], NED[0]) * RAD_TO_DEG
		beta = np.arcsin(-NED[2] / d) * RAD_TO_DEG
		return alpha, beta, d

	def _GroundBase2GroundBase(self):
		return 0
	def _GroundBase2Satellite(self,ECEF_SAT,ECEF_GB,LLH_GB,Min,threshold, Latency):
		p = ECEF_SAT-ECEF_GB
		NED = self._ECEF2NED(p,LLH_GB)
		alpha,beta,d = self._NED2AzimuthElevationDistance(NED)

		if (beta >= Min) and d < threshold:
			if (Latency == 'False'): delay = 0
			else: delay = d * C_INV_MS
		else:
			delay = -1

		return delay

	def _Satellite2Satellite(self, ECI1, ECI2, threshold):
		Er = a_Earth
		norm1 = np.linalg.norm(ECI1)

		if norm1 < Er:
			return -1

		theta = np.arcsin(Er / norm1)

		diff_vec = ECI1 - ECI2
		diff_norm = np.linalg.norm(diff_vec)

		ECI1_norm = ECI1 / norm1
		diff_vec_norm = diff_vec / diff_norm
		diff_vec_norm = np.nan_to_num(diff_vec_norm, nan=0.0)

		dot_res = np.dot(diff_vec_norm, ECI1_norm)
		diff_angle = np.arccos(np.abs(dot_res))

		if diff_angle > theta and threshold > diff_norm:
			return diff_norm * C_INV_MS
		elif threshold > diff_norm:
			distance_tangent_point = norm1 * np.cos(theta)
			if diff_norm > distance_tangent_point:
				return -1
			else:
				return diff_norm * C_INV_MS
		else:
			return -1

	# --- Vectorized variants operating on the whole timeline at once ---

	def _Satellite2Satellite_vec(self, ECI1, ECI2, threshold):
		'''Vectorized version of _Satellite2Satellite. ECI1/ECI2: (T,3) arrays.
		Returns delays array of shape (T,). Replicates the scalar logic exactly.'''
		norm1 = np.linalg.norm(ECI1, axis=1)						 # (T,)
		theta = np.arcsin(np.clip(a_Earth / np.maximum(norm1, 1e-9), -1.0, 1.0))

		diff_vec = ECI1 - ECI2
		diff_norm = np.linalg.norm(diff_vec, axis=1)				 # (T,)

		with np.errstate(invalid='ignore', divide='ignore'):
			ECI1_unit = ECI1 / norm1[:, None]
			diff_unit = np.nan_to_num(diff_vec / diff_norm[:, None], nan=0.0)
		dot_res = np.abs(np.einsum('ij,ij->i', diff_unit, ECI1_unit))
		diff_angle = np.arccos(np.clip(dot_res, -1.0, 1.0))

		delay_val = diff_norm * C_INV_MS
		in_threshold = threshold > diff_norm
		tangent_dist = norm1 * np.cos(theta)

		result = np.where(
			(diff_angle > theta) & in_threshold,
			delay_val,
			np.where(in_threshold & (diff_norm <= tangent_dist), delay_val, -1.0)
		)
		# Below Earth surface -> no contact
		result = np.where(norm1 < a_Earth, -1.0, result)
		return result

	def _GroundBase2Satellite_vec(self, ECEF_SAT, ECEF_GB, LLH_GB, Min, threshold, Latency):
		'''Vectorized version of _GroundBase2Satellite. ECEF_SAT: (T,3) array.
		Returns delays array of shape (T,).'''
		p = ECEF_SAT - ECEF_GB[None, :]							  # (T,3)
		lat = LLH_GB[0] * DEG_TO_RAD
		lon = LLH_GB[1] * DEG_TO_RAD
		sin_lat, cos_lat = np.sin(lat), np.cos(lat)
		sin_lon, cos_lon = np.sin(lon), np.cos(lon)

		x, y, z = p[:, 0], p[:, 1], p[:, 2]
		D = -cos_lat*cos_lon*x - cos_lat*sin_lon*y - sin_lat*z
		d = np.linalg.norm(p, axis=1)
		with np.errstate(invalid='ignore', divide='ignore'):
			beta = np.where(d > 0, np.arcsin(np.clip(-D / np.maximum(d, 1e-9), -1.0, 1.0)) * RAD_TO_DEG, 0.0)

		visible = (beta >= Min) & (d < threshold)
		delay_val = 0.0 if Latency == 'False' else d * C_INV_MS
		return np.where(visible, delay_val, -1.0)

	def czml_channels(self, datetime_vector, node1, node2, idx1=None, idx2=None):
		ID = f'{node1.name}-to-{node2.name}'
		name = f'{node1.name} to {node2.name}'

		channel = czml.CZMLPacket(id=ID, name=name)
		polyline = czml.Polyline()
		polyline.show = []

		last_change = datetime_vector[0].isoformat()

		Any_channel = False
		StrDescription = "<h2>Access times</h2><table class='sky-infoBox-access-table'><tr><th>Start</th><th>End</th>"

		# Reuse the precomputed timeline when available — avoids recomputing
		# every pairwise delay a second time during CZML generation.
		use_timeline = self._delays is not None and idx1 is not None and idx2 is not None
		if use_timeline:
			series = self._delays[:, idx1, idx2]
			previous_delay = series[0]
		else:
			previous_delay = self._Define_Channel(node1, node2, 0)

		if previous_delay != -2:

			for marker in range(1, len(datetime_vector)):
				dt = datetime_vector[marker]
				dt_iso = dt.isoformat()
				delay = series[marker] if use_timeline else self._Define_Channel(node1, node2, marker)

				if delay != -1 and previous_delay == -1:
					show = {"interval": f"{last_change}/{dt_iso}", "boolean": False}
					polyline.show.append(show)
					last_change = dt_iso
				elif delay == -1 and previous_delay != -1:
					show = {"interval": f"{last_change}/{dt_iso}", "boolean": True}

					start_t = last_change.split('+')[0].replace('T', ' ')
					end_t = dt_iso.split('+')[0].replace('T', ' ')

					StrDescription += f"<tr><td>{start_t}</td><td>{end_t}</td></tr>"
					polyline.show.append(show)
					last_change = dt_iso
					Any_channel = True
				elif marker == len(datetime_vector) - 1 and delay != -1:
					show = {"interval": f"{last_change}/{dt_iso}", "boolean": True}

					start_t = last_change.split('+')[0].replace('T', ' ')
					end_t = dt_iso.split('+')[0].replace('T', ' ')

					StrDescription += f"<tr><td>{start_t}</td><td>{end_t}</td></tr></table>"
					Any_channel = True
					polyline.show.append(show)
				elif marker == len(datetime_vector) - 1 and delay == -1:
					show = {"interval": f"{last_change}/{dt_iso}", "boolean": False}
					polyline.show.append(show)

				previous_delay = delay

		if Any_channel:
			description = czml.Description(StrDescription)
			color = czml.Color()
			color.rgba = [0, 255, 0, 255]
			solidColor = czml.SolidColor()
			solidColor.color = color
			material = czml.Material()
			material.solidColor = solidColor

			references = [f'{node1.name}#position', f'{node2.name}#position']
			position = czml.Positions(references=references)

			polyline.positions = position
			polyline.material = material
			polyline.width = 1
			polyline.followSurface = False
			channel.polyline = polyline
			channel.description = description
			return channel
		return None
