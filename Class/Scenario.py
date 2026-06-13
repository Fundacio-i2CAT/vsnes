#!/usr/bin/env python3
from Class.Satellite import Satellite
from Class.Ground_Station import GroundStation
from Class.Time_parameters import time_parameters
from Class.Channel import channel

from skyfield.api import load
from ipaddress import IPv4Network,AddressValueError
from czml import czml
import time
import subprocess
import threading
import sys
import os
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

		Docker-container nodes (is_external_vm=1 + docker inspect succeeds) use an
		IFB-based approach: ingress traffic on each container's host-side veth is
		redirected to an ifb<N> device where HTB + netem with u32 dst-IP filters
		shape it.  No VLAN subinterfaces or iptables MARK are needed.

		Internal/real external VMs use the original VLAN + iptables MARK path.
		"""
		host_interface = self._host_interface

		# Partition nodes into Docker containers vs traditional VMs
		docker_vm_nodes  = [(n, self._node_list[n-1]) for n in range(1, self._nNodes+1)
		                    if self._node_list[n-1].check_VM() and self._node_list[n-1]._is_docker_container()]
		classic_vm_nodes = [(n, self._node_list[n-1]) for n in range(1, self._nNodes+1)
		                    if self._node_list[n-1].check_VM() and not self._node_list[n-1]._is_docker_container()]

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
					if getattr(_nd, 'ip_ext', None) and _nd._is_docker_container():
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
				w_runtime.write('sudo ip -force -batch ip_setup.batch\n')
				w_runtime.write('sudo tc -force -batch tc_setup.batch\n')
				w_shutdown.write('sudo tc -force -batch tc_teardown.batch 2>/dev/null\n')
				w_shutdown.write('sudo ip -force -batch ip_teardown.batch 2>/dev/null\n')

				# Install initial OLSR topology iptables rules (blocks no-LOS pairs).
				logging.info("Applying OLSR topology rules inside containers "
				             "(iptables per no-LOS pair)...")
				self._channel.init_olsr_rules(self._node_list, self._nNodes)

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
					if node.is_external_vm:
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
					if node.service in ('relay', 'batman', 'RELAY'):
						nn2 = self._nNodes + n
						w_runtime.write('sudo ip link add link %s name %s.%d type vlan id %d\n' % (interface, interface, nn2, nn2))
						w_shutdown.write('sudo ip link del link %s name %s.%d type vlan id %d\n' % (interface, interface, nn2, nn2))
						w_runtime.write('sudo ip link set dev %s.%d up\n' % (interface, nn2))
						w_runtime.write('sudo brctl addif brSATEMU %s.%d\n' % (interface, nn2))
						w_runtime.write('sudo iptables -A PREROUTING -t mangle -m physdev --physdev-in %s.%d -j MARK --set-mark %d\n' % (interface, nn2, n))
						w_shutdown.write('sudo iptables -D PREROUTING -t mangle -m physdev --physdev-in %s.%d -j MARK --set-mark %d\n' % (interface, nn2, n))
						w_runtime.write('sudo tc qdisc add dev %s.%d root netem loss 100%%\n' % (interface, nn2))

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
					if node.is_external_vm:
						w_shutdown.write(f"sshpass -p '{node._password}' ssh -o StrictHostKeyChecking=no {node._username}@{node.ip_ext} 'sudo -S ip link del {interface}'\n")

				w_shutdown.write('sudo ip link set vsnes_ext down\n')
				w_shutdown.write('sudo ip link del vsnes_ext\n')
				w_shutdown.write('sudo iptables -D FORWARD -i %s -o virbr0 -s %s -d 192.168.122.0/24 -j ACCEPT\n' % (host_interface, self._network_ext))
				w_shutdown.write('sudo ip link set dev brSATEMU down\n')
				w_shutdown.write('sudo brctl delbr brSATEMU\n')

		subprocess.run(['chmod', '+x', 'runtime_bash.sh'])
		subprocess.run(['chmod', '+x', 'shutdown_bash.sh'])
	def get_speed(self):
		return self._time_parameters.get_speed(self._channel.get_exist())
	def get_number_of_nodes(self):
		return self._nNodes
	
	def _run_shutdown(self, password=None):
		"""Run shutdown_bash.sh and reset state. Safe to call from any thread."""
		self._channel.cleanup_olsr_rules()
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
		channels = self._channel.possible_channels()
		sys.stdout.write(f"[SIM]{self._time_parameters.get_date_time().strftime('%m/%d/%Y, %H:%M:%S')}\n")
		for ch in channels:
			parts = ch.split('/')
			n, j = int(parts[0]), int(parts[1])
			sys.stdout.write(f"[SIM]-{self._node_list[n].get_basic_data()} -> {self._node_list[j].get_basic_data()}:   {self._channel.get_channel(n, j):.6f}ms\n")
		sys.stdout.flush()

	def start_scenario(self, EMU, password=None):
		logging.info(f"Starting scenario - Emulation: {EMU}")
		self._running = True

		if EMU:
			if any(getattr(node, 'EmuScript', None) for node in self._node_list):
				self._Emulation_startup_script()
			self.write_bash()

		n_connections = int(1+(self._nNodes-1)*self._nNodes/2)
		logging.info(f"Starting emulation process with {n_connections} connections")
		self._emulator_process = threading.Thread(target=self._run, args=(EMU, password), daemon=True)
		self._emulator_process.start()


	def _run(self, EMU, password=None):

		if EMU:
			logging.info("Executing runtime bash script")
			if password:
				proc = subprocess.run(['sudo', '-S', './runtime_bash.sh'], input=(password + '\n').encode(), capture_output=True)
				if proc.returncode != 0:
					logging.error(f"Error executing runtime script: {proc.stderr.decode()}")
			else:
				subprocess.call('./runtime_bash.sh')

		time.sleep(5)

		self._emit_sim_block()
		time.sleep(self._time_parameters.get_TimeInterval()/self.get_speed())
		Nversion = 1
		self._update_czml_clock(Nversion, self.get_speed())
		while self._running:
			# Initialize a document
			start = time.time()
			if self.step(EMU):
				logging.info("The emulation is over: stopping simulation")
				self._running = False
				self._run_shutdown(password)
				break
			self._emit_sim_block()
			# Grab Currrent Time After Running the Code
			end = time.time()

			#Subtract Start Time from The End Time
			total_time = end - start
			multiplier = self.get_speed()
			stopTime=(self._time_parameters.get_TimeInterval()/multiplier)-total_time
			if stopTime < 0:
				multiplier = self._time_parameters.get_TimeInterval()/total_time
				stopTime = 0
				
			Nversion += 1
			self._update_czml_clock(Nversion, multiplier)
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
			self.czml_doc.write(tmpname)
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
			if not Node.is_external_vm:
				if not(Node.check_VM()):
					logging.error("Not all VMs are running, starting VMs")
					return False
			else:
				Node.run_VM(self._nNodes)
		
		logging.info("All VMs are running")
		return True
				

				
	def delete_VMs (self):
		logging.warning("Deleting VMs")
		for n in range(0,self._nNodes):
			self._node_list[n].delete_VM()
	def start_VMs(self):
		for node in self._node_list:
			node.run_VM(self._nNodes)
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
		
		# Grab Currrent Time After Running the Code
		end = time.time()

		#Subtract Start Time from The End Time
		total_time = end - start
		logging.info("CZML file writing complete in %.2f seconds" % total_time)
