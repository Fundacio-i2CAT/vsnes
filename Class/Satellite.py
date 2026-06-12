#!/usr/bin/env python3
from Class.SGP4 import SGP4
from Class.TwoBody import TwoBody
from Class.Node import Node
from czml import czml
import csv
import math
from sgp4 import exporter
from datetime import datetime,timedelta
import json
import logging

class Satellite(Node):
	'''Specific node type which is particularity  of has an orbit.'''
	#Each satellite have a unique Norad ID. The ID property save this code 
	_id = None
	
	#The Orbit property defines a position of the node in relation of datetime.
	_orbit = None
	
	@property
	def id(self):
		return self._id
	
	def __init__(self,sat,constallation,network,mask,nNodes,datetime_vector):
		# Creates a satellite class object from three configuration lines
		logging.info(f"Initializing Satellite '{sat.name}' from TLE and configuration")
		self._id = sat.model.satnum
		
		try:
			if constallation['propagator'].lower() == 'twobody':
				self._orbit = TwoBody(sat)
				logging.info(f"Satellite '{sat.name}' using TwoBody propagator")
			else:
				self._orbit = SGP4(sat)
				logging.info(f"Satellite '{sat.name}' using SGP4 propagator")
		except KeyError:
			error_msg = f"Missing 'propagator' configuration for satellite {sat.name}"
			logging.error(error_msg)
			raise KeyError(error_msg)
			
		Node.__init__(self,name = sat.name, Node = constallation,network = network,mask = mask,nNodes = nNodes)
		self._ECI,self._ECEF,self._POS = self._orbit._vectors(datetime_vector)

		# _POS rows may be numpy arrays (vectorized propagation) — convert for JSON
		json_data = {'orbit': [[float(v) for v in p] for p in self._POS]}
		position_file = f'Positions/{self.name}-total.json'
		try:
			with open(position_file,'w') as file:
				json.dump(json_data, file)
			logging.info(f"Satellite position data written to {position_file}")
		except Exception as e:
			logging.error(f"Failed to write position file {position_file}: {e}")
	
		logging.info(f"Satellite '{sat.name}' initialized successfully")
		
	def get_TLE (self):
		#Return the skyfield object TLE
		return self._orbit._TLE
	def get_ECI(self,marker):
		return self._ECI[marker]
	def get_POS(self,marker):
		return self._POS[marker]
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
		for i in range(0,len(datetime_vector)):
			#Loop through a vector of datetimes
			#Append datetime
			cartesian.append(datetime_vector[i])
			#Calcule the ECI position in the datetime
			ECI = self._ECI[i]
			#Append x-axis
			cartesian.append(ECI[0])
			#Append y-axis
			cartesian.append(ECI[1])
			#Append z-axis
			cartesian.append(ECI[2])
		Period = 2*math.pi/self._orbit._TLE.model.no_kozai
		post_datetime = datetime_vector[-1]+timedelta(minutes=Period+15)
		date_time = datetime_vector[-1]
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
	def czml_node(self,datetime_vector):
		#Return object of type CZMLPacket
		#Create a object of clas CZMLPacket
		SAT = czml.CZMLPacket(id=self.name,name=self.name)
		
		#Create a object of clas Billboard
		bb = czml.Billboard(scale=0.5, show=True)
		#Defines image from the Billboard
		bb.image = "data:image/png;base64,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"
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
		color.rgba = [0,255,255,128]
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
		return SAT
