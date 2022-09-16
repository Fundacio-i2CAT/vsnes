#!/usr/bin/env python3
import subprocess
from skyfield.api import load
import math
from czml import czml
import time
import numpy as np
#GLOBAL CONSTANTS
a_Earth = 6371000 				# Earth major semi axis [m]
c = 3e8					# Speed of light [m/s]
ts = load.timescale()


class channel:
	'''A channel object defines the delays between node'''
	# The delay matrix property defines a matrix with de deay between a pair of nodes, if there aren't line of sight(LoS) the value is -1
	_dalay_matrix = None
	#The exist_channel property is a boolean which defines if there are one pair of node with LoS 
	_exist_channel = None
	def __init__(self,channel):
		self._dalay_matrix=[]
		self._exist_channel = False
		self.channels = channel['Channel']
	def AddNode(self,node_list,nNodes,marker):
		#Add a new row and a new to the matrix with one new node
		#Creates a empty row to define the new row of the matrix
		new_row = []
		for n in range(0,nNodes-1):
			#Add a new position with the daley of the node n and the new node
			#Calcule the delay betwwen a pair of nodes
			delay = self._Define_Channel(node_list[n],node_list[nNodes-1],marker)
			if not(self._exist_channel) and delay > -1:
				#Check if exist some channel
				self._exist_channel = True
			#Append the dealy between the nodes in the row of the n node to the delay matrix
			self._dalay_matrix[n].append(delay)
			#Append the dealy between the nodes in the row of the new node to a provisional list
			new_row.append(delay)
		#Append a 0 in the diagonal
		new_row.append(-2)
		#Append the new row
		self._dalay_matrix.append(new_row)
	def update(self,node_list,nNodes,marker,EMU):
		#update the value of the delays betwwen the nodes. If EMU is true the method change the delay of the emulator
		#Save the current matrix
		old_matrix = self._dalay_matrix
		#Restart the Boolean to False
		self._exist_channel = False
		delay = 0
		#Compare all the nodes between them
		for n in range(0,nNodes):
			for j in range(0,nNodes):
				if old_matrix[n][j] != -2: 
					if j < n :
						#If j is lower than n the delay of the nodes in the position n and j have benn calulate yet. It only copy the value of the position j:n
						delay = self._dalay_matrix[j][n]
					elif j > n:
						#If j is bigger than n, it calcule the delay between the nodes in the new datetime
						delay = self._Define_Channel(node_list[n],node_list[j],marker)
						if delay > -1 and not(self._exist_channel):
							#Check if exist some channel
							self._exist_channel = True
					if EMU and old_matrix[n][j]!=delay and n != j and node_list[n].check_VM():
						#Update the rules of the netem if EMU is True and the dalay in the before datetime was different 
						interface = '%s.%d'%(node_list[n]._get_Host_interface(),n+1)
						n_j = '1:%d' %(j+1)
						nj = '1%d:' %(j+1)
						if delay == -1:
							#If daley is equal to -1, the channel losses are defined of the 100%
							subprocess.run(['sudo','tc','qdisc','change','dev',interface,'parent',n_j,'handle',nj,'netem','loss','100%'])
						elif delay != 0:
							Channel = self._Get_Channel_Definition(node_list[n],node_list[j])
							str_delay = '%fms' % (delay)
							Losses = str(Channel['Packet_loss'])+'%'
							Burst_Losses = str(Channel['Correlated_losses'])+'%'
							subprocess.run(['sudo','tc','qdisc','change','dev',interface,'parent',n_j,'handle',nj,'netem','delay',str_delay,'loss',Losses,Burst_Losses])
					self._dalay_matrix[n][j] = delay
	def possible_channels(self):
		channels = []
		for n in range(0,len(self._dalay_matrix)):
			for j in range(n+1,len(self._dalay_matrix)):
				if self._dalay_matrix[n][j] > -1:
					channels.append('%d/%d'%(n,j))
		return channels
	def delete(self):
		#Delete the delay matrix
		self._dalay_matrix = []
		self._exist_channel = False
	def get_channel(self,node1 = None,node2 = None):
		if (node1 == None and node2 == None):
			return self._dalay_matrix
		elif node2 == None:
			return self._dalay_matrix[node1]
		elif node1 == None:
			return self._dalay_matrix[:][node2]
		return self._dalay_matrix[node1][node2]
	def get_exist(self):
		#Return exist_channel
		return self._exist_channel	
	def _Define_Channel(self,node, other,marker):
		#Compute the daly beteween nodes.it checks the type of the nodes and make the necessary cumputation. It returns a Bolean and a delay.
		Channel = self._Get_Channel_Definition(node, other)
		if Channel == None:
			return -2
		#Compare the type of the nodes
		elif type(node).__name__ == "Satellite" and type(other).__name__ == "Satellite":
			#Compute the delay between two satellites
			return self._Satellite2Satellite(node.get_ECI(marker),other.get_ECI(marker),Channel['Threshold'])
		elif type(node).__name__ != "Satellite" and type(other).__name__ == "Satellite":
			#Compute the delay between a Satellite and a Ground Station
			try:
				return self._GroundBase2Satellite(other.get_ECEF(marker),node.get_ECEF(),node.get_LLH(),Channel['Min_elevation_angle'],Channel['Threshold'])
			except TypeError:
				return self._GroundBase2Satellite(other.get_ECEF(marker),node.get_ECEF(),node.get_LLH(),0,Channel['Threshold'])
			except KeyError:
				return self._GroundBase2Satellite(node.get_ECEF(marker),other.get_ECEF(),other.get_LLH(),0,Channel['Threshold'])
		elif type(node).__name__ == "Satellite" and type(other).__name__ != "Satellite":
			#Compute the delay between a Satellite and a Ground Station
			try:	
				return self._GroundBase2Satellite(node.get_ECEF(marker),other.get_ECEF(),other.get_LLH(),Channel['Min_elevation_angle'],Channel['Threshold'])
			except TypeError:
				return self._GroundBase2Satellite(node.get_ECEF(marker),other.get_ECEF(),other.get_LLH(),0,Channel['Threshold'])
			except KeyError:
				return self._GroundBase2Satellite(node.get_ECEF(marker),other.get_ECEF(),other.get_LLH(),0,Channel['Threshold'])
		else:
			return -1
	def _Get_Channel_Definition(self,node1,node2):
		name1 = node1.group
		name2 = node2.group
		cont = 0
		for channel in self.channels:
			try:
				if  (channel['Node1'] == name1 and channel['Node2'] == name2) or (channel['Node1'] == name2 and channel['Node2'] == name1):
					while True:
						try:
							channel['Threshold'] = float(channel['Threshold'])
							break
						except KeyError:
							channel['Threshold'] = input('Insert threshold between %s and %s:'%(name1,name2))
						except ValueError:
							channel['Threshold'] = input('Insert again threshold between %s and %s:'%(name1,name2))
					self.channels[cont] = channel
					return channel
			except KeyError:
				pass
			cont += 1
		return None
	
	def _ECEF2NED(self,pseudoDistance,LLH):
		#Return a array in NED (Nord,East,Down) relative of GS from a vector in ECEF
		x = pseudoDistance[0]
		y = pseudoDistance[1]
		z = pseudoDistance[2]
		lat = LLH[0] * math.pi/180
		long = LLH[1] * math.pi/180
		N = -math.sin(lat)*math.cos(long)*x - math.sin(lat)*math.sin(long)*y + math.cos(lat) * z
		E = -math.sin(long)*x + math.cos(long)*y
		D = -math.cos(lat)*math.cos(long)*x - math.cos(lat)*math.sin(long)*y - math.sin(lat)*z
		NED = np.array([N,E,D])
		return NED
	def _NED2AzimuthElevationDistance(self,NED):
		# Computation of the pointing angles and the distance to each of the satellites
		
		d=math.sqrt(NED[0]**2+NED[1]**2+NED[2]**2)	#Distance
		alpha=math.atan(NED[1]/NED[0])*180/math.pi	#Azimuth
		beta=math.asin(-NED[2]/d)*180/math.pi		#Elevation
		return alpha,beta,d
	def _GroundBase2Satellite(self,ECEF_SAT,ECEF_GB,LLH_GB,Min,threshold):
		p = ECEF_SAT-ECEF_GB
		NED = self._ECEF2NED(p,LLH_GB)
		alpha,beta,d = self._NED2AzimuthElevationDistance(NED)
		if (beta >= Min) and d < threshold:
			delay = d/c*1e3
		else:
			delay = -1
		return delay		
	def _Satellite2Satellite(self,ECI1,ECI2,threshold):
		#Compute the delay between two Satellite nodes
		#Find the angle of the cone
		#Note: it can never be greater than 90 º provided that earth_radius < norm (src)
		Er = a_Earth
		norm1 = math.sqrt(ECI1[0]**2+ECI1[1]**2+ECI1[2]**2)
		ECI1_norm = ECI1/norm1
		if norm1 < Er:
			return -1
		theta = math.asin(Er/norm1)
		#Find the angle between the two points
		diff_vec = ECI1 - ECI2
		diff_norm = math.sqrt(diff_vec[0]**2+diff_vec[1]**2+diff_vec[2]**2)
		diff_vec_norm = diff_vec/diff_norm
		dot_res = diff_vec_norm[0] * ECI1_norm [0] + diff_vec_norm[1] * ECI1_norm [1] + diff_vec_norm[2] * ECI1_norm [2]
		diff_angle = math.acos(abs(dot_res))
		#If the angle is greater than theta, then destination must be ouside the cone.
		
		if diff_angle > theta and threshold > diff_norm:
			#Compute the delay in ms in the ideal situation where the propagation speed is the light speed
			delay = diff_norm/c*1e3
			return delay
		elif threshold > diff_norm:
			#In this case, we need to check wether destination is further from the distance to the cone base (i.e. no line of sight) or closer to the cone vertex (i.e. has line of sight)
			#Compute the length of the cone diagonal (i.e. distance from source to sphere tangent point)
			distance_tangent_point= norm1 * math.cos(theta) 
			if diff_norm > distance_tangent_point:
				return -1
			else:
				#Compute the delay in ms in the ideal situation where the propagation speed is the light speed
				delay = diff_norm/c*1e3
				return delay
		else: 
			return -1
	def czml_channels(self,datetime_vector,node1,node2):
		#Return a CZMLPacket objects
		#Defines the name and the id of the new packet. (e.j, ID = Node1.name-to-Node2.name)
		ID =  '%s-to-%s'%(node1.name,node2.name)
		name = '%s to %s'%(node1.name,node2.name)
		#Create a object of clas CZMLPacket
		channel = czml.CZMLPacket(id= ID ,name=name)
		
		Any_channel = False
		#Create a object of clas Polyline
		polyline = czml.Polyline()
		#Defines show from the Polyline like a list
		polyline.show = []
		#last_change save the last datetime when the state of LoS has changed
		last_change = datetime_vector[0].isoformat()
		marker = 0
		#previous_LoS is a boolean that define if there is line of sigth in the previous datetime
		previous_delay = self._Define_Channel(node1,node2,marker)
		if previous_delay != -2:
			StrDescription = "<h2>Access times</h2><table class='sky-infoBox-access-table'><tr><th>Start</th><th>End</th>"
			#The loop search the intervals when there is line of sigth and when there isn't
			for marker in range(1,len(datetime_vector)):
				datetime = datetime_vector[marker]
				#Calcul is there is a LoS
				delay = self._Define_Channel(node1,node2,marker)
				if delay != -1 and previous_delay == -1:
					#When current LoS is different than the previus and True, close a false interval with the datetime in last_change and the value of datetime 
					show = {"interval":last_change+'/%s'%datetime.isoformat(),"boolean":False}
					polyline.show.append(show)
					#update last_change
					last_change = datetime.isoformat()
				elif delay == -1 and previous_delay != -1:
					#When current LoS is different than the previus and False, close a true interval with the datetime in last_change and the value of datetime
					show = {"interval":last_change+'/%s'%datetime.isoformat(),"boolean":True}
					StrDescription += "<tr><td>%s</td><td>%s</td></tr>"%(last_change.split('+')[0].replace('T',' '),datetime.isoformat().split('+')[0].replace('T',' '))
					#color = {"interval":last_change+'/%s'%datetime.isoformat(),"rgba":[0,255,0,255]}
					#colors.append(color)
					polyline.show.append(show)
					#update last_change
					last_change = datetime.isoformat()
					Any_channel = True
				elif datetime == datetime_vector[-1] and delay != -1:
					#When we check all the datetimes of the emulation, it closes the last interval.In that case with a True interval
					show = {"interval":last_change+'/%s'%datetime.isoformat(),"boolean":True}
					StrDescription += "<tr><td>%s</td><td>%s</td></tr></table>"%(last_change.split('+')[0].replace('T',' '),datetime.isoformat().split('+')[0].replace('T',' '))
					#color = {"interval":last_change+'/%s'%datetime.isoformat(),"rgba":[0,255,0,255]}
					#colors.append(color)
					Any_channel = True
					polyline.show.append(show)
				elif datetime == datetime_vector[-1] and delay == -1:
					#When we check all the datetimes of the emulation, it closes the last interval.In that case with a False interval
					show = {"interval":last_change+'/%s'%datetime.isoformat(),"boolean":False}
					polyline.show.append(show)
				
				#Update previous_LoS
				previous_delay = delay
		if Any_channel:
			description = czml.Description(StrDescription)
			#Create a object of clas Color
			color = czml.Color()
			#Defines rgba from the Color
			color.rgba = [0,255,0,255]
			#Create a object of clas SolidColor
			solidColor = czml.SolidColor()
			#Defines color from the SolidColor
			solidColor.color = color
			#Create a object of clas Material
			material = czml.Material()
			#Defines solidColor from the Material
			material.solidColor= solidColor
			#Defines the referen of the position like the position of the a pair of nodes
			references = ['%s#position'%(node1.name),'%s#position'%(node2.name)]
			#Create a object of clas Position with the refereces defined
			position = czml.Positions(references=references)
			#Defines positions from the Polyline
			polyline.positions = position
			#Defines material from the Polyline
			polyline.material = material
			#Defines width from the Polyline
			polyline.width = 1
			polyline.followSurface = False
			#Defines polyline from the CZMLPacket
			channel.polyline = polyline
			channel.description = description
			return channel
