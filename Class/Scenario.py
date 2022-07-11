#!/usr/bin/env python3

from Class.Satellite import Satellite
from Class.Ground_Station import GroundStation
from Class.Time_parameters import time_parameters
from Class.Channel import channel

from skyfield.api import load
from ipaddress import IPv4Network
from czml import czml

import time
import subprocess
import webbrowser
import threading
from multiprocessing import Process
import sys
ip_Address = []
Network = None
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
		
	def __init__(self,TOMLfile):
		self.start_Network()
		self._time_parameters = time_parameters(TOMLfile['Time'])
		self._node_list = []
		self._channel = channel(TOMLfile['Channel'])
		self._nNodes = 0
		global ip_Address
		global Network
		Network = TOMLfile['Network']['network']
		Network = IPv4Network(Network)
		while True:
			try:
				for addr in Network:
					ip_Address.append(addr)
				break
			except ValueError:
				Network = input('%s is not a possible network. Insert a correct one:'%(Network)) 
		ip_Address = ip_Address[1:-1]
		self.interface = TOMLfile['Network']['interface']
		SpaceSegment = TOMLfile['SpaceSegment']
		for SatelliteSistem in SpaceSegment['SatelliteSistem']:
			config_file = SatelliteSistem['TLE']
			satellites = load.tle_file(config_file)
			for sat in satellites:
				self.AddSatellite(sat,SatelliteSistem)
		GroundSegment = TOMLfile['GroundSegment']
		for GroundSistem in GroundSegment['GroundSistem']:
			self.AddGroundStation(GroundSistem)
		self.write_bash()
		# Read an existing CZML file
		filename = 'Class/templates/ScenarioCZML.czml'
		with open(filename, 'r') as example:
			self.czml_doc = czml.CZML()
			self.czml_doc.loads(example.read())
		self.czml_doc
	def AddSatellite(self,sat_toml,constallation):
		#Creates a Satellite object and add to the scenario
		try:
			#Creade a Satellite Node
			SAT = Satellite(sat_toml,constallation,ip_Address[self._nNodes],Network.netmask,self._nNodes)
			#Check if the node exist yet
			if self.Exist_Node(SAT):
				print ("- Satellite %s: NOT ACCEPTED"%(SAT.name))
			else:
				#Add the node to the node list
				self._node_list.append(SAT)
				print ("- Satellite %s: ADDED"%(SAT.name))
				#Add 1 to the  node counter
				self._nNodes += 1
				#Add a new node to the channel
				self._channel.AddNode(self._node_list,self._nNodes,self._time_parameters.get_date_time())
		except IndexError:
			print ('Maximum number of nodes exceeded: Node NOT ACCEPTED')
			return
		

	def AddGroundStation(self,TOML_GS):
		#Creates a GroundStation object and add to the scenario
		try:
			#Creade a GroundStation Node
			GS = GroundStation(TOML_GS, ip_Address[self._nNodes], Network.netmask,self._nNodes)
			#Check if the node exist yet
			if self.Exist_Node(GS):
				print ("- Ground Station %s: NOT ACCEPTED"%(GS.name))
				return None
			else:
				self._node_list.append(GS)
				print ("- Ground Station %s: ADDED"%(GS.name))				
				#Add 1 to the node counter	
				self._nNodes += 1
				#Add a new node to the channel
				self._channel.AddNode(self._node_list,self._nNodes,self._time_parameters.get_date_time())
		except IndexError:
			print ('Maximum number of nodes exceeded: Node NOT ACCEPTED')
			return	
	def step(self,EMU = False):
		# change date_time marker and update the scenario
		if self._time_parameters.step():
			self.reset()
			return True
		else:
			datetime = self._time_parameters.get_date_time()
			self._channel.update(self._node_list,self._nNodes,datetime,EMU,self.interface)
			return False
	def reset(self):
		# restart the parameters of simulatión, put date_time marker equal to 0 and update de scenario
		self._time_parameters.reset()
		datetime = self._time_parameters.get_date_time()
		self._channel.update(self._node_list,self._nNodes,datetime,False,self.interface)
	def write_bash (self):
		# write two bash files, one for define the scenario and  other to delete the configuration of the first file.
		#Open the two bash files
		w_runtime = open("runtime_bash.sh", "w")
		w_shutdown = open("shutdown_bash.sh", "w")
		w_runtime.write('#!/bin/sh\n')
		w_shutdown.write('#!/bin/sh\n')
		#Command to create a bridge with name brSATEMU
		w_runtime.write('sudo brctl addbr brSATEMU\nsudo ip link set dev brSATEMU up\n')
		#Command to delete the bridge
		w_shutdown.write('sudo ip link set dev brSATEMU down\nsudo brctl delbr brSATEMU\n')
		interface = self.interface
		for n in range(1,self._nNodes+1):
			#Loop from 1 to one more than the number of nodes to define one VLAN per node and start the VLANs in 1
			
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
			line_runtime = str('sudo tc qdisc add dev %s.%d root handle %d: htb\n'%(interface,n,n))
			w_runtime.write(line_runtime)
			#Delete the root of tc qdisc
			line_shutdown = str('sudo tc qdisc del dev %s.%d root handle %d: htb\n'%(interface,n,n))
			w_shutdown.write(line_shutdown)
			# Delete the interface associated with the VLAN 
			line_shutdown = str('sudo ip link del link %s name %s.%d type vlan id %d\n'%(interface,interface,n,n))
			w_shutdown.write(line_shutdown)
		#Creates one classid per node in every Vlan interface and define channel properties
		for n in range(1,self._nNodes+1):
			for j in range(1,self._nNodes+1):
				#Create a classid in the interface of the vlan n (of the node in the position: n-1) to define the channel with de node j-1
				line_runtime = str('sudo tc class add dev %s.%d parent %d: classid %d:%d htb rate 100mbit\n'%(interface,n,n,n,j))
				w_runtime.write(line_runtime)
				# Add the conditions of the channel
				#Obtain the delay between the nodes n-1 and j-1
				delay = self._channel.get_channel(n-1,j-1)
				if delay == -1:
					line_runtime = str('sudo tc qdisc add dev %s.%d parent %d:%d handle %d%d: netem loss 100'%(interface,n,n,j,n,j))
					line_runtime = line_runtime + '%\n'
				else:
					line_runtime = str('sudo tc qdisc add dev %s.%d parent %d:%d handle %d%d: netem delay %fms\n'%(interface,n,n,j,n,j,delay))
				w_runtime.write(line_runtime)
				ip = ip_Address[j-1]
				# Define filters according to the source ip 
				line_runtime = str('sudo tc filter add dev %s.%d protocol ip parent %d:0 prio 1 u32 match ip src %s/32 flowid %d:%d\n'%(interface,n,n,ip,n,j))
				w_runtime.write(line_runtime)
				# Delete the filters
				line_shutdown = str('sudo rtc filter del dev %s.%d protocol ip parent %d:0 prio 1 u32 match ip src %s/32 flowid %d:%d\n'%(interface,n,n,ip,n,j))
				#w_shutdown.write(line_shutdown)
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
	def start_Network (self):
		exist_net = subprocess.run('virsh net-list | grep -c -w default', capture_output = True, text = True, shell = True).stdout
		if int(exist_net) == 0:
			subprocess.run(['virsh', 'net-start', 'default'])
	def start_scenario(self,EMU,CESIUM):
		
		if EMU:
			self.check_VMs()
			subprocess.call('./runtime_bash.sh')
			n_connections = int(1+(self._nNodes-1)*self._nNodes/2)
			EMULADOR = Process(target=self._run,args=(EMU, CESIUM,n_connections))
			EMULADOR.start()
		if CESIUM:
			if EMU:
				EMU_bool = 'true'
			else:
				EMU_bool = 'false'
			timer_ms = self._time_parameters.get_TimeInterval()/self._time_parameters._non_contact_speed * 10**3
			shell = 'gnome-terminal -t %s -- python3 Class/Server.py %s %f'%('Cesium Server',EMU_bool,timer_ms)
			subprocess.run(shell, shell = True)
			webbrowser.open_new('http://localhost:5000/')
		input("press enter to shutdown\n")
		if EMU:
			EMULADOR.terminate()
			EMULADOR.join()
			subprocess.call('./shutdown_bash.sh')
			for _ in range(n_connections):
				sys.stdout.write("\x1b[1A\x1b[2K")
		for _ in range(3):
				sys.stdout.write("\x1b[1A\x1b[2K")
		self.reset()
	def _run(self,EMU,CESIUM,n_connections):
		
		time.sleep(1)
		n_connections = int(1+(self._nNodes-1)*self._nNodes/2)
		String = self._time_parameters.get_date_time().strftime("%m/%d/%Y, %H:%M:%S")
		String += '\n'
		for n in range(self._nNodes):
			for j in range(n+1,self._nNodes):
				String +=  '-%s -> %s:	 %fms\n'%(self._node_list[n].get_basic_data(),self._node_list[j].get_basic_data(),self._channel.get_channel(n,j))
		sys.stdout.write(String) # reprint the linesprint (String)
		time.sleep(self._time_parameters.get_TimeInterval()/self.get_speed())
		Nversion = 0
		while True:
			# Initialize a document
			start = time.time()
			if self.step(EMU):
				print('The emulation is over: press enter to shutdown')
				sys.stdout.write("\x1b[1A\x1b[2K") # move up cursor and delete whole line'''
				break
			String = self._time_parameters.get_date_time().strftime("%m/%d/%Y, %H:%M:%S")
			String += '\n'
			for n in range(self._nNodes):
				for j in range(n+1,self._nNodes):
					String +=  '-%s -> %s:	 %fms\n'%(self._node_list[n].get_basic_data(),self._node_list[j].get_basic_data(),self._channel.get_channel(n,j))
			for _ in range(n_connections):
				sys.stdout.write("\x1b[1A\x1b[2K") # move up cursor and delete whole line
			sys.stdout.write(String) # print the linesprint (String)
			if CESIUM:
				clone_czml = czml.CZML()
				ID = 'document'
				name = 'Satellite Network Emulator'
				Nversion += 1
				version= self.czml_doc.packets[0].version[0]+'.'+str(Nversion)
				interval = self._time_parameters.get_interval()
				currentTime = self._time_parameters.get_date_time().isoformat()
				multiplier = self.get_speed()
				clock = czml.Clock(interval=interval,currentTime=currentTime,multiplier=multiplier,range = 'UNBOUNDED',step = 'SYSTEM_CLOCK_MULTIPLIER')
				packet1 = czml.CZMLPacket(id=ID,name=name,version=version,clock=clock)
				packet1.availability = interval
				clone_czml.packets.append(packet1)
				for packet in self.czml_doc.packets[1:]:
					clone_czml.packets.append(packet)
				filename = "Class/templates/ScenarioCZML.czml"
				clone_czml.write(filename)
				self.czml_doc = clone_czml
			# Grab Currrent Time After Running the Code
			end = time.time()

			#Subtract Start Time from The End Time
			total_time = end - start
			stopTime=(self._time_parameters.get_TimeInterval()/self.get_speed())-total_time
			if stopTime < 0:
				stopTime = 0
			time.sleep(stopTime)
	def check_VMs(self):
		for Node in self._node_list:
			if not(Node.check_VM()):
				while True:
					ans = input("Not all the VMs are running. Do you want to start all the VMs?(Y/N):").strip().lower()
					if ans == 'y' or ans == 'yes':
						self.start_VMs()
						break
					elif ans == 'n' or ans == 'no':
						break
					else:
						print('ERROR: Invalid answer')
				break
	def delete_VMs (self):
		for n in range(0,self._nNodes):
			self._node_list[n].delete_VM()
	def start_VMs(self):
		for node in self._node_list:
			node.run_VM()
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
	def update_czml(self):
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
		
		processes = []
		czml_nodes = []
		results = []
		results.append(None)
		index = 0
		initial_threads = threading.active_count()
		datetime_vector = []
		date_time = self._time_parameters.get_date_time()
		datetime_vector.append(date_time)
		for node in self._node_list:
			czml_nodes.append(node.czml_node(datetime_vector,results,index))
		czml_channels = self._channel.update(self._node_list,self._nNodes,date_time,True,self.interface,True)
		for packet in czml_nodes:
			self.czml_doc.packets.append(packet)
		for packet in czml_channels:
			self.czml_doc.packets.append(packet)
		# Write the CZML document to a file
		filename = "Class/templates/ScenarioCZML.czml"
		self.czml_doc.write(filename)
		# Grab Currrent Time After Running the Code
		end = time.time()

		#Subtract Start Time from The End Time
		total_time = end - start
		#print("\n"+ str(total_time))
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
		
		processes = []
		results = []
		index = 0
		initial_threads = threading.active_count()
		for node in self._node_list:
			results.append(None)
			x = threading.Thread(target=node.czml_node,args=(self._time_parameters.get_datetimes(),results,index,))
			x.start()
			processes.append(x)
			index +=1
		czml_channels = []
		for n in range(0,self._nNodes):
			for j in range(n+1,self._nNodes):
				results.append(None)
				x = threading.Thread(target=self._channel.czml_channels,args=(self._time_parameters.get_datetimes(),self._node_list[n],self._node_list[j],results,index,))
				x.start()
				processes.append(x)
				index +=1
		len_Processes = len(processes)
		print ('Writting the Cesium configuration file. Packages computed 0/%d.'%(len_Processes))
		sys.stdout.write("\x1b[1A\x1b[2K")
		for process in processes:
			process.join()
			N_working_processes = len_Processes-(threading.active_count()-initial_threads)
			print ('Writting the Cesium configuration file. Packages computed %d/%d.'%(N_working_processes,len_Processes))
			sys.stdout.write("\x1b[1A\x1b[2K")
		for result in results:
			if result is not None:
				self.czml_doc.packets.append(result)
		# Write the CZML document to a file
		filename = "Class/templates/ScenarioCZML.czml"
		self.czml_doc.write(filename)
		
		# Grab Currrent Time After Running the Code
		end = time.time()

		#Subtract Start Time from The End Time
		total_time = end - start
		#print("\n"+ str(total_time))
