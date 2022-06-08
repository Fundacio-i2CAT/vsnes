#!/usr/bin/env python3
from Class.Satellite import Satellite
from Class.Ground_Station import GroundStation
from Class.Time_parameters import time_parameters
from Class.Channel import channel
from skyfield.api import load, wgs84
from ipaddress import IPv4Network
from czml import czml
import time
import subprocess
import threading

path_apache = '/var/www/SNES/'
# class for the creation and management of nodes and channels. 
class scenario:
	'''A scenario load a configuration file and managed different classes'''
	#The node_list property agrups all the nodes(Satellites and Graond Stations)
	_node_list = None
	
	#The channel property defines a Channel class to calcule the delay of the diferents pair of nodes
	_channel = None
	
	#nNodes property is the number of nodes that are loaded in the scenario
	_nNodes = None
	
	#The time paeameters property defines a time_paramiters class witch control the time of the emulation
	_time_parameters = None
	
	#Ip address is a list of the posible ip address that can be assigned to the nodes
	_ip_Address = None
	
	#The network property defines the network address of the scenario
	_Network = None
	
	def __init__(self,TOMLfile,run_VM = True):
		self.start_Network()
		self._time_parameters = time_parameters(TOMLfile['Time'])
		self._node_list = []
		self._channel = channel(TOMLfile['Channel'])
		self._nNodes = 0
		ip_Address = []
		Network = TOMLfile['Network']['network']
		self._Network = IPv4Network(Network)
		while True:
			try:
				for addr in self._Network:
					ip_Address.append(addr)
				break
			except ValueError:
				Network = input('%s is not a possible network. Insert a correct one:'%(Network)) 
		self._ip_Address = ip_Address[1:-1]
		self.interface = TOMLfile['Network']['interface']
		SpaceSegment = TOMLfile['SpaceSegment']
		for SatelliteSistem in SpaceSegment['SatelliteSistem']:
			config_file = SatelliteSistem['TLE']
			satellites = load.tle_file(config_file)
			for sat in satellites:
				self.AddSatellite(sat,SatelliteSistem,run_VM)
		GroundSegment = TOMLfile['GroundSegment']
		for GroundSistem in GroundSegment['GroundSistem']:
			self.AddGroundStation(GroundSistem,run_VM)
		self.write_czml()
	def AddSatellite(self,sat_czml,constallation,run_VM):
		#Creates a Satellite object and add to the scenario
		try:
			#Creade a Satellite Node
			SAT = Satellite(sat_czml,constallation,self._ip_Address[self._nNodes],self._Network.netmask,self._nNodes)
			#Check if the node exist yet
			if self.Exist_Node(SAT):
				print ("- Satellite %s: NOT ACCEPTED"%(SAT.name))
			else:
				#Add the node to the node list
				self._node_list.append(SAT)
				print ("- Satellite %s: ADDED"%(SAT.name))
				#Create or start a VM related with the node
				if run_VM: SAT.run_VM()
				#Add 1 to the  node counter
				#self._node_list[self._nNodes].update_position(self._time_parameters.get_date_time())	
				self._nNodes += 1
				#Add a new node to the channel
				self._channel.AddNode(self._node_list,self._nNodes,self._time_parameters.get_date_time())
		except IndexError:
			print ('Maximum number of nodes exceeded: Node NOT ACCEPTED')
			return
		

	def AddGroundStation(self,TOML_GS,run_VM):
		#Creates a GroundStation object and add to the scenario
		try:
			#Creade a GroundStation Node
			GS = GroundStation(TOML_GS, self._ip_Address[self._nNodes], self._Network.netmask,self._nNodes)
			#Check if the node exist yet
			if self.Exist_Node(GS):
				print ("- Ground Station %s: NOT ACCEPTED"%(GS.name))
				return None
			else:
				self._node_list.append(GS)
				print ("- Ground Station %s: ADDED"%(GS.name))
				#Create or start a VM related with the node
				if run_VM: GS.run_VM()
				#Add 1 to the node counter
				#self._node_list[self._nNodes].update_position(self._time_parameters.get_date_time())	
				self._nNodes += 1
				#Add a new node to the channel
				self._channel.AddNode(self._node_list,self._nNodes,self._time_parameters.get_date_time())
		except IndexError:
			print ('Maximum number of nodes exceeded: Node NOT ACCEPTED')
			return	
	def _update(self,EMU = False):
		# channel is updated with the delay at one precise time instant.
		# EMU equals True, update the rules of the interfaces to represent the delay and the channel discontinuation
		datetime = self._time_parameters.get_date_time()
		self._channel.update(self._node_list,self._nNodes,datetime,EMU,self.interface)
	def delate (self):
		# delate all the nodes and channels
		self._node_list = []
		self._channel.delete()
		self._nNodes = 0
	def step(self,EMU = False,CESIUM = False):
		# change date_time marker and update the scenario
		if self._time_parameters.step():
			self.reset()
			return True
		else:
			self._update(EMU = EMU)
			return False
	def reset(self):
		# restart the parameters of simulatión, put date_time marker equal to 0 and update de scenario
		self._time_parameters.reset()
		self._update()
	def write_bash (self):
		# write two bash files, one for define the scenario and  other to delete the configuration of the first file.
		#Open the two bash files
		w_runtime = open("runtime_bash.sh", "w")
		w_shutdown = open("shutdown_bash.sh", "w")
		w_runtime.write('#!/bin/sh\n')
		w_shutdown.write('#!/bin/sh\n')
		#Command to create a bridge with name brSATEMU
		w_runtime.write('brctl addbr brSATEMU\nip link set dev brSATEMU up\n')
		#Command to delete the bridge
		w_shutdown.write('ip link set dev brSATEMU down\nbrctl delbr brSATEMU\n')
		interface = self.interface
		for n in range(1,self._nNodes+1):
			#Loop from 1 to one more than the number of nodes to define one VLAN per node and start the VLANs in 1
			
			# Define an interface in a VLAN
			line_runtime = str('ip link add link %s name %s.%d type vlan id %d\n'%(interface,interface,n,n))
			w_runtime.write(line_runtime)
			#Set up
			line_runtime = str('ip link set dev %s.%d up\n'%(interface,n))
			w_runtime.write(line_runtime)
			#Add the interface to the bridge
			line_runtime = str('brctl addif brSATEMU %s.%d\n'%(interface,n))
			w_runtime.write(line_runtime)
			#Defines a tc qdisc root
			line_runtime = str('tc qdisc add dev %s.%d root handle %d: htb\n'%(interface,n,n))
			w_runtime.write(line_runtime)
			#Delete the root of tc qdisc
			line_shutdown = str('tc qdisc del dev %s.%d root handle %d: htb\n'%(interface,n,n))
			w_shutdown.write(line_shutdown)
			# Delete the interface associated with the VLAN 
			line_shutdown = str('ip link del link %s name %s.%d type vlan id %d\n'%(interface,interface,n,n))
			w_shutdown.write(line_shutdown)
		#Creates one classid per node in every Vlan interface and define channel properties
		for n in range(1,self._nNodes+1):
			for j in range(1,self._nNodes+1):
				#Create a classid in the interface of the vlan n (of the node in the position: n-1) to define the channel with de node j-1
				line_runtime = str('tc class add dev %s.%d parent %d: classid %d:%d htb rate 100mbit\n'%(interface,n,n,n,j))
				w_runtime.write(line_runtime)
				# Add the conditions of the channel
				#Obtain the delay between the nodes n-1 and j-1
				delay = self._channel.get_channel(n-1,j-1)
				if delay == -1:
					line_runtime = str('tc qdisc add dev %s.%d parent %d:%d handle %d%d: netem loss 100'%(interface,n,n,j,n,j))
					line_runtime = line_runtime + '%\n'
				else:
					line_runtime = str('tc qdisc add dev %s.%d parent %d:%d handle %d%d: netem delay %fms\n'%(interface,n,n,j,n,j,delay))
				w_runtime.write(line_runtime)
				ip = self._ip_Address[j-1]
				# Define filters according to the source ip 
				line_runtime = str('tc filter add dev %s.%d protocol ip parent %d:0 prio 1 u32 match ip src %s/32 flowid %d:%d\n'%(interface,n,n,ip,n,j))
				w_runtime.write(line_runtime)
				# Delete the filters
				line_shutdown = str('tc filter del dev %s.%d protocol ip parent %d:0 prio 1 u32 match ip src %s/32 flowid %d:%d\n'%(interface,n,n,ip,n,j))
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
	def run(self,stop_threads,EMU,CESIUM):
		print (self._time_parameters.get_date_time())
		print ('-Delay SAT1->SAT2: ',self._channel.get_channel(0,1))
		print ('-Delay SAT1->i2CAT: ',self._channel.get_channel(0,2))
		print ('-Delay SAT2->i2CAT: ',self._channel.get_channel(1,2))
		time.sleep(60*self._time_parameters.get_TimeInterval()/self.get_speed())
		while True:
			if stop_threads:
				break
			if self.step(EMU,CESIUM):
				print('The emulation is over: press enter to shutdown')
				break
			print (self._time_parameters.get_date_time())
			print ('-Delay SAT1->SAT2: ',self._channel.get_channel(0,1))
			print ('-Delay SAT1->i2CAT: ',self._channel.get_channel(0,2))
			print ('-Delay SAT2->i2CAT: ',self._channel.get_channel(1,2))
			#print (scenario.channel_matrix)
			time.sleep(60*self._time_parameters.get_TimeInterval()/self.get_speed())
		if EMU:subprocess.call('./shutdown_bash.sh')
	def delete_VMs (self):
		for n in range(0,self._nNodes):
			self._node_list[n].delete_VM()
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
	def write_czml (self):
		# Initialize a document
		doc = czml.CZML()
		# Create and append the document packet
		ID = 'document'
		name = 'Satellite Network Emulator'
		version='1.0'
		interval = self._time_parameters.get_interval()
		currentTime = self._time_parameters.get_date_time().isoformat()
		multiplier = self._time_parameters.get_speed()
		clock = czml.Clock(interval=interval,currentTime=currentTime,multiplier=multiplier,range = None,step = None)
		packet1 = czml.CZMLPacket(id=ID,name=name,version=version,clock=clock)
		doc.packets.append(packet1)
		
		processes = []
		czml_nodes = []
		results = []
		index = 0
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
		'''	
		for channel in self._channel.czml_channels(self._time_parameters.datetime_vector,self._node_list):
			doc.packets.append(channel)'''
		for process in processes:
			process.join()
		for result in results:
			if result is not None:
				doc.packets.append(result)
		'''print (len(czml_nodes))
		for czmlPacket in czml_nodes:
			doc.packets.append(czmlPacket)
		print (len(czml_channels))
		for czmlPacket in czml_channels:
			doc.packets.append(czmlPacket)'''
		'''
		# Create and append a billboard packet
		packet2 = czml.CZMLPacket(id='billboard')
		bb = czml.Billboard(scale=0.7, show=True)
		bb.image = 'http://localhost/img.png'
		bb.color = {'rgba': [0, 255, 127, 55]}
		packet2.billboard = bb
		doc.packets.append(packet2)
		'''
		# Write the CZML document to a file
		filename = path_apache+"test.czml"
		doc.write(filename)
