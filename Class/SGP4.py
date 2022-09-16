#!/usr/bin/env python3
from skyfield.api import load, wgs84
from datetime import datetime,timedelta,timezone
from Class.Orbit import Orbit
class SGP4(Orbit):
	'''Orbit class difine a propagation orbit with a TLE (Two Line Element)'''
	#The TLE property define a class of skyfield that is inicialice with a satellite TLE
	_TLE = None
	
	def __init__(self,sat):
		# Creates a Orbit class object from a TLE
		Orbit.__init__(self,sat)
	def _ECEF(self,datetime):
		# Return cartesian cordinates in ECEF [x,y,z]
		#Load a timescale in the datetime
		ts = load.timescale().from_datetime(datetime)
		#Calcule the position in ECI cordinates
		geocentric = self._TLE.at(ts)
		#Recalcule the position in relation of the geoid wgs84
		position = wgs84.geographic_position_of(geocentric)
		return position.itrs_xyz.m
	def _ECI(self,datetime):
		# Return cartesian cordinates in ECI [x,y,z]
		#Load a timescale in the datetime
		ts = load.timescale().from_datetime(datetime)
		#Calcule the position in ECI cordinates
		geocentric = self._TLE.at(ts)
		return geocentric.position.m
	def _vectors(self,datetime_vector):	
		
		# Return cartesian cordinates in ECI [x,y,z]
		#Load a timescale in the datetime
		ECI = []
		ECEF = []
		for datetime in datetime_vector:
			ts = load.timescale().from_datetime(datetime)
			#Calcule the position in ECI cordinates
			geocentric = self._TLE.at(ts)
			ECI.append(geocentric.position.m)
			position = wgs84.geographic_position_of(geocentric)
			ECEF.append(position.itrs_xyz.m)
		return ECI,ECEF
