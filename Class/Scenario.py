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
		try:
			self._time_parameters = time_parameters(TOMLfile['Time'])
		except KeyError:
			TOMLfile['Time'] = {}
			self._time_parameters = time_parameters(TOMLfile['Time'])
		self._node_list = []
		self._channel = channel(TOMLfile['Channels'])
		self._nNodes = 0
		global ip_Address
		global Network
		while True:
			Network = TOMLfile['network']
			try:
				Network = IPv4Network(Network)
				break
			except AddressValueError:
				print('ERROR: Invalid format')
				network = input('What is the correct IP address of the network?[10.0.0.0/24]')
				if network == '':
					network = '10.0.0.0/24'
				Network = TOMLfile['network'] = network
			except ValueError:
				network = input('ERROR: %s has host bits set. What is the correct IP address of the network?[10.0.0.0/24]'%(TOMLfile['network']))
		print(Network)
		for addr in Network:
			ip_Address.append(addr)
		ip_Address = ip_Address[1:-1]
		try:
			SpaceSegment = TOMLfile['SpaceSegment']
		except KeyError:
			TOMLfile['SpaceSegment'] = {}
		try:
			for SatelliteSistem in SpaceSegment['SatelliteSistem']:
				try:
					config_file = SatelliteSistem['TLE']
				except KeyError:
					pass
				satellites = load.tle_file(config_file)
				for sat in satellites:
					self.AddSatellite(sat,SatelliteSistem)
		except UnboundLocalError:
			pass
		try:
			GroundSegment = TOMLfile['GroundSegment']
		except KeyError:
			pass
		for GroundSistem in GroundSegment['GroundSistem']:
			self.AddGroundStation(GroundSistem)
		# Read an existing CZML file
		filename = 'Class/templates/ScenarioCZML.czml'
		with open(filename, 'r') as example:
			if os.stat(filename).st_size == 0:
				self.write_czml()
			else:
				self.czml_doc = czml.CZML()
				self.czml_doc.loads(example.read())
		#print(toml.dumps(TOMLfile))
	def AddSatellite(self,sat_tle,constallation):
		#Creates a Satellite object and add to the scenario
		try:
			#Creade a Satellite Node
			SAT = Satellite(sat_tle,constallation,ip_Address[self._nNodes],Network.netmask,self._nNodes,self._time_parameters.get_datetimes())
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
				self._channel.AddNode(self._node_list,self._nNodes,self._time_parameters._marker)
		except IndexError:
			print ('Maximum number of nodes exceeded: Node NOT ACCEPTED')
			return
		

	def AddGroundStation(self,TOML_GS):
		#Creates a GroundStation object and add to the scenario
		try:
			#Creade a GroundStation Node
			GS = GroundStation(TOML_GS, ip_Address[self._nNodes], Network.netmask,self._nNodes)
			#Check if the node exist yet
			if self.Exist_Node(GS) or GS.name == None:
				print ("- Ground Station %s: NOT ACCEPTED"%(GS.name))
				return None
			else:
				self._node_list.append(GS)
				print ("- Ground Station %s: ADDED"%(GS.name))				
				#Add 1 to the node counter	
				self._nNodes += 1
				#Add a new node to the channel
				self._channel.AddNode(self._node_list,self._nNodes,self._time_parameters._marker)
		except IndexError:
			print ('Maximum number of nodes exceeded: Node NOT ACCEPTED')
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
		w_runtime.write('sudo brctl addbr brSATEMU\nsudo ip link set dev brSATEMU up\n')
		#Command to delete the bridge
		w_shutdown.write('sudo ip link set dev brSATEMU down\nsudo brctl delbr brSATEMU\n')
		w_runtime.write('sudo brctl stp brSATEMU off\nsudo brctl setageing brSATEMU 0\nsudo brctl setfd brSATEMU 0\n')
		
		for n in range(1,self._nNodes+1):
			if self._node_list[n-1].check_VM():
				#Loop from 1 to one more than the number of nodes to define one VLAN per node and start the VLANs in 1
				interface = self._node_list[n-1]._get_Host_interface()
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
				if self._node_list[n-1].service == 'relay' or self._node_list[n-1].service == 'Relay' or self._node_list[n-1].service == 'RELAY':
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
					if delay == -2:
						#Create a classid in the interface of the vlan n (of the node in the position: n-1) to define the channel with de node j-1
						line_runtime = str('sudo tc class add dev %s.%d parent 1: classid 1:%d htb rate 100mbit\n'%(interface,n,j))
						w_runtime.write(line_runtime)
						# Add the conditions of the channel
						line_runtime = str('sudo tc qdisc add dev %s.%d parent 1:%d handle 1%d: netem loss 100'%(interface,n,j,j))
						line_runtime += '%\n'
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
							line_runtime = str('sudo tc qdisc add dev %s.%d parent 1:%d handle 1%d: netem loss 100'%(interface,n,j,j))
							line_runtime = line_runtime + '%\n'
						else:
							Losses = str(Channel['Packet_loss'])+'%'
							Correlated_losses = str(Channel['Correlated_losses'])+'%'
							line_runtime = str('sudo tc qdisc add dev %s.%d parent 1:%d handle 1%d: netem delay %fms loss %s %s\n'%(interface,n,j,j,delay,Losses,Correlated_losses))
					w_runtime.write(line_runtime)
					ip = ip_Address[j-1]
					# Define filters according to the source ip 
					line_runtime = str('sudo tc filter add dev %s.%d protocol ip parent 1:0 prio 1 handle %d fw flowid 1:%d\n'%(interface,n,j,j))
					w_runtime.write(line_runtime)
					# Delete the filters
					line_shutdown = str('sudo tc filter del dev %s.%d protocol ip parent 1:0 prio 1 handle %d fw flowid 1:%d\n'%(interface,n,j,j))
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
			self.write_bash()
			subprocess.call('./runtime_bash.sh')
			n_connections = int(1+(self._nNodes-1)*self._nNodes/2)
			EMULADOR = Process(target=self._run,args=(EMU, CESIUM,n_connections))
			EMULADOR.start()
		if CESIUM:
			if EMU:
				EMU_bool = 'true'
			else:
				EMU_bool = 'false'
			timer_ms = self._time_parameters.get_TimeInterval()/(self._time_parameters._non_contact_speed*4) * 10**3
			if timer_ms > 1000:
				timer_ms = 500
			shell = 'gnome-terminal -t %s -- python3 Class/Server.py %s %f'%('Cesium Server',EMU_bool,timer_ms)
			subprocess.run(shell, shell = True)
			webbrowser.open_new('http://localhost:5000/')
		input("press enter to shutdown\n")
		if EMU:
			EMULADOR.terminate()
			EMULADOR.join()
			subprocess.call('./shutdown_bash.sh')
		for _ in range(3):
				sys.stdout.write("\x1b[1A\x1b[2K")
		self.reset()
	def _run(self,EMU,CESIUM,n_connections):
		start = time.time()
		self._Emulation_startup_script()
		end = time.time()

		#Subtract Start Time from The End Time
		total_time = end - start
		if CESIUM:
			if total_time < 5:
				time.sleep(5-total_time)
		else:
			if total_time < 1:
				time.sleep(1-total_time)
		n_connections = int(1+(self._nNodes-1)*self._nNodes/2)
		String = self._time_parameters.get_date_time().strftime("%m/%d/%Y, %H:%M:%S")
		String += '\n'
		channels = self._channel.possible_channels()
		for channel in channels:
			channel = channel.split('/')
			n = int(channel[0])
			j = int(channel[1])
			String +=  '-%s -> %s:	 %fms\n'%(self._node_list[n].get_basic_data(),self._node_list[j].get_basic_data(),self._channel.get_channel(n,j))
		sys.stdout.write(String) # print the linesprint (String)
		
		
		for _ in range(len(channels)+1):
			sys.stdout.write("\x1b[1A\x1b[2K") # move up cursor and delete whole line
		time.sleep(self._time_parameters.get_TimeInterval()/self.get_speed())
		Nversion = 0
		if CESIUM:
			clone_czml = czml.CZML()
			ID = 'document'
			name = 'Satellite Network Emulator'
			Nversion += 1
			version= self.czml_doc.packets[0].version[0]+'.'+str(Nversion)
			interval = self._time_parameters.get_interval()
			multiplier = self.get_speed()*0.75
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
		while True:
			# Initialize a document
			start = time.time()
			if self.step(EMU):
				print('The emulation is over: press enter to shutdown')
				sys.stdout.write("\x1b[1A\x1b[2K") # move up cursor and delete whole line'''
				break
			String = self._time_parameters.get_date_time().strftime("%m/%d/%Y, %H:%M:%S")
			String += '\n'
			channels = self._channel.possible_channels()
			for channel in channels:
				channel = channel.split('/')
				n = int(channel[0])
				j = int(channel[1])
				String +=  '-%s -> %s:	 %fms\n'%(self._node_list[n].get_basic_data(),self._node_list[j].get_basic_data(),self._channel.get_channel(n,j))
			sys.stdout.write(String) # print the linesprint (String)
			for _ in range(len(channels)+1):
				sys.stdout.write("\x1b[1A\x1b[2K") # move up cursor and delete whole line
			# Grab Currrent Time After Running the Code
			end = time.time()

			#Subtract Start Time from The End Time
			total_time = end - start
			multiplier = self.get_speed()*0.75
			stopTime=(self._time_parameters.get_TimeInterval()/multiplier)-total_time
			if stopTime < 0:
				multiplier = self._time_parameters.get_TimeInterval()/total_time*0.75
				stopTime = 0
				
			if CESIUM:
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
		delete = False
		for Node in self._node_list:
			if Node.check_VM():
				while True:
					ans = input("Do you want to delete all the VMs relete with the scenario?(Y/N):").strip().lower()
					if ans == 'y' or ans == 'yes':
						delete = True
						break
					elif ans == 'n' or ans == 'no':
						break
					else:
						print('ERROR: Invalid answer')
				break
		if delete:
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
		#print("\n"+ str(total_time))
