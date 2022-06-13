#!/usr/bin/env python3
from Class.Node import Node
from skyfield.api import wgs84
from czml import czml
class GroundStation(Node):
	'''Specific node type which the particularity  of a static position in the Earth surface.'''
		
	def __init__(self,TOML_GS,network,mask, nNodes):
		# Creates a GroundStation class object from three configuration lines
		name = TOML_GS['name']
		latitude = TOML_GS['latitude']
		longitude = TOML_GS['longitude']
		height = TOML_GS['height']
		channels = TOML_GS['channels']
		clone_VM = TOML_GS['clone_VM']
		self._position = wgs84.latlon(latitude,longitude,height)
		Node.__init__(self,name = name,channels = channels,cloneVM = clone_VM,network = network, mask = mask,nNodes = nNodes)
	def update_position(self,date_time):
		#No update nothing because is a static node
		pass
	def czml_node(self,datetime_vector,results,index):
		#Return object of type CZMLPacket
		#Create a object of clas CZMLPacket
		GS = czml.CZMLPacket(id=self.name,name=self.name)
		
		#Create a object of clas Billboard
		bb = czml.Billboard(scale=1.5, show=True)
		#Defines image from the Billboard
		bb.image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAADsMAAA7DAcdvqGQAAACvSURBVDhPrZDRDcMgDAU9GqN0lIzijw6SUbJJygUeNQgSqepJTyHG91LVVpwDdfxM3T9TSl1EXZvDwii471fivK73cBFFQNTT/d2KoGpfGOpSIkhUpgUMxq9DFEsWv4IXhlyCnhBFnZcFEEuYqbiUlNwWgMTdrZ3JbQFoEVG53rd8ztG9aPJMnBUQf/VFraBJeWnLS0RfjbKyLJA8FkT5seDYS1Qwyv8t0B/5C2ZmH2/eTGNNBgMmAAAAAElFTkSuQmCC"
		#Defines eyeOffset from the Billboard
		bb.eyeOffset = {"cartesian":[0,0,0]}
		#Defines pixelOffset from the Billboard
		bb.pixelOffset = {"cartesian2":[0,0]}
		#Defines color from the Billboard
		bb.color = 1.0
		
		
		#Create a object of clas Position
		position =czml.Position()
		#Calcule the position in ECEF
		ECEF = self.get_ECEF()
		#Defines cartesian from the position
		position.cartesian =[ECEF[0],ECEF[1],ECEF[2]]
		
		description = "<p>Ground Station %s:\n-ip address: %s\nPosition:\n-Latitud: %fº\n-Longitude: %fº\n-Height: %fm</p>"%(self.name,str(self._ip),self._position.latitude.degrees,self._position.longitude.degrees,self._position.elevation.m)
		
		#Create a object of clas Label
		label_text = '%s\n(ip:%s)'%(self.name,str(self._ip))
		label =czml.Label(text = label_text,show = True)
		#Defines horizontalOrigin from the Label
		label.horizontalOrigin ='CENTER'
		#Defines verticalOrigin from the Label
		label.verticalOrigin ='DOWN'
		#Defines scale from the Label
		label.scale = 0.5
		#Defines pixelOffset from the Label
		label.pixelOffset = {"cartesian2":[30,20]}
		
		#GS.description=str("Hello World")
		#Defines billboard from the CZMLPacket
		GS.billboard = bb
		#Defines position from the CZMLPacket
		GS.position = position
		#Defines label from the CZMLPacket
		GS.label = label
		#GS.description = description
		results[index] = GS
		return GS
