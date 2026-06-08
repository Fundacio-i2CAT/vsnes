#!/usr/bin/env python3
from Class.Node import Node
from skyfield.api import wgs84
from czml import czml
import logging

class GroundStation(Node):
	'''Specific node type which to particularity  of a static position in Earth surface.'''
		
	def __init__(self,TOML_GS,network,mask,nNodes):
		# Creates a GroundStation class object from three configuration lines
		logging.info(f"Initializing Ground Station from TOML configuration")
		
		try:
			name = TOML_GS['name']
		except KeyError:
			error_msg = "Missing 'name' configuration for ground station"
			logging.error(error_msg)
			raise KeyError(error_msg)
			
		if name != None:
			try:	
				latitude = float(TOML_GS['latitude'])
				logging.info(f"Ground station '{name}' latitude set to {latitude}")
			except KeyError:
				error_msg = f"Missing 'latitude' configuration for ground station {name}"
				logging.error(error_msg)
				raise KeyError(error_msg)
			except ValueError:
				error_msg = f"Invalid latitude value for ground station {name}: {TOML_GS['latitude']}"
				logging.error(error_msg)
				raise ValueError(error_msg)
				
			try:
				longitude = float(TOML_GS['longitude'])
				logging.info(f"Ground station '{name}' longitude set to {longitude}")
			except KeyError:
				error_msg = f"Missing 'longitude' configuration for ground station {name}"
				logging.error(error_msg)
				raise KeyError(error_msg)
			except ValueError:
				error_msg = f"Invalid longitude value for ground station {name}: {TOML_GS['longitude']}"
				logging.error(error_msg)
				raise ValueError(error_msg)
				
			try:
				height = float(TOML_GS['height'])
				logging.info(f"Ground station '{name}' height set to {height}")
			except KeyError:
				error_msg = f"Missing 'height' configuration for ground station {name}"
				logging.error(error_msg)
				raise KeyError(error_msg)
			except ValueError:
				error_msg = f"Invalid height value for ground station {name}: {TOML_GS['height']}"
				logging.error(error_msg)
				raise ValueError(error_msg)
				
			self._position = wgs84.latlon(latitude,longitude,height)
			Node.__init__(self,name = name, Node = TOML_GS ,network = network, mask = mask,nNodes = nNodes)
			logging.info(f"Ground station '{name}' initialized successfully")
		else:
			logging.warning("Ground station name is None, skipping initialization")
	def description(self):
		description = '<h3>Ground Station %s (ip:%s)</h3>'%(self._name,self._ip)
		description += '<p>Latitud: %fº</p>\n'%(self._position.latitude.degrees)
		description += '<p>Longitude: %fº</p>\n'%(self._position.longitude.degrees)
		description += '<p>Height: %d m</p>\n'%(self._position.elevation.m)
		return description
	def get_POS(self,marker):
		return [self._position.latitude.degrees,self._position.longitude.degrees,self._position.elevation.m]
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
		bb = czml.Billboard(scale=0.6, show=True)
		#Defines image from the Billboard
		bb.image = "data:image/png;base64,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"
		#Defines eyeOffset from the Billboard
		bb.eyeOffset = {"cartesian":[0,1000,0]}
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
