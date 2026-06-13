#!/usr/bin/env python3
import subprocess
import logging
from Class.Satellite import Satellite
from czml import czml
import numpy as np
import json
from enum import IntEnum

# GLOBAL CONSTANTS
a_Earth = 6371000.0			 # Earth major semi axis [m]
c = 3e8						 # Speed of light [m/s]

# Precomputed constants
DEG_TO_RAD = np.pi / 180.0
RAD_TO_DEG = 180.0 / np.pi
C_INV_MS = 1000.0 / c		   # Precompute for delay calculation

TC_BATCH_FILE = '/tmp/batch_tc_update.txt'
POSITIONS_FILE = 'Positions/nodes.json'

class ChannelState(IntEnum):
	NO_LOS = -1
	DIAGONAL = -2
	VALID = 0

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
		# diffed at runtime to support dynamic rate changes).
		self._applied_rates = {}
		# Names of nodes "killed" from the GUI. Every link touching a killed node
		# is forced to 100% loss next tick (the node is logically removed from the
		# matrix) while all other pairs keep working. Reversible via revive_node().
		self._killed = set()

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

		for n in range(0, nNodes):
			node_n_data = node_cache[n]
			for j in range(0, nNodes):
				if old_matrix[n][j] == -2:
					continue
				if use_timeline:
					delay = float(self._delays[marker][n][j])
				elif j < n:
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
					if node_n_data['is_docker']:
						# IFB name already encodes the node index (e.g. ifb2)
						interface = node_n_data['interface_base']
					else:
						interface = f"{node_n_data['interface_base']}.{n+1}"
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
								if node_n_data['is_docker']:
									iface_dr = node_n_data['interface_base']
								else:
									iface_dr = f"{node_n_data['interface_base']}.{n+1}"
								script_lines.append(f'class change dev {iface_dr} parent 1: classid 1:{j+1} htb rate {rate:f}mbit')
								self._applied_rates[(n, j)] = rate

				self._delay_matrix[n][j] = delay

		if EMU and script_lines:
			self._batch_update_netem(script_lines)

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
