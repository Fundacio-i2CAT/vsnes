#!/usr/bin/env python3
from skyfield.api import load, wgs84
from datetime import datetime,timedelta,timezone
class Orbit:
	'''Orbit class difine a propagation orbit with a TLE (Two Line Element)'''
	#The TLE property define a class of skyfield that is inicialice with a satellite TLE
	_TLE = None
	
	def __init__(self,sat):
		# Creates a Orbit class object from a TLE
		self._TLE = sat
	def ECEF(self,datetime):
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
	'''
	def time_vector(self,TotalTime,TimeInterval,date_time,UTC = 0):
		if date_time == None:
			date_time = datetime.now(timezone(timedelta(hours=UTC)))
		n_intervals = round(TotalTime*60/TimeInterval)
		intervall = timedelta(minutes = TimeInterval)
		timelist = []
		for i in range(n_intervals):
			timelist.append(date_time + i*intervall)
		return timelist
	def ECEF(self,TotalTime = 1,TimeInterval = 60,esec = None,date_time = None):
		# Return a list of arrays in cartesian coordinates with the current position or in a time diference in seconds with respect to the ToA (Time of Aplicability)
		ECEF = []
		timelist = self.time_vector(TotalTime,TimeInterval,date_time)
		for t in timelist:
			ts = load.timescale().from_datetime(t)
			geocentric = self.TLE.at(ts)
			position = wgs84.geographic_position_of(geocentric)
			ECEF.append(position.itrs_xyz.m)
		return ECEF
	def LLA(self,TotalTime = 1,TimeInterval = 60,esec = None,date_time = None):
		# Return a list of arrays in geographic coordinate system with the current position or in a time diference in seconds with respect to the ToA (Time of Aplicability)
		LLA = []
		timelist = self.time_vector(TotalTime,TimeInterval,date_time)
		for t in timelist:
			ts = load.timescale().from_datetime(t)
			geocentric = self.TLE.at(ts)
			position = wgs84.geographic_position_of(geocentric)
			LLA.append([position.latitude.degrees,position.longitude.degrees,position.elevation.m])
		return LLA
	def ECI(self,TotalTime = 1,TimeInterval = 60,esec = None,date_time = None):
		# Return a list of arrays in geographic coordinate system with the current position or in a time diference in seconds with respect to the ToA (Time of Aplicability)
		ECI = []
		timelist = self.time_vector(TotalTime,TimeInterval,date_time)
		for t in timelist:
			ts = load.timescale().from_datetime(t)
			geocentric = self.TLE.at(ts)
			ECI.append(geocentric.position.m)
		return ECI'''
	def get_position(self,datetime):
		#Return the position in a datetime
		#Load a timescale in the datetime
		t_skyfield = load.timescale().from_datetime(datetime)
		#Calcule the position in ECI cordinates
		geocentric = self._TLE.at(t_skyfield)
		#Recalcule the position in relation of the geoid wgs84
		position = wgs84.geographic_position_of(geocentric)
		return position
