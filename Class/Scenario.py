#!/usr/bin/env python3
from Class.Satellite import Satellite
from Class.Ground_Station import GroundStation
from Class.Time_parameters import time_parameters
from Class.Channel import channel

from skyfield.api import load
from ipaddress import IPv4Network,AddressValueError
from czml import czml
import toml
import time
import subprocess
import webbrowser
import threading
from multiprocessing import Process
import sys
import os
import logging

# Create log directory if it doesn't exist
os.makedirs('/tmp/log', exist_ok=True)
	
# Setup logging (if not already configured by Node.py)
if not logging.getLogger().handlers:
	os.makedirs('/tmp/log', exist_ok=True)
	
	logging.basicConfig(
		level=logging.INFO,
		format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
		handlers=[
			logging.FileHandler('/tmp/log/snes.log'),
			logging.StreamHandler()
		]
	)
ip_Address = []
Network = None
host_interface = 'enp4s0'
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
		global ip_Address
		global Network
		global Network_ext
		global host_interface

		try:
			Network_ext = TOMLfile['network_ext']
		except KeyError:
			error_msg = f"Missing 'network_ext' configuration"
			logging.error(error_msg)
			raise KeyError(error_msg)

		try:
			host_interface = TOMLfile['host_interface']
		except KeyError:
			import socket
			host_interface = next(
				(iface for iface in socket.if_nameindex()
				 if iface[1] not in ('lo', 'virbr0') and not iface[1].startswith('vnet')),
				(None, 'enp4s0')
			)[1]
			logging.warning(f"'host_interface' not set in config — auto-detected: {host_interface}")
		try:
			Network = TOMLfile['network']
		except KeyError:
			error_msg = f"Missing 'unicast_flooding' configuration"
			logging.error(error_msg)
			raise KeyError(error_msg)
		try:
			Network = IPv4Network(Network)
		except AddressValueError:
				logging.warning(f"Invalid network address: {TOMLfile['network']}")
				network = '10.0.0.0/24'
				TOMLfile['network'] = network
				Network = IPv4Network(network)



		for addr in Network:
			ip_Address.append(addr)
		ip_Address = ip_Address[1:-1]
		logging.info(f"IP address pool configured with {len(ip_Address)} available addresses")

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
#	   for sat in satellites:
#		   self.AddSatellite(sat,SatelliteSistem)

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
		#print(toml.dumps(TOMLfile))
	def AddSatellite(self,sat_tle,constallation):
		#Creates a Satellite object and add to the scenario
		try:
			#Create a Satellite Node
			SAT = Satellite(sat_tle,constallation,ip_Address[self._nNodes],Network.netmask,self._nNodes,self._time_parameters.get_datetimes())
			#Check if the node exist yet
			# if self.Exist_Node(SAT):
			#   print ("- Satellite %s: NOT ACCEPTED"%(SAT.name))
			# else:
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
			GS = GroundStation(TOML_GS, ip_Address[self._nNodes], Network.netmask,self._nNodes)
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
	def write_bash (self):
		# write two bash files, one for define the scenario and  other to delete the configuration of the first file.
		#Open the two bash files
		w_runtime = open("runtime_bash.sh", "w")
		w_shutdown = open("shutdown_bash.sh", "w")
		w_runtime.write('#!/bin/sh\n')
		w_shutdown.write('#!/bin/sh\n')

		w_runtime.write('sudo ip link set dev brSATEMU down\nsudo brctl delbr brSATEMU\n')
		w_runtime.write('sudo brctl addbr brSATEMU\nsudo ip link set dev brSATEMU up\n')
		w_runtime.write('sudo brctl stp brSATEMU off\n')
		if self._unicast_flooding:
			w_runtime.write('sudo brctl setageing brSATEMU 0\n')
		# Commands to enable external domains/VMs in Relay mode
		w_runtime.write('sudo sysctl -w net.ipv4.ip_forward=1\n')
		w_runtime.write('sudo iptables -I FORWARD -i %s -o virbr0 -s %s -d 192.168.122.0/24 -j ACCEPT\n'%(host_interface, Network_ext))
		w_runtime.write('sudo ip link add vsnes_ext type vxlan id 10 dev %s group 239.1.1.1 dstport 4789\n'%(host_interface))
		w_runtime.write('sudo ip link set vsnes_ext master virbr0\n')
		w_runtime.write('sudo ip link set vsnes_ext up\n')
		
		for n in range(1,self._nNodes+1):
			if self._node_list[n-1].check_VM():
				#Loop from 1 to one more than the number of nodes to define one VLAN per node and start the VLANs in 1
				interface = self._node_list[n-1]._get_Host_interface()
				if self._node_list[n-1].is_external_vm:
					line_runtime = str('sudo -S ip link add %s type vxlan id %d00 remote %s dev %s dstport 4789;'%(interface,n,self._node_list[n-1].ip_ext,host_interface))
					w_runtime.write(line_runtime)
					line_runtime = str('sudo ip link set dev %s up\n'%(interface))
					w_runtime.write(line_runtime)
				# Define an interface in a VLAN
				line_runtime = str('sudo ip link add link %s name %s.%d type vlan id %d\n'%(interface,interface,n,n))
				w_runtime.write(line_runtime)
				#Set up
				line_runtime = str('sudo ip link set dev %s.%d up\n'%(interface,n))
				w_runtime.write(line_runtime)
				#Add the interface to the bridge
				line_runtime = str('sudo brctl addif brSATEMU %s.%d\n'%(interface,n))
				w_runtime.write(line_runtime)
				#Defines a tc qdisc root
				line_runtime = str('sudo tc qdisc add dev %s.%d root handle 1: htb\n'%(interface,n))
				w_runtime.write(line_runtime)
				line_runtime = str('sudo iptables -A PREROUTING -t mangle -m physdev --physdev-in %s.%d -j MARK --set-mark %d\n'%(interface,n,n))
				w_runtime.write(line_runtime)
				#Delete the root of tc qdisc
				line_shutdown = str('sudo tc qdisc del dev %s.%d root handle 1: htb\n'%(interface,n))
				w_shutdown.write(line_shutdown)
				# Delete the interface associated with the VLAN 
				line_shutdown = str('sudo ip link del link %s name %s.%d type vlan id %d\n'%(interface,interface,n,n))
				w_shutdown.write(line_shutdown)
				line_shutdown = str('sudo iptables -D PREROUTING -t mangle -m physdev --physdev-in %s.%d -j MARK --set-mark %d\n'%(interface,n,n))
				w_shutdown.write(line_shutdown)
				if self._node_list[n-1].service == 'relay' or self._node_list[n-1].service == 'batman' or self._node_list[n-1].service == 'RELAY':
					nodeNumber2 = self._nNodes + n
					line_runtime = 'sudo ip link add link %s name %s.%d type vlan id %d\n'%(interface,interface,nodeNumber2,nodeNumber2)
					w_runtime.write(line_runtime)
					line_shutdown = 'sudo ip link del link %s name %s.%d type vlan id %d\n'%(interface,interface,nodeNumber2,nodeNumber2)
					w_shutdown.write(line_shutdown)
					line_runtime = 'sudo ip link set dev %s.%d up\n' % (interface,nodeNumber2)
					w_runtime.write(line_runtime)
					line_runtime = 'sudo brctl addif brSATEMU %s.%d\n' % (interface,nodeNumber2)
					w_runtime.write(line_runtime)
					line_runtime = str('sudo iptables -A PREROUTING -t mangle -m physdev --physdev-in %s.%d -j MARK --set-mark %d\n'%(interface,nodeNumber2,n))
					w_runtime.write(line_runtime)
					line_shutdown = str('sudo iptables -D PREROUTING -t mangle -m physdev --physdev-in %s.%d -j MARK --set-mark %d\n'%(interface,nodeNumber2,n))
					w_shutdown.write(line_shutdown)
					# Add the conditions of the channel
					line_runtime = str('sudo tc qdisc add dev %s.%d root netem loss 100'%(interface,nodeNumber2))
					line_runtime += '%\n'
					w_runtime.write(line_runtime)
		#Creates one classid per node in every Vlan interface and define channel properties
		for n in range(1,self._nNodes+1):
			if self._node_list[n-1].check_VM():
				interface = self._node_list[n-1]._get_Host_interface()
				for j in range(1,self._nNodes+1):
					#Obtain the delay between the nodes n-1 and j-1
					delay = self._channel.get_channel(n-1,j-1)
					#print('Delay between %s and %s: %fms'%(self._node_list[n-1].get_basic_data(),self._node_list[j-1].get_basic_data(),delay))
					if delay == -2:
						#Create a classid in the interface of the vlan n (of the node in the position: n-1) to define the channel with de node j-1
						line_runtime = str('sudo tc class add dev %s.%d parent 1: classid 1:%d htb rate 100mbit\n'%(interface,n,j))
						w_runtime.write(line_runtime)
						# Add the conditions of the channel
						line_runtime = str('sudo tc qdisc add dev %s.%d parent 1:%d handle 1%d: netem loss 100\n'%(interface,n,j,j))
						w_runtime.write(line_runtime)
					else:
						Channel = self._channel._Get_Channel_Definition(self._node_list[n-1],self._node_list[j-1])
						#Create a classid in the interface of the vlan n (of the node in the position: n-1) to define the channel with de node j-1
						try:
							line_runtime = str('sudo tc class add dev %s.%d parent 1: classid 1:%d htb rate %fmbit\n'%(interface,n,j,Channel['Data_rate']))
						except KeyError or TypeError:
							line_runtime = str('sudo tc class add dev %s.%d parent 1: classid 1:%d htb rate 100mbit\n'%(interface,n,j))
						w_runtime.write(line_runtime)
						# Add the conditions of the channel
						if delay == -1:
							line_runtime = str('sudo tc qdisc add dev %s.%d parent 1:%d handle 1%d: netem loss 100\n'%(interface,n,j,j))
							w_runtime.write(line_runtime)

						else:
							Losses = str(Channel['Packet_loss'])+'%'
							Correlated_losses = str(Channel['Correlated_losses'])+'%'
							line_runtime = str('sudo tc qdisc add dev %s.%d parent 1:%d handle 1%d: netem delay %fms loss %s %s\n'%(interface,n,j,j,delay,Losses,Correlated_losses))
							w_runtime.write(line_runtime)
					ip = ip_Address[j-1]
					# Define filters according to the source ip 
					line_runtime = str('sudo tc filter add dev %s.%d protocol ip parent 1:0 prio 1 handle %d fw flowid 1:%d\n'%(interface,n,j,j))
					w_runtime.write(line_runtime)
					#line_runtime = str('sudo tc filter add dev %s.%d parent 1: protocol arp prio 1 u32 match u32 0 0 flowid 1:%d\n'%(interface,n,j))
					#w_runtime.write(line_runtime)

				if self._node_list[n-1].is_external_vm:
					line_shutdown = str(f"sshpass -p '{self._node_list[n-1]._password}' ssh -o StrictHostKeyChecking=no {self._node_list[n-1]._username}@{self._node_list[n-1].ip_ext} 'sudo -S ip link del {interface}'\n")
					w_shutdown.write(line_shutdown)
		# Tear down global interfaces after all per-node cleanup
		w_shutdown.write('sudo ip link set vsnes_ext down\n')
		w_shutdown.write('sudo ip link del vsnes_ext\n')
		w_shutdown.write('sudo iptables -D FORWARD -i %s -o virbr0 -s %s -d 192.168.122.0/24 -j ACCEPT\n'%(host_interface, Network_ext))
		w_shutdown.write('sudo ip link set dev brSATEMU down\n')
		w_shutdown.write('sudo brctl delbr brSATEMU\n')
		# Close opened files
		w_runtime.close()
		w_shutdown.close()
		# Make the files executable
		subprocess.run(['chmod', '+x', 'runtime_bash.sh'])
		subprocess.run(['chmod', '+x', 'shutdown_bash.sh'])
	def get_speed(self):
		return self._time_parameters.get_speed(self._channel.get_exist())
	def get_number_of_nodes(self):
		return self._nNodes
	
	def _run_shutdown(self, password=None):
		"""Run shutdown_bash.sh and reset state. Safe to call from any thread."""
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
		exist_net = subprocess.run('virsh net-list | grep -c -w default', capture_output = True, text = True, shell = True).stdout
		if int(exist_net) == 0:
			subprocess.run(['virsh', 'net-start', 'default'])
	
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
			#self._Emulation_startup_script()	
			self.write_bash()

		n_connections = int(1+(self._nNodes-1)*self._nNodes/2)
		logging.info(f"Starting emulation process with {n_connections} connections")
		self._emulator_process = threading.Thread(target=self._run, args=(EMU, True, n_connections, password), daemon=True)
		self._emulator_process.start()


	def _run(self, EMU, CESIUM, n_connections, password=None):

		if EMU:
			logging.info("Executing runtime bash script")
			if password:
				proc = subprocess.run(['sudo', '-S', './runtime_bash.sh'], input=(password + '\n').encode(), capture_output=True)
				if proc.returncode != 0:
					logging.error(f"Error executing runtime script: {proc.stderr.decode()}")
			else:
				subprocess.call('./runtime_bash.sh')

		time.sleep(5)
		
		n_connections = int(1+(self._nNodes-1)*self._nNodes/2)
		self._emit_sim_block()
		time.sleep(self._time_parameters.get_TimeInterval()/self.get_speed())
		Nversion = 0
		clone_czml = czml.CZML()
		ID = 'document'
		name = 'Satellite Network Emulator'
		Nversion += 1
		version= self.czml_doc.packets[0].version[0]+'.'+str(Nversion)
		interval = self._time_parameters.get_interval()
		multiplier = self.get_speed()
		currentTime = self._time_parameters.get_date_time().isoformat()
		clock = czml.Clock(interval=interval,currentTime=currentTime,multiplier=multiplier,range = 'UNBOUNDED',step = 'SYSTEM_CLOCK_MULTIPLIER')
		packet1 = czml.CZMLPacket(id=ID,name=name,version=version,clock=clock)
		packet1.availability = interval
		clone_czml.packets.append(packet1)
		for packet in self.czml_doc.packets[1:]:
			clone_czml.packets.append(packet)
		filename = "Class/templates/ScenarioCZML.czml"
		clone_czml.write(filename)
		self.czml_doc = clone_czml
		with open("simulation_time.txt", "w") as f:
			f.write(currentTime)
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
				
			clone_czml = czml.CZML()
			ID = 'document'
			name = 'Satellite Network Emulator'
			Nversion += 1
			version= self.czml_doc.packets[0].version[0]+'.'+str(Nversion)
			interval = self._time_parameters.get_interval()
			currentTime = self._time_parameters.get_date_time().isoformat()
			clock = czml.Clock(interval=interval,currentTime=currentTime,multiplier=multiplier,range = 'UNBOUNDED',step = 'SYSTEM_CLOCK_MULTIPLIER')
			packet1 = czml.CZMLPacket(id=ID,name=name,version=version,clock=clock)
			packet1.availability = interval
			clone_czml.packets.append(packet1)
			for packet in self.czml_doc.packets[1:]:
				clone_czml.packets.append(packet)
			filename = "Class/templates/ScenarioCZML.czml"
			clone_czml.write(filename)
			self.czml_doc = clone_czml
			with open("simulation_time.txt", "w") as f:
				f.write(currentTime)
			time.sleep(stopTime)
	
	
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
		for Node in self._node_list:
			Node.arp_table(self._node_list)
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
				result = self._channel.czml_channels(self._time_parameters.get_datetimes(),self._node_list[n],self._node_list[j])
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
