#!/usr/bin/env python3
from Class.Node import Node
from skyfield.api import wgs84
from czml import czml
class GroundStation(Node):
	'''Specific node type which the particularity  of a static position in the Earth surface.'''
		
	def __init__(self,TOML_GS,network,mask, nNodes):
		# Creates a GroundStation class object from three configuration lines
		try:
			name = TOML_GS['name']
		except KeyError:
			name = None
		if name != None:
			while True:
				try:	
					latitude = float(TOML_GS['latitude'])
					break
				except KeyError:
					TOML_GS['latitude'] = input('Insert the %s latitude:'%(name))
				except ValueError:
					TOML_GS['latitude'] = input('Insert again the %s latitude:'%(name))
			while True:
				try:
					longitude = float(TOML_GS['longitude'])
					break
				except KeyError:
					TOML_GS['longitude'] = input('Insert the %s longitudde:'%(name))
				except ValueError:
					TOML_GS['longitude'] = input('Insert again the %s longitude:'%(name))
			while True:	
				try:
					height = float(TOML_GS['height'])
					break
				except KeyError:
					TOML_GS['height'] = input('Insert the %s height:'%(name))
				except ValueError:
					TOML_GS['height'] = input('Insert again the %s height:'%(name))
			self._position = wgs84.latlon(latitude,longitude,height)
		Node.__init__(self,name = name, Node = TOML_GS ,network = network, mask = mask,nNodes = nNodes)
	def description(self):
		description = '<h3>Ground Station %s (ip:%s)</h3>'%(self._name,self._ip)
		description += '<p>Latitud: %fº</p>\n'%(self._position.latitude.degrees)
		description += '<p>Longitude: %fº</p>\n'%(self._position.longitude.degrees)
		description += '<p>Height: %d m</p>\n'%(self._position.elevation.m)
		return description
	def get_ECEF(self):
		#Return the last saved position in ECEF[m]
		return self._position.itrs_xyz.m
	def get_LLH(self):
		#Return the last saved position in Latitud[º], Longitud[º] and heigth [m]
		return [self._position.latitude.degrees,self._position.longitude.degrees,self._position.elevation.m]
	def czml_node(self,datetime_vector):
		#Return object of type CZMLPacket
		#Create a object of clas CZMLPacket
		GS = czml.CZMLPacket(id=self.name)
		#,name=self.name
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
		
		#description = "<p>Ground Station %s:\n-ip address: %s\nPosition:\n-Latitud: %fº\n-Longitude: %fº\n-Height: %fm</p>"%(self.name,str(self._ip),self._position.latitude.degrees,self._position.longitude.degrees,self._position.elevation.m)
		
		#Create a object of clas Label
		label_text = '%s\n(ip:%s)'%(self.name,str(self._ip))
		label =czml.Label(text = label_text,show = True)
		#Defines horizontalOrigin from the Label
		label.horizontalOrigin ='CENTER'
		#Defines verticalOrigin from the Label
		label.verticalOrigin ='UP'
		#Defines scale from the Label
		label.scale = 0.5
		#Defines pixelOffset from the Label
		label.pixelOffset = {"cartesian2":[0,-25]}
		
		description = czml.Description(self.description())
		#Defines billboard from the CZMLPacket
		GS.billboard = bb
		#Defines position from the CZMLPacket
		GS.position = position
		#Defines label from the CZMLPacket
		GS.label = label
		
		GS.description = description
		return GS
