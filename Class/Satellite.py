#!/usr/bin/env python3

from Class.Orbit import Orbit
from Class.Node import Node
from czml import czml

import math
from sgp4 import exporter
from datetime import datetime,timedelta
class Satellite(Node):
	'''Specific node type which the particularity  of has an orbit.'''
	#Each satellite have a unique Norad ID. The ID property save this code 
	_id = None
	
	#The Orbit property defines the position of the node in relation of datetime.
	_orbit = None
	
	@property
	def id(self):
		return self._id
	
	def __init__(self,sat,constallation,network,mask,nNodes,datetime_vector):
		# Creates a satellite class object from three configuration lines
		self._id = sat.model.satnum
		self._orbit = Orbit(sat)
		Node.__init__(self,name = sat.name,channels = constallation['channels'], cloneVM = constallation['clone_VM'],network = network,mask = mask,nNodes = nNodes)
		self._ECI,self._ECEF = self._orbit._vectors(datetime_vector)
	
	def get_TLE (self):
		#Return the skyfield object TLE
		return self._orbit._TLE
	def get_ECI(self,marker):
		return self._ECI[marker]
	def get_ECEF(self,marker):
		return self._ECEF[marker]
	def description (self):
		description = '<h3>Satellite %s(%s) (ip:%s)</h3>'%(self._name,self._id,self._ip)
		TLE = self._orbit._TLE.model
		line1, line2 = exporter.export_tle(TLE)
		description += '<p><small>%s</small></p>\n'%(line1)
		description += '<p><small>%s</small></p>\n'%(line2)
		return description		
	def _czml_positions(self,datetime_vector):
		#Return a czml object of type position
		#Create a object of clas Position
		position = czml.Position()
		#Defines interpolationAlgorithm from the position
		position.interpolationAlgorithm = 'LAGRANGE'
		#Defines interpolationDegree from the position
		position.interpolationDegree = 5
		#Defines referenceFrame from the position
		position.referenceFrame = 'INERTIAL'
		#cartesian is a list with the next format [time,x,y,z,time,x,y,z....,z]
		cartesian = []
		Period = 2*math.pi/self._orbit._TLE.model.no_kozai
		post_datetime = datetime_vector[-1]+timedelta(minutes=Period+15)
		date_time = datetime_vector[0]
		while date_time < post_datetime:
			#Loop through a vector of datetimes
			#Append datetime
			cartesian.append(date_time.isoformat())
			#Calcule the ECI position in the datetime
			ECI = self._orbit._ECI(date_time)
			#Append x-axis
			cartesian.append(ECI[0])
			#Append y-axis
			cartesian.append(ECI[1])
			#Append z-axis
			cartesian.append(ECI[2])
			date_time += timedelta(minutes=15)
		#Defines cartesian from the position
		position.cartesian = cartesian
		return position	
	def czml_node(self,datetime_vector,results,index):
		#Return object of type CZMLPacket
		#Create a object of clas CZMLPacket
		SAT = czml.CZMLPacket(id=self.name,name=self.name)
		
		#Create a object of clas Billboard
		bb = czml.Billboard(scale=1.5, show=True)
		#Defines image from the Billboard
		bb.image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAADsMAAA7DAcdvqGQAAADJSURBVDhPnZHRDcMgEEMZjVEYpaNklIzSEfLfD4qNnXAJSFWfhO7w2Zc0Tf9QG2rXrEzSUeZLOGm47WoH95x3Hl3jEgilvDgsOQUTqsNl68ezEwn1vae6lceSEEYvvWNT/Rxc4CXQNGadho1NXoJ+9iaqc2xi2xbt23PJCDIB6TQjOC6Bho/sDy3fBQT8PrVhibU7yBFcEPaRxOoeTwbwByCOYf9VGp1BYI1BA+EeHhmfzKbBoJEQwn1yzUZtyspIQUha85MpkNIXB7GizqDEECsAAAAASUVORK5CYII="
		#Defines eyeOffset from the Billboard
		bb.eyeOffset = {"cartesian":[0,0,0]}
		#Defines pixelOffset from the Billboard
		bb.pixelOffset = {"cartesian2":[0,0]}
		#Defines color from the Billboard
		bb.color = 1.0
		
		#description = "<p>Ground Station %s:\n-ip address: %s\nPosition:\n-Latitud: %fº\n-Longitude: %fº\n-Height: %fm</p>"%(self.name,str(self._ip),self.position.latitude.degrees,self.position.longitude.degrees,self.position.elevation.m)
		
		#Create a object of clas Label
		label_text = '%s(%s)\n(ip:%s)'%(self.name,self.id,str(self._ip))
		label =czml.Label(text = label_text,show = True)
		#Defines horizontalOrigin from the Label
		label.horizontalOrigin ='CENTER'
		#Defines verticalOrigin from the Label
		label.verticalOrigin ='DOWN'
		#Defines scale from the Label
		label.scale = 0.5
		#Defines pixelOffset from the Label
		label.pixelOffset = {"cartesian2":[30,20]}
		
		#Create a object of clas Path
		path = czml.Path()
		#Defines show from the Path
		path.show = True
		#path.show = [{"interval":datetime_vector[0].isoformat()+'/'+datetime_vector[-1].isoformat(),"boolean":True}]
		#Defines width from the Path
		path.width = 1
		#Defines resolution from the Path
		path.resolution = 120
		#Create a object of clas Color
		color = czml.Color()
		#Defines rgba from the Color
		color.rgba = [255,255,0,255]
		#Create a object of clas SolidColor
		solidColor = czml.SolidColor()
		#Defines color from the SolidColor
		solidColor.color = color
		#Create a object of clas Material
		material = czml.Material()
		#Defines solidColor from the Material
		material.solidColor= solidColor
		#Defines material from the Path
		path.material = material
		Period = 2*math.pi/self._orbit._TLE.model.no_kozai*60
		#Defines leadTime from the Path
		path.leadTime = Period
		#Defines trailTime from the Path
		path.trailTime = 0
		
		#Create and defines a object of clas Position
		position = self._czml_positions(datetime_vector)
		
		description = czml.Description(self.description())
		
		#Defines billboard from the CZMLPacket
		SAT.billboard = bb
		#Defines label from the CZMLPacket
		SAT.label = label
		#Defines path from the CZMLPacket
		SAT.path = path
		#Defines position from the CZMLPacket
		SAT.position = position
		
		SAT.description = description
		results[index] = SAT
		return SAT
