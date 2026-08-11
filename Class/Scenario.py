#!/usr/bin/env python3
from Class.Satellite import Satellite
from Class.Ground_Station import GroundStation
from Class.Time_parameters import time_parameters
from Class.Channel import channel
from Class.routing import get_protocol

from skyfield.api import load
from ipaddress import IPv4Network,AddressValueError
from czml import czml
import time
import subprocess
import threading
import sys
import os
import json
import logging

from Class.log_config import setup_logging
setup_logging()
# class for the creation and management of nodes and channels.
class scenario:
	'''A scenario load a configuration file and managed different classes'''
	#The node_list property agrups all the nodes(Satellites and Graond Stations)
	_node_list = None
	
	#The channel property defines a Channel class to calcule the delay of the diferents pair of nodes
	_channel = None
	
	#nNodes property is the number of nodes that are loaded in the scenario
	_nNodes = None
	
	#The time paeameters property defines a time_paramiters class which control the time of the emulation
	_time_parameters = None
	
	#Flag to control simulation running state
	_running = False
	# True once the timeline reached its natural end (clock stopped, marker reset
	# to zero, but tc/OLSR rules still applied). Cleared on (re)start and on stop.
	_ended = False
		
	def __init__(self,TOMLfile):
		logging.info("Initializing scenario from TOML configuration")
		self.start_Network()
		try:
			self._time_parameters = time_parameters(TOMLfile['Time'])
			logging.info("Time parameters loaded successfully")
		except KeyError:
			logging.warning("No Time section in TOML, using defaults")
			TOMLfile['Time'] = {}
			self._time_parameters = time_parameters(TOMLfile['Time'])
		self._node_list = []

		try:
			self._channel = channel(TOMLfile['Channels'])
		except KeyError:
			error_msg = f"Missing 'Channels' configuration"
			logging.error(error_msg)
			raise KeyError(error_msg)

		# [Routing] protocol selection (Class/routing.py registry). Absent
		# section -> 'none' (netem shaping only, no gating, no daemon).
		self._routing_protocol = TOMLfile.get('Routing', {}).get('protocol', 'none')
		get_protocol(self._routing_protocol)   # validate at load time
		if 'Routing' not in TOMLfile:
			logging.warning("No [Routing] section in TOML — defaulting to "
			                "protocol = 'none' (no mesh routing daemon)")
		else:
			logging.info(f"Routing protocol: {self._routing_protocol}")


		self._nNodes = 0
		try:
			self._unicast_flooding = TOMLfile['unicast_flooding']
		except KeyError:
			error_msg = f"Missing 'unicast_flooding' configuration"
			logging.error(error_msg)
			raise KeyError(error_msg)
		try:
			self._network_ext = TOMLfile['network_ext']
		except KeyError:
			error_msg = f"Missing 'network_ext' configuration"
			logging.error(error_msg)
			raise KeyError(error_msg)

		try:
			self._host_interface = TOMLfile['host_interface']
		except KeyError:
			import socket
			self._host_interface = next(
				(iface for iface in socket.if_nameindex()
				 if iface[1] not in ('lo', 'virbr0') and not iface[1].startswith('vnet')),
				(None, 'enp4s0')
			)[1]
			logging.warning(f"'host_interface' not set in config — auto-detected: {self._host_interface}")
		try:
			network = TOMLfile['network']
		except KeyError:
			error_msg = f"Missing 'network' configuration"
			logging.error(error_msg)
			raise KeyError(error_msg)
		try:
			self._Network = IPv4Network(network)
		except AddressValueError:
				logging.warning(f"Invalid network address: {TOMLfile['network']}")
				network = '10.0.0.0/24'
				TOMLfile['network'] = network
				self._Network = IPv4Network(network)

		self._ip_Address = list(self._Network)[1:-1]
		logging.info(f"IP address pool configured with {len(self._ip_Address)} available addresses")

		# Load Satellites
		try:
			SpaceSegment = TOMLfile['SpaceSegment']
			logging.info("Loading satellite segment")
		except KeyError:
			logging.warning("No SpaceSegment section found in TOML")

		try:
			config_file = SpaceSegment['TLE']
			logging.info(f"Loading TLE file: {config_file}")
		except KeyError:
			logging.warning("No TLE file specified in SpaceSegment")
		try:
			satellites = load.tle_file(config_file)
			logging.info(f"Loaded {len(satellites)} satellites from TLE file")
		except UnboundLocalError:
			logging.error("TLE file not found or unreadable")

		for SatelliteSistem in SpaceSegment['SatelliteSistem']:
			for sat in satellites:
				if sat.name == SatelliteSistem['name']:
					self.AddSatellite(sat,SatelliteSistem)
	

		# Load Ground stations
		try:
			GroundSegment = TOMLfile['GroundSegment']
			logging.info("Loading ground segment")
		except KeyError:
			logging.warning("No GroundSegment section found in TOML")
		for GroundSistem in GroundSegment['GroundSistem']:
			self.AddGroundStation(GroundSistem)

		# Precompute the full contact/delay timeline now that all nodes are
		# loaded. Emulation, CZML generation and speed control all reuse it.
		self._channel.precompute(self._node_list, self._nNodes,
								 len(self._time_parameters.get_datetimes()))

		# Read an existing CZML file
		filename = 'Class/templates/ScenarioCZML.czml'
		with open(filename, 'r') as example:
			if os.stat(filename).st_size == 0:
				logging.info("Creating new CZML file")
				self.write_czml()
			else:
				logging.info("Loading existing CZML file")
				self.czml_doc = czml.CZML()
				self.czml_doc.loads(example.read())
				# Cache the static packets for the per-tick clock splice (same
				# as write_czml() does when generating a fresh document).
				try:
					self._czml_static_blob = ','.join(
						json.dumps(p.data()) for p in self.czml_doc.packets[1:])
				except Exception as e:
					logging.warning(f"Could not cache static CZML blob: {e}")
					self._czml_static_blob = None
		
		logging.info(f"Scenario initialization complete with {self._nNodes} nodes")
	def AddSatellite(self,sat_tle,constallation):
		#Creates a Satellite object and add to the scenario
		try:
			#Create a Satellite Node
			SAT = Satellite(sat_tle,constallation,self._ip_Address[self._nNodes],self._Network.netmask,self._nNodes,self._time_parameters.get_datetimes())
			#Add the node to the node list
			self._node_list.append(SAT)
			logging.info(f"Satellite '{SAT.name}' added to scenario")
			print ("- Satellite %s: ADDED"%(SAT.name))
			#Add 1 to the  node counter
			self._nNodes += 1
			#Add a new node to the channel
			self._channel.AddNode(self._node_list,self._nNodes,self._time_parameters._marker)
		except IndexError:
			error_msg = 'Maximum number of nodes exceeded: Node NOT ACCEPTED'
			logging.error(error_msg)
			print(error_msg)
			return
		except (KeyError, ValueError) as e:
			error_msg = f"Configuration error for satellite: {e}"
			logging.error(error_msg)
			print(error_msg)
			return
		except Exception as e:
			error_msg = f"Unexpected error creating satellite: {e}"
			logging.error(error_msg)
			print(error_msg)
			return

	def AddGroundStation(self,TOML_GS):
		#Creates a GroundStation object and add to the scenario
		try:
			#Creade a GroundStation Node
			GS = GroundStation(TOML_GS, self._ip_Address[self._nNodes], self._Network.netmask,self._nNodes)
			#Check if the node exist yet
			if self.Exist_Node(GS) or GS.name == None:
				error_msg = f"Ground Station '{GS.name}' NOT ACCEPTED"
				logging.warning(error_msg)
				return None
			else:
				self._node_list.append(GS)
				logging.info(f"Ground Station '{GS.name}' added to scenario")
				#Add 1 to the node counter  
				self._nNodes += 1
				#Add a new node to the channel
				self._channel.AddNode(self._node_list,self._nNodes,self._time_parameters._marker)
		except IndexError:
			error_msg = 'Maximum number of nodes exceeded: Node NOT ACCEPTED'
			logging.error(error_msg)
			return
		except (KeyError, ValueError) as e:
			error_msg = f"Configuration error for ground station: {e}"
			logging.error(error_msg)
			return
		except Exception as e:
			error_msg = f"Unexpected error creating ground station: {e}"
			logging.error(error_msg)
			return
	def step(self,EMU = False):
		# change date_time marker and update the scenario
		if self._time_parameters.step():
			self.reset()
			return True
		else:
			self._channel.update(self._node_list,self._nNodes,self._time_parameters._marker,EMU)
			return False
	def reset(self):
		# restart the parameters of simulatión, put date_time marker equal to 0 and update de scenario
		self._time_parameters.reset()
		self._channel.update(self._node_list,self._nNodes,self._time_parameters._marker,False)
	def write_bash(self):
		"""Write runtime_bash.sh and shutdown_bash.sh for channel emulation setup.

		Container nodes (type='container'/'container_external') use an
		IFB-based approach: ingress traffic on each container's host-side veth is
		redirected to an ifb<N> device where HTB + netem with u32 dst-IP filters
		shape it.  No VLAN subinterfaces or iptables MARK are needed.

		Internal/real external VMs use the original VLAN + iptables MARK path.
		"""
		host_interface = self._host_interface

		# Partition nodes into Docker containers vs traditional VMs
		docker_vm_nodes  = [(n, self._node_list[n-1]) for n in range(1, self._nNodes+1)
		                    if self._node_list[n-1].check_VM() and self._node_list[n-1].is_container]
		classic_vm_nodes = [(n, self._node_list[n-1]) for n in range(1, self._nNodes+1)
		                    if self._node_list[n-1].check_VM() and not self._node_list[n-1].is_container]

		with open("runtime_bash.sh", "w") as w_runtime, open("shutdown_bash.sh", "w") as w_shutdown:
			w_runtime.write('#!/bin/sh\n')
			w_shutdown.write('#!/bin/sh\n')

			# ── Docker IFB mode ──────────────────────────────────────────────────
			# All ip/tc commands go into batch files executed by a SINGLE ip/tc
			# process (`-batch`).  At N nodes the setup is O(N²) commands —
			# spawning sudo+tc per line takes minutes at 65 nodes; batch mode
			# runs the same setup in seconds.
			if docker_vm_nodes:
				n_ifbs = len(docker_vm_nodes)
				ip_up, tc_up, ip_down, tc_down = [], [], [], []
				logging.info(f"Configuring network emulation for {n_ifbs} Docker nodes "
				             f"(discovering interfaces, this may take a few minutes)...")

				# Phase 1: create IFB + redirect each container's outgoing traffic into it
				for n, node in docker_vm_nodes:
					veth = node.get_docker_veth()
					if not veth:
						logging.error(f'write_bash: could not find veth for {node.name} — skipping tc setup')
						continue
					ifb = f'ifb{n}'
					node._ifb_iface = ifb  # cache so Channel.update() uses the right interface

					ip_up.append(f'link add {ifb} type ifb')
					ip_up.append(f'link set dev {ifb} up')
					# Redirect ALL ingress from the container's host-side veth to the IFB
					tc_up.append(f'qdisc add dev {veth} ingress handle ffff:')
					tc_up.append(f'filter add dev {veth} parent ffff: protocol all u32 match u32 0 0 action mirred egress redirect dev {ifb}')
					# HTB root on IFB — per-destination classes go in Phase 2
					tc_up.append(f'qdisc add dev {ifb} root handle 1: htb')

					tc_down.append(f'qdisc del dev {veth} ingress')
					ip_down.append(f'link del {ifb}')
					# Cache veth so OLSR topology sync can reference it
					node._veth_iface = veth

				# Collect MAC addresses once so Phase 2 can match on L2 next-hop (dst MAC).
				# Filtering by MAC rather than dst IP lets OLSRd multi-hop routing work:
				# a packet routed via an intermediate node has that node's MAC as dst,
				# so it hits the correct per-hop netem class rather than the no-LOS class.
				logging.info("Discovering container MAC addresses for traffic shaping...")
				node_macs = {}  # node_list index → 'aa:bb:cc:dd:ee:ff'
				for _idx, _nd in enumerate(self._node_list):
					if getattr(_nd, 'ip_ext', None) and _nd.is_container:
						_mac = _nd.get_docker_mac()
						if _mac:
							node_macs[_idx] = _mac

				# Phase 2: HTB classes + netem + flower dst-MAC filters per (source, dest) pair
				logging.info("Generating tc/netem shaping rules...")
				for n, node in docker_vm_nodes:
					if not getattr(node, '_ifb_iface', None):
						continue
					ifb = node._ifb_iface
					for j in range(1, self._nNodes+1):
						dest_node = self._node_list[j-1]
						dest_ip   = getattr(dest_node, 'ip_ext', None)
						delay     = self._channel.get_channel(n-1, j-1)
						Ch        = self._channel._Get_Channel_Definition(node, dest_node)
						try:
							rate = float(Ch['Data_rate'])
						except (TypeError, KeyError, ValueError):
							rate = 100.0
						tc_up.append(f'class add dev {ifb} parent 1: classid 1:{j} htb rate {rate}mbit')
						if delay == -2 or delay == -1:
							tc_up.append(f'qdisc add dev {ifb} parent 1:{j} handle 1{j}: netem loss 100%')
						else:
							try:
								losses = f"{Ch['Packet_loss']}%"
								burst  = f"{Ch['Correlated_losses']}%"
							except (TypeError, KeyError):
								losses, burst = '0%', '0%'
							tc_up.append(f'qdisc add dev {ifb} parent 1:{j} handle 1{j}: netem delay {delay:.3f}ms loss {losses} {burst}')
						# Filter by Ethernet destination MAC (L2 next-hop) rather than
						# IP destination.  This allows OLSRd multi-hop routing: when SAT-n
						# routes to a no-LOS peer via an intermediate node, the frame's
						# dst MAC is the intermediate node's MAC — hitting its per-hop netem
						# class instead of the no-LOS loss-100% class.
						dest_mac = node_macs.get(j - 1)
						if dest_mac:
							tc_up.append(
								f'filter add dev {ifb} parent 1:0 protocol all prio 1 '
								f'flower dst_mac {dest_mac} classid 1:{j}'
							)
						else:
							# Fallback for non-Docker nodes: IP destination filter (no multi-hop).
							emu_ip = str(getattr(dest_node, '_ip', '') or '')
							for dip in dict.fromkeys(filter(None, (emu_ip, dest_ip))):
								tc_up.append(f'filter add dev {ifb} parent 1:0 protocol ip prio 1 u32 match ip dst {dip}/32 flowid 1:{j}')

				with open('ip_setup.batch', 'w') as f:
					f.write('\n'.join(ip_up) + '\n')
				with open('tc_setup.batch', 'w') as f:
					f.write('\n'.join(tc_up) + '\n')
				with open('tc_teardown.batch', 'w') as f:
					f.write('\n'.join(tc_down) + '\n')
				with open('ip_teardown.batch', 'w') as f:
					f.write('\n'.join(ip_down) + '\n')

				w_runtime.write(f'sudo modprobe ifb numifbs={n_ifbs} 2>/dev/null || true\n')
				# Stop bridged IPv6 frames from traversing the host ip6tables
				# (whose FORWARD policy is often DROP, e.g. k3s/kube-proxy). With
				# br_netfilter on, that silently drops inter-container IPv6 —
				# breaking any IPv6-multicast routing daemon (e.g. babel). Harmless
				# for IPv4-only setups. (No-op if br_netfilter isn't loaded.)
				w_runtime.write('sudo sysctl -w net.bridge.bridge-nf-call-ip6tables=0 2>/dev/null || true\n')
				w_runtime.write('sudo ip -force -batch ip_setup.batch\n')
				w_runtime.write('sudo tc -force -batch tc_setup.batch\n')
				w_shutdown.write('sudo tc -force -batch tc_teardown.batch 2>/dev/null\n')
				w_shutdown.write('sudo ip -force -batch ip_teardown.batch 2>/dev/null\n')

			# ── Classic VM mode (VLAN subinterfaces + iptables MARK) ─────────────
			if classic_vm_nodes:
				w_runtime.write('sudo ip link set dev brSATEMU down 2>/dev/null; sudo brctl delbr brSATEMU 2>/dev/null || true\n')
				w_runtime.write('sudo brctl addbr brSATEMU\nsudo ip link set dev brSATEMU up\n')
				w_runtime.write('sudo brctl stp brSATEMU off\n')
				if self._unicast_flooding:
					w_runtime.write('sudo brctl setageing brSATEMU 0\n')
				w_runtime.write('sudo sysctl -w net.ipv4.ip_forward=1\n')
				w_runtime.write('sudo iptables -I FORWARD -i %s -o virbr0 -s %s -d 192.168.122.0/24 -j ACCEPT\n' % (host_interface, self._network_ext))
				w_runtime.write('sudo ip link add vsnes_ext type vxlan id 10 dev %s group 239.1.1.1 dstport 4789\n' % host_interface)
				w_runtime.write('sudo ip link set vsnes_ext master virbr0\n')
				w_runtime.write('sudo ip link set vsnes_ext up\n')

				for n, node in classic_vm_nodes:
					interface = node._get_Host_interface()
					if node.node_type == 'vm_external':
						w_runtime.write('sudo -S ip link add %s type vxlan id %d00 remote %s dev %s dstport 4789;' % (interface, n, node.ip_ext, host_interface))
						w_runtime.write('sudo ip link set dev %s up\n' % interface)
					w_runtime.write('sudo ip link add link %s name %s.%d type vlan id %d\n' % (interface, interface, n, n))
					w_runtime.write('sudo ip link set dev %s.%d up\n' % (interface, n))
					w_runtime.write('sudo brctl addif brSATEMU %s.%d\n' % (interface, n))
					w_runtime.write('sudo tc qdisc add dev %s.%d root handle 1: htb\n' % (interface, n))
					w_runtime.write('sudo iptables -A PREROUTING -t mangle -m physdev --physdev-in %s.%d -j MARK --set-mark %d\n' % (interface, n, n))
					w_shutdown.write('sudo tc qdisc del dev %s.%d root handle 1: htb\n' % (interface, n))
					w_shutdown.write('sudo ip link del link %s name %s.%d type vlan id %d\n' % (interface, interface, n, n))
					w_shutdown.write('sudo iptables -D PREROUTING -t mangle -m physdev --physdev-in %s.%d -j MARK --set-mark %d\n' % (interface, n, n))

				for n, node in classic_vm_nodes:
					interface = node._get_Host_interface()
					for j in range(1, self._nNodes+1):
						delay = self._channel.get_channel(n-1, j-1)
						if delay == -2:
							w_runtime.write('sudo tc class add dev %s.%d parent 1: classid 1:%d htb rate 100mbit\n' % (interface, n, j))
							w_runtime.write('sudo tc qdisc add dev %s.%d parent 1:%d handle 1%d: netem loss 100\n' % (interface, n, j, j))
						else:
							Ch = self._channel._Get_Channel_Definition(self._node_list[n-1], self._node_list[j-1])
							try:
								w_runtime.write('sudo tc class add dev %s.%d parent 1: classid 1:%d htb rate %fmbit\n' % (interface, n, j, float(Ch['Data_rate'])))
							except (KeyError, TypeError, ValueError):
								w_runtime.write('sudo tc class add dev %s.%d parent 1: classid 1:%d htb rate 100mbit\n' % (interface, n, j))
							if delay == -1:
								w_runtime.write('sudo tc qdisc add dev %s.%d parent 1:%d handle 1%d: netem loss 100\n' % (interface, n, j, j))
							else:
								Losses = str(Ch['Packet_loss']) + '%'
								Corr   = str(Ch['Correlated_losses']) + '%'
								w_runtime.write('sudo tc qdisc add dev %s.%d parent 1:%d handle 1%d: netem delay %fms loss %s %s\n' % (interface, n, j, j, delay, Losses, Corr))
						w_runtime.write('sudo tc filter add dev %s.%d protocol ip parent 1:0 prio 1 handle %d fw flowid 1:%d\n' % (interface, n, j, j))
					if node.node_type == 'vm_external':
						w_shutdown.write(f"sshpass -p '{node._password}' ssh -o StrictHostKeyChecking=no {node._username}@{node.ip_ext} 'sudo -S ip link del {interface}'\n")

				w_shutdown.write('sudo ip link set vsnes_ext down\n')
				w_shutdown.write('sudo ip link del vsnes_ext\n')
				w_shutdown.write('sudo iptables -D FORWARD -i %s -o virbr0 -s %s -d 192.168.122.0/24 -j ACCEPT\n' % (host_interface, self._network_ext))
				w_shutdown.write('sudo ip link set dev brSATEMU down\n')
				w_shutdown.write('sudo brctl delbr brSATEMU\n')

		subprocess.run(['chmod', '+x', 'runtime_bash.sh'])
		subprocess.run(['chmod', '+x', 'shutdown_bash.sh'])

		# Gate the selected routing protocol (rules + daemon) for the WHOLE
		# scenario — containers get chain+rules+daemon, internal VMs get the
		# daemon over SSH. Outside the branches above so pure-VM scenarios
		# (no docker nodes) are gated too. 'none' just sanitizes.
		self._channel.init_routing_rules(self._node_list, self._nNodes,
		                                 self._routing_protocol)
	def get_speed(self):
		return self._time_parameters.get_speed(self._channel.get_exist())
	def get_number_of_nodes(self):
		return self._nNodes
	
	def _run_shutdown(self, password=None):
		"""Run shutdown_bash.sh and reset state. Safe to call from any thread.
		This is the ONLY path that removes the tc/OLSR rules — reached via an
		explicit stop (stop_simulation), never from the natural end of the run."""
		self._ended = False
		self._channel.cleanup_routing_rules()
		if os.path.isfile('./shutdown_bash.sh'):
			logging.info("Executing shutdown bash script")
			if password:
				proc = subprocess.run(['sudo', '-S', './shutdown_bash.sh'], input=(password + '\n').encode(), capture_output=True)
				if proc.returncode != 0:
					logging.error(f"Error executing shutdown script: {proc.stderr.decode()}")
			else:
				subprocess.call('./shutdown_bash.sh')
		else:
			logging.info("shutdown_bash.sh not found — skipping (emulation was not started)")
		sys.stdout.write("[SIM_CLEAR]\n")
		sys.stdout.flush()
		logging.info("Scenario reset complete")
		self.reset()

	def _clock_finished(self):
		"""Natural end of the timeline. 'Move the marker to zero': reset the time
		marker (recomputing the scenario at marker 0) WITHOUT removing any tc /
		OLSR rules. The channel shaping and contact-gating stay applied — they are
		removed only when an explicit stop is sent (stop_simulation -> _run_shutdown).
		This is what stops the end-of-run from tearing shaping down under the
		still-running containers (the sub-ms RTT collapse at sim end).

		The last [SIM] block is left on screen (not cleared) to signal 'ended but
		live'. The clock can be restarted with start_clock() (the 'run' command),
		which replays from the reset marker without re-applying any rules."""
		self._running = False
		self._ended = True
		self.reset()
		logging.info("Emulation finished — marker reset to zero; tc/OLSR rules "
		             "retained (send stop to remove them; run to restart the clock)")

	def stop_simulation(self, password=None):
		"""Stop the simulation from outside (e.g. user command or API call)."""
		logging.info("Stopping simulation...")
		self._running = False
		if hasattr(self, '_emulator_process') and self._emulator_process:
			logging.info("Waiting for emulator thread to stop")
			self._emulator_process.join(timeout=10)
			self._emulator_process = None
		self._run_shutdown(password)
	def start_Network (self):
		# libvirt is optional (only needed for internal VMs); skip if absent
		try:
			exist_net = subprocess.run('virsh net-list | grep -c -w default', capture_output = True, text = True, shell = True).stdout
			if int(exist_net) == 0:
				subprocess.run(['virsh', 'net-start', 'default'])
		except (ValueError, FileNotFoundError):
			logging.warning("libvirt/virsh not available — skipping default network start (internal VMs disabled)")
	
	def start_scenario_VM(self):
		logging.info("Starting scenario in VM mode")
		# If reconfiguration (started by init_scenario or a previous call) is still running, wait
		if hasattr(self, '_vm_startup_process') and self._vm_startup_process and self._vm_startup_process.is_alive():
			logging.info("VM reconfiguration in progress, waiting...")
			return False
		if not self.check_VMs():
			self._vm_startup_process = threading.Thread(target=self.start_VMs, daemon=True)
			self._vm_startup_process.start()
			return False
		logging.info("All VMs are running and configured")
		return True

	def _emit_sim_block(self):
		# The timestamp header goes out every tick (keeps the CLI clock live);
		# the per-channel detail lines (~O(N²), 500+ lines/tick at 78 nodes —
		# 1.5 GB of stdout over a 13 h campaign) are emitted every Nth tick.
		# VSNES_SIM_EMIT_EVERY=1 restores the old full-verbosity behaviour.
		every = getattr(self, '_sim_emit_every', None)
		if every is None:
			try:
				every = max(1, int(os.environ.get('VSNES_SIM_EMIT_EVERY', '10')))
			except ValueError:
				every = 10
			self._sim_emit_every = every
			self._sim_emit_count = 0
		sys.stdout.write(f"[SIM]{self._time_parameters.get_date_time().strftime('%m/%d/%Y, %H:%M:%S')}\n")
		self._sim_emit_count += 1
		if (self._sim_emit_count - 1) % every == 0:
			channels = self._channel.possible_channels()
			for ch in channels:
				parts = ch.split('/')
				n, j = int(parts[0]), int(parts[1])
				sys.stdout.write(f"[SIM]-{self._node_list[n].get_basic_data()} -> {self._node_list[j].get_basic_data()}:   {self._channel.get_channel(n, j):.6f}ms\n")
		sys.stdout.flush()

	def generate_docker_compose(self, output_path=None):
		"""Generate docker-compose.yml from the loaded scenario node list.

		Produces one service block per docker node (satellites + ground station)
		following the fixed MAC/IP convention used by the vsnes bridge network:
		  MAC = 02:42 + first two octets of ip_ext (hex) + 02 + last octet (hex)
		The registry service and network stanza are appended unchanged.
		Writes to <scenario_dir>/docker-compose.yml by default.
		Returns True on success, False on error.
		"""
		import ipaddress

		base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
		if output_path is None:
			output_path = os.path.join(base_dir, "docker-compose.yml")

		docker_nodes = [n for n in self._node_list if n.is_internal_container]
		if not docker_nodes:
			logging.error("generate_docker_compose: no docker nodes in scenario")
			return False

		# Derive bridge subnet from the first node's IP.
		try:
			sample_ip = ipaddress.IPv4Address(docker_nodes[0].ip_ext)
			net = ipaddress.IPv4Network(f"{sample_ip}/24", strict=False)
			subnet = str(net)
		except Exception:
			subnet = "172.28.0.0/24"

		def _mac(ip_str):
			parts = ip_str.split(".")
			return f"02:42:{int(parts[0]):02x}:{int(parts[1]):02x}:02:{int(parts[3]):02x}"

		# Ground-station services (clients depend on the first one so it comes
		# up before the constellation; must reference the ACTUAL service name).
		gs_services = [n._name.lower().replace("_", "-") for n in docker_nodes
		               if getattr(n, "group", "") == "GS"]
		gs_ip = next((n.ip_ext for n in docker_nodes
		              if getattr(n, "group", "") == "GS"), "172.28.0.2")

		lines = ["services:"]
		for node in docker_nodes:
			name = node._name
			svc  = name.lower().replace("_", "-")
			ip   = node.ip_ext
			mac  = _mac(ip)
			is_gs = getattr(node, "group", "") == "GS"
			lines.append(f"  {svc}:")
			lines.append(f"    build: .")
			lines.append(f"    container_name: {name}")
			lines.append(f"    hostname: {name}")
			lines.append(f"    privileged: true")
			lines.append(f"    cgroup: host")
			lines.append(f"    ulimits:")
			lines.append(f"      nofile:")
			lines.append(f"        soft: 65536")
			lines.append(f"        hard: 65536")
			lines.append(f"    cap_add:")
			lines.append(f"      - NET_ADMIN")
			lines.append(f"      - SYS_ADMIN")
			lines.append(f"      - NET_RAW")
			lines.append(f"    security_opt:")
			lines.append(f"      - apparmor=unconfined")
			if not is_gs and gs_services:
				lines.append(f"    depends_on:")
				lines.append(f"      - {gs_services[0]}")
			lines.append(f"    environment:")
			if is_gs:
				lines.append(f"      - ROLE=server")
			else:
				lines.append(f"      - ROLE=client")
				lines.append(f"      - GS_IP=${{GS_IP:-{gs_ip}}}")
				lines.append(f"      - GS_PORTS=5201 5202 5203 5204 5205 5206")
				lines.append(f"      - PING_INTERVAL=${{PING_INTERVAL:-4}}")
				lines.append(f"      - THROUGHPUT_SEGMENT_S=${{THROUGHPUT_SEGMENT_S:-900}}")
			lines.append(f"    volumes:")
			lines.append(f"      - /lib/modules:/lib/modules:ro")
			lines.append(f"      - ./results:/results")
			lines.append(f"      - ./control:/control:ro")
			lines.append(f"    sysctls:")
			lines.append(f"      - net.ipv4.ip_forward=1")
			lines.append(f"    networks:")
			lines.append(f"      olsr_net:")
			lines.append(f"        ipv4_address: {ip}")
			lines.append(f"        mac_address: {mac}")
			lines.append(f"    restart: unless-stopped")

		# Registry service
		lines += [
			"  registry:",
			"    image: registry:2",
			"    container_name: vsnes-registry",
			"    restart: unless-stopped",
			"    ports:",
			'      - "5001:5000"',
			"    volumes:",
			"      - ./registry-data:/var/lib/registry",
			"    networks:",
			"      olsr_net:",
			"        ipv4_address: 172.28.0.250",
			"",
			"networks:",
			"  olsr_net:",
			"    driver: bridge",
			"    ipam:",
			"      config:",
			f"        - subnet: {subnet}",
		]

		try:
			with open(output_path, "w") as f:
				f.write("\n".join(lines) + "\n")
			logging.info(f"generate_docker_compose: wrote {len(docker_nodes)} services to {output_path}")
			return True
		except Exception as e:
			logging.error(f"generate_docker_compose: write failed: {e}")
			return False

	def start_from_compose(self):
		"""Bring up docker node containers via 'docker compose up -d'.

		Never recreates or restarts a running container (a live k3s cluster or
		routing daemon must survive re-init). Only the scenario's own services
		are ever passed to compose — nothing outside the loaded scenario is
		started — and only the ones actually missing are brought up.
		"""
		compose_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docker-compose.yml")
		if not os.path.exists(compose_file):
			logging.warning("start_from_compose: docker-compose.yml not found — skipping")
			return False

		# container name -> compose service name (same convention as
		# generate_docker_compose: lowercase, '_' -> '-').
		svc_by_name = {n.name: n.name.lower().replace('_', '-')
		               for n in self._node_list if n.is_internal_container}
		if not svc_by_name:
			logging.info("start_from_compose: no internal containers in scenario")
			return True

		chk = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
		                     capture_output=True, text=True)
		running = set(chk.stdout.split())
		missing = [svc for name, svc in svc_by_name.items() if name not in running]
		if not missing:
			logging.info(f"start_from_compose: all {len(svc_by_name)} containers "
			             f"already running — nothing to do")
			return True

		logging.info(f"start_from_compose: starting {len(missing)} missing container(s): "
		             f"{' '.join(missing)}")
		cmd = ["docker", "compose", "-f", compose_file, "up", "-d",
		       "--no-recreate", "--no-build"] + missing
		result = subprocess.run(cmd, capture_output=True, text=True)
		if result.returncode != 0:
			# Compose reports progress on stderr, so the real cause (a name
			# conflict with a leftover container, a service missing from the
			# regenerated compose file) is buried under 'Creating' lines.
			out = (result.stdout or '') + (result.stderr or '')
			causes = [ln.strip() for ln in out.splitlines()
			          if ('Error' in ln or 'no such service' in ln or 'Conflict' in ln)]
			logging.error("start_from_compose failed: "
			              + (" | ".join(causes) if causes else out.strip()))
			return False
		logging.info("start_from_compose: containers started")
		return True

	def compose_service_names(self):
		'''Compose service names for the scenario's internal containers.'''
		return [n.name.lower().replace('_', '-')
		        for n in self._node_list if n.is_internal_container]

	def _host_ip(self):
		'''First global IPv4 on the host interface — the vxlan remote that
		vm_external nodes tunnel back to. None if it can't be resolved.'''
		try:
			out = subprocess.run(
				['ip', '-4', '-o', 'addr', 'show', self._host_interface],
				capture_output=True, text=True, timeout=5).stdout
			for line in out.splitlines():
				parts = line.split()
				if 'inet' in parts:
					return parts[parts.index('inet') + 1].split('/')[0]
		except Exception as e:
			logging.warning(f"_host_ip: could not resolve host IP on "
			                f"{self._host_interface}: {e}")
		return None

	# ── Stage 2: prepare ─────────────────────────────────────────────────────
	def prepare_scenario(self, isVM=True, password=None):
		"""Prepare everything so start_clock() only has to run the time loop.

		isVM=True : start/configure nodes by their `type` (container via compose
		            then docker exec; vm via virt-clone/virsh + SSH; externals
		            validated + configured over SSH) + generate routing rules
		            (write_bash) + apply the one-time channel shaping (runtime_bash).
		isVM=False: skip ALL node/network config — only the contacts/timing
		            (already computed at load) are used; start_clock() then just
		            advances satellite positions + sim time (external sync).
		password  : sudo password for the channel-shaping script.

		The routing protocol (gating rules + daemon) comes from the toml
		[Routing] section — see Class/routing.py.
		"""
		self._isVM = isVM
		self._password = password
		if not isVM:
			logging.info("prepare_scenario: isVM=False — simulation only "
			             "(contacts/timing), skipping node and network config")
			return True
		# 1. start nodes by type. Internal containers must EXIST before their
		# per-node start() (which docker-execs into them), so compose runs first.
		if any(n.is_internal_container for n in self._node_list):
			self.start_from_compose()
		host_ip = self._host_ip()
		for node in self._node_list:
			node.start(self._nNodes, host_ip=host_ip)
		# 2. routing rules + channel-prep scripts
		if any(getattr(node, 'EmuScript', None) for node in self._node_list):
			self._Emulation_startup_script()
		self.write_bash()
		# 3. apply the one-time tc/netem channel shaping (moved out of _run)
		self._apply_channels(password)
		return True

	def _apply_channels(self, password=None):
		"""Run runtime_bash.sh — the one-time tc/netem channel setup. Moved out
		of _run so the channels are prepared during init, not at clock start."""
		logging.info("Executing runtime bash script (channel setup)")
		if password:
			proc = subprocess.run(['sudo', '-S', './runtime_bash.sh'],
			                      input=(password + '\n').encode(), capture_output=True)
			if proc.returncode != 0:
				logging.error(f"Error executing runtime script: {proc.stderr.decode()}")
		else:
			subprocess.call('./runtime_bash.sh')

	# ── Stage 3: start the clock ─────────────────────────────────────────────
	def start_clock(self, isVM=None, password=None):
		"""Start ONLY the simulation time loop (prepare_scenario must have run).
		Uses the saved isVM to decide whether per-tick network updates apply;
		positions/timing always advance so external sync works either way."""
		if isVM is not None:
			self._isVM = isVM
		if password is not None:
			self._password = password
		self._ended = False          # (re)starting the clock clears the ended flag
		self._running = True
		n_connections = int(1+(self._nNodes-1)*self._nNodes/2)
		logging.info(f"Starting clock loop (isVM={getattr(self, '_isVM', True)}, "
		             f"{n_connections} connections)")
		self._emulator_process = threading.Thread(target=self._run, daemon=True)
		self._emulator_process.start()

	# ── Back-compat: old one-shot start (prepare + run together) ──────────────
	def start_scenario(self, EMU, password=None):
		logging.info(f"Starting scenario (legacy one-shot) - Emulation: {EMU}")
		self.prepare_scenario(isVM=EMU, password=password)
		self.start_clock()


	def _run(self):
		# Channel shaping (runtime_bash) now runs in prepare_scenario/_apply_channels.
		# _run only advances the clock; step(EMU) applies per-tick network updates
		# when EMU (isVM) is True, and always advances positions/sim time.
		EMU = getattr(self, '_isVM', True)

		time.sleep(5)

		self._emit_sim_block()
		time.sleep(self._time_parameters.get_TimeInterval()/self.get_speed())
		Nversion = 1
		self._update_czml_clock(Nversion, self.get_speed())
		self._achieved_multiplier = self.get_speed()
		self._overrun_count = 0
		# Sleep-deficit accounting: a slow tick's overrun is carried forward and
		# repaid by later fast ticks, so the AVERAGE achieved speed converges to
		# the configured one whenever the mean tick cost fits the budget
		# (previously each overrun permanently lost time). Capped so a one-off
		# stall (host suspend, load spike) can't force minutes of flat-out
		# catch-up.
		debt = 0.0
		last_warn = 0.0
		prev_tick_start = None
		while self._running:
			start = time.time()
			t0 = time.time()
			finished = self.step(EMU)
			t_step = time.time() - t0
			if finished:
				logging.info("The emulation is over: moving the marker to zero "
				             "(rules retained — send stop to remove them)")
				self._clock_finished()
				break
			t0 = time.time()
			self._emit_sim_block()
			t_emit = time.time() - t0

			# Achieved multiplier = sim seconds advanced per real second,
			# smoothed (EMA) over the actual tick period including the sleep.
			interval_s = self._time_parameters.get_TimeInterval()
			if prev_tick_start is not None:
				inst = interval_s / max(start - prev_tick_start, 1e-9)
				self._achieved_multiplier = 0.8*self._achieved_multiplier + 0.2*inst
			prev_tick_start = start

			Nversion += 1
			t0 = time.time()
			self._update_czml_clock(Nversion, self._achieved_multiplier)
			t_czml = time.time() - t0

			# NOTE: total_time now includes the CZML clock write — previously it
			# was measured BEFORE that write, so its cost never counted against
			# the tick budget and every tick silently ran long.
			total_time = time.time() - start
			multiplier = self.get_speed()
			budget = interval_s / multiplier
			stopTime = budget - total_time - debt
			if stopTime >= 0:
				debt = 0.0
			else:
				debt = min(-stopTime, 5.0 * budget)
				stopTime = 0
				self._overrun_count += 1
				now = time.time()
				if now - last_warn > 30:
					last_warn = now
					logging.warning(
						f"Tick overran its {budget:.2f}s budget (x{multiplier:g}): "
						f"total={total_time:.2f}s [step={t_step:.2f}s emit={t_emit:.2f}s "
						f"czml={t_czml:.2f}s] achieved~x{self._achieved_multiplier:.2f} "
						f"({self._overrun_count} overruns so far)")

			time.sleep(stopTime)

	def _update_czml_clock(self, Nversion, multiplier):
		# Replace only the document (clock) packet — the node/channel packets
		# are static during a run — and write the file atomically so the web
		# server never reads a half-written document.
		version = self.czml_doc.packets[0].version[0]+'.'+str(Nversion)
		interval = self._time_parameters.get_interval()
		currentTime = self._time_parameters.get_date_time().isoformat()
		clock = czml.Clock(interval=interval,currentTime=currentTime,multiplier=multiplier,range='UNBOUNDED',step='SYSTEM_CLOCK_MULTIPLIER')
		packet1 = czml.CZMLPacket(id='document',name='Satellite Network Emulator',version=version,clock=clock)
		packet1.availability = interval
		self.czml_doc.packets[0] = packet1
		# Transient OSErrors (e.g. Windows-side file locks on /mnt/c) must not
		# kill the simulation thread — both files are rewritten next tick anyway.
		filename = "Class/templates/ScenarioCZML.czml"
		tmpname = filename + '.tmp'
		try:
			# Only the document packet changes per tick; the node/channel
			# packets were serialized once by write_czml(). Splicing the fresh
			# clock packet onto that cached blob avoids re-serializing the
			# whole multi-MB document through the czml object tree every tick
			# (~2 s at 78 nodes — this was capping the achievable sim speed).
			blob = getattr(self, '_czml_static_blob', None)
			if blob is None:
				self.czml_doc.write(tmpname)
			else:
				head = json.dumps(packet1.data())
				with open(tmpname, 'w') as f:
					f.write('[' + head + (',' + blob if blob else '') + ']')
			os.replace(tmpname, filename)
		except OSError as e:
			logging.warning(f"Skipping CZML clock write this tick: {e}")
		try:
			with open("simulation_time.txt", "w") as f:
				f.write(currentTime)
		except OSError as e:
			logging.warning(f"Skipping simulation_time.txt write this tick: {e}")
	
	
	def check_VMs(self):
		for Node in self._node_list:
			if Node.node_type == 'vm':
				if not(Node.check_VM()):
					logging.error("Not all VMs are running, starting VMs")
					return False
			else:
				Node.start(self._nNodes, host_ip=self._host_ip())

		logging.info("All VMs are running")
		return True



	def delete_VMs (self):
		logging.warning("Deleting VMs")
		for n in range(0,self._nNodes):
			self._node_list[n].delete_VM()
	def start_VMs(self):
		if any(n.is_internal_container for n in self._node_list):
			self.start_from_compose()
		host_ip = self._host_ip()
		for node in self._node_list:
			node.start(self._nNodes, host_ip=host_ip)
	def Exist_Node(self,New_node):
		exist = False
		n = 0
		for Node in self._node_list:
			if type(New_node).__name__ == "Satellite" and type(Node).__name__ == "Satellite":
				if Node.id == New_node.id or Node.name == New_node.name:
					return True
			elif type(New_node).__name__ == "GroundStation" and type(Node).__name__ == "GroundStation":
				if Node.name == New_node.name:
					return True	 
		return False	 
	def scenario_description(self):
		description = "The scenario is formed by %d nodes\n"%(self._nNodes)
		description += 'Initialize: %s Ends: %s\n\n'%(self._time_parameters.get_initial_date_time(),self._time_parameters.get_end_date_time())
		for n in range(0,self._nNodes):
			description += 'Node %d: %s\n'%(n+1,self._node_list[n].description().replace('<h3>','').replace('<p>','').replace('</h3>','\n').replace('</p>','').replace('</small>','').replace('<small>',''))
		return description
	def _Emulation_startup_script(self):
		# Run the user-provided EmuScript on each node VM (if configured)
		for Node in self._node_list:
			Node.Emulation_startup_script(self._node_list)
	def write_czml (self):
		# Initialize a document
		start = time.time()
		self.czml_doc = czml.CZML()
		# Create and append the document packet
		ID = 'document'
		name = 'Satellite Network Emulator'
		version= '1.0'
		interval = self._time_parameters.get_interval()
		currentTime = self._time_parameters.get_date_time().isoformat()
		multiplier = self._time_parameters.get_speed()
		clock = czml.Clock(interval=interval,currentTime=currentTime,multiplier=multiplier,range = 'LOOP_STOP',step = 'SYSTEM_CLOCK_MULTIPLIER')
		packet1 = czml.CZMLPacket(id=ID,name=name,version=version,clock=clock)
		packet1.availability = interval
		self.czml_doc.packets.append(packet1)
		n_packets = int(1+self._nNodes+(self._nNodes-1)*self._nNodes/2)
		cont = 1
		for node in self._node_list:
			print ('Writting the Cesium configuration file. Packages computed %d/%d.'%(cont,n_packets))
			sys.stdout.write("\x1b[1A\x1b[2K")
			self.czml_doc.packets.append(node.czml_node(self._time_parameters.get_datetimes()))
			cont += 1
		for n in range(0,self._nNodes):
			for j in range(n+1,self._nNodes):
				print ('Writting the Cesium configuration file. Packages computed %d/%d.'%(cont,n_packets))
				sys.stdout.write("\x1b[1A\x1b[2K")
				result = self._channel.czml_channels(self._time_parameters.get_datetimes(),self._node_list[n],self._node_list[j],idx1=n,idx2=j)
				if result is not None:
					self.czml_doc.packets.append(result)
				cont += 1
		# Write the CZML document to a file
		filename = "Class/templates/ScenarioCZML.czml"
		self.czml_doc.write(filename)

		# Serialize the static packets (everything except the clock/document
		# packet) ONCE — _update_czml_clock() splices the per-tick clock onto
		# this blob instead of re-serializing the whole document each tick.
		try:
			self._czml_static_blob = ','.join(
				json.dumps(p.data()) for p in self.czml_doc.packets[1:])
		except Exception as e:
			logging.warning(f"Could not cache static CZML blob (per-tick clock "
			                f"writes will use the slow full-document path): {e}")
			self._czml_static_blob = None

		# Grab Currrent Time After Running the Code
		end = time.time()

		#Subtract Start Time from The End Time
		total_time = end - start
		logging.info("CZML file writing complete in %.2f seconds" % total_time)
