#!/usr/bin/env python3
import subprocess
from Class.Satellite import Satellite
from skyfield.api import load
from czml import czml
import time
import numpy as np
import json
from enum import IntEnum

# GLOBAL CONSTANTS
a_Earth = 6371000.0			 # Earth major semi axis [m]
c = 3e8						 # Speed of light [m/s]
ts = load.timescale()

# Precomputed constants
DEG_TO_RAD = np.pi / 180.0
RAD_TO_DEG = 180.0 / np.pi
C_INV_MS = 1000.0 / c		   # Precompute for delay calculation

class ChannelState(IntEnum):
	NO_LOS = -1
	DIAGONAL = -2
	VALID = 0

class channel:
	'''A channel object defines the delays between node'''
	_delay_matrix = None
	_exist_channel = None
	
	def __init__(self, channel):
		self._delay_matrix = []
		self._exist_channel = False
		self.channels = channel['Channel']

	def AddNode(self, node_list, nNodes, marker):
		'''Add a new row and a new to the matrix with one new node'''
		new_row = []
		for n in range(0, nNodes-1):
			delay = self._Define_Channel(node_list[n], node_list[nNodes-1], marker)
			if not self._exist_channel and delay > -1:
				self._exist_channel = True
			
			self._delay_matrix[n].append(delay)
			new_row.append(delay)
		
		new_row.append(-2)
		self._delay_matrix.append(new_row)

	def update(self, node_list, nNodes, marker, EMU):
		old_matrix = self._delay_matrix
		script_lines = ['#!/bin/bash', 'set -e']
		self._exist_channel = False
		delay = 0.0

		node_cache = []
		for node in node_list:
			is_sat = isinstance(node, Satellite)
			
			# Cache structure
			entry = {
				'obj': node,
				'name': node.name,
				'is_sat': is_sat,
				'interface_base': node._get_Host_interface(), # Cache string op
				'eci': None,
				'ecef': None,
				'llh': None,
				'time'	: marker
			}

			if is_sat:
				# Satellites require the time marker
				entry['eci'] = node.get_ECI(marker)
				entry['ecef'] = node.get_ECEF(marker)
				entry['llh'] = node.get_POS(marker)
			else:
				# Ground Stations are static (no marker needed)
				entry['ecef'] = node.get_ECEF()
				entry['llh'] = node.get_LLH()
			
			node_cache.append(entry)
		# --- OPTIMIZATION END ---
		position_file = f'Positions/nodes.json'
		try:
			with open(position_file,'w') as file:
				json.dump(node_cache, file, default=str, indent=4)
		except Exception as e:
			print(f'Error writing node positions to {position_file}: {e}')

		for n in range(0, nNodes):
			# Access cached data for Node N
			node_n_data = node_cache[n]
			
			for j in range(0, nNodes):
				if old_matrix[n][j] != -2: 
					if j < n :
						delay = self._delay_matrix[j][n]
					elif j > n:
						# Use optimized helper with cached data
						node_j_data = node_cache[j]
						delay = self._calculate_delay_from_cache(node_n_data, node_j_data)
						
						if delay > -1 and not self._exist_channel:
							self._exist_channel = True
					
					# Traffic Control Logic
					if EMU and old_matrix[n][j] != delay and n != j:
						# Use cached interface name
						interface = f"{node_n_data['interface_base']}.{n+1}"
						class_id = f"1:{j+1}"
						handle_id = f"1{j+1}:"

						if delay == -1:
							cmd = f'sudo tc qdisc change dev {interface} parent {class_id} handle {handle_id} netem loss 100%'
						elif delay != 0:
							# We still need the definition for loss parameters
							Channel = self._Get_Channel_Definition(node_n_data['obj'], node_cache[j]['obj'])
							
							str_delay = f'{delay:f}ms'
							losses = f"{Channel['Packet_loss']}%"
							burst_losses = f"{Channel['Correlated_losses']}%"
							
							cmd = f'sudo tc qdisc change dev {interface} parent {class_id} handle {handle_id} netem delay {str_delay} loss {losses} {burst_losses}'
						
						script_lines.append(cmd)
						
					self._delay_matrix[n][j] = delay
		
		if EMU:
			self._batch_update_netem(script_lines)

	def _calculate_delay_from_cache(self, n1_data, n2_data):
		"""Helper to calculate delay using pre-calculated coordinates"""
		Channel = self._Get_Channel_Definition(n1_data['obj'], n2_data['obj'])
		if Channel is None:
			return -2
		
		threshold = Channel['Threshold']
		latency = Channel.get('Latency', 'True')
		# Logic based on pre-calculated boolean types
		if n1_data['is_sat'] and n2_data['is_sat']:
			return float(self._Satellite2Satellite(n1_data['eci'], n2_data['eci'], threshold))
			
		elif not n1_data['is_sat'] and n2_data['is_sat']:
			# GS -> Sat
			try:
				min_el = Channel['Min_elevation_angle']
				
				return float(self._GroundBase2Satellite(n2_data['ecef'], n1_data['ecef'], n1_data['llh'], min_el, threshold, latency))
			except (TypeError, KeyError):
				return float(self._GroundBase2Satellite(n2_data['ecef'], n1_data['ecef'], n1_data['llh'], 0, threshold, latency))
				
		elif n1_data['is_sat'] and not n2_data['is_sat']:
			# Sat -> GS
			try:
				min_el = Channel['Min_elevation_angle']
				return float(self._GroundBase2Satellite(n1_data['ecef'], n2_data['ecef'], n2_data['llh'], min_el, threshold, latency))
			except (TypeError, KeyError):
				return float(self._GroundBase2Satellite(n1_data['ecef'], n2_data['ecef'], n2_data['llh'], 0, threshold, latency))
		else:
			return self._GroundBase2GroundBase()

	def _batch_update_netem(self, script_lines):
		with open('/tmp/batch_tc_update.sh', 'w') as f:
			f.write('\n'.join(script_lines))
		subprocess.run(['sudo', 'bash', '/tmp/batch_tc_update.sh'])

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

	def get_channel(self, node1=None, node2=None):
		if node1 is None and node2 is None:
			return self._delay_matrix
		elif node2 is None:
			return self._delay_matrix[node1]
		elif node1 is None:
			return self._delay_matrix[:][node2]
		return self._delay_matrix[node1][node2]

	def get_exist(self):
		return self._exist_channel

	def _Define_Channel(self, node, other, marker):
		"""Legacy function for initialization/CZML generation (non-cached)"""
		Channel = self._Get_Channel_Definition(node, other)
		if Channel is None:
			return -2
		
		is_sat_1 = isinstance(node, Satellite)
		is_sat_2 = isinstance(other, Satellite)

		if is_sat_1 and is_sat_2:
			return float(self._Satellite2Satellite(node.get_ECI(marker), other.get_ECI(marker), Channel['Threshold']))
		
		elif not is_sat_1 and is_sat_2:
			try:
				return float(self._GroundBase2Satellite(other.get_ECEF(marker), node.get_ECEF(), node.get_LLH(), Channel['Min_elevation_angle'], Channel['Threshold'], Channel.get('Latency', 'True')))
			except (TypeError, KeyError):
				# Fallback for GS without markers
				return float(self._GroundBase2Satellite(other.get_ECEF(marker), node.get_ECEF(), node.get_LLH(), 0, Channel['Threshold'], Channel.get('Latency', 'True')))
		
		elif is_sat_1 and not is_sat_2:
			try:	
				return float(self._GroundBase2Satellite(node.get_ECEF(marker), other.get_ECEF(), other.get_LLH(), Channel['Min_elevation_angle'], Channel['Threshold'], Channel.get('Latency', 'True')))
			except (TypeError, KeyError):
				# Fallback for GS without markers
				return float(self._GroundBase2Satellite(node.get_ECEF(marker), other.get_ECEF(), other.get_LLH(), 0, Channel['Threshold'], Channel.get('Latency', 'True')))
		else:
			return self._GroundBase2GroundBase()

	def _Get_Channel_Definition(self, node1, node2):
		name1 = node1.group
		name2 = node2.group
		
		for i, channel in enumerate(self.channels):
			c_n1 = channel['Node1']
			c_n2 = channel['Node2']
			if (c_n1 == name1 and c_n2 == name2) or (c_n1 == name2 and c_n2 == name1):
				while True:
					try:
						channel['Threshold'] = float(channel['Threshold'])
						break
					except KeyError:
						channel['Threshold'] = input(f'Insert threshold between {name1} and {name2}:')
					except ValueError:
						channel['Threshold'] = input(f'Insert again threshold between {name1} and {name2}:')
				
				self.channels[i] = channel
				return channel
		return None
	
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
		# print('Elevation (degrees): %f; distance (Km): %f'%(beta,d))
		
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

	def czml_channels(self, datetime_vector, node1, node2):
		ID = f'{node1.name}-to-{node2.name}'
		name = f'{node1.name} to {node2.name}'
		
		channel = czml.CZMLPacket(id=ID, name=name)
		polyline = czml.Polyline()
		polyline.show = []
		
		last_change = datetime_vector[0].isoformat()
		marker = 0
		
		Any_channel = False
		StrDescription = "<h2>Access times</h2><table class='sky-infoBox-access-table'><tr><th>Start</th><th>End</th>"

		previous_delay = self._Define_Channel(node1, node2, marker)
		
		if previous_delay != -2:
			
			for marker in range(1, len(datetime_vector)):
				dt = datetime_vector[marker]
				dt_iso = dt.isoformat()
				delay = self._Define_Channel(node1, node2, marker)
				
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
