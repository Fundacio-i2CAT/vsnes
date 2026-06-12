#!/usr/bin/env python3
import numpy as np
from skyfield.api import load, wgs84
from Class.Orbit import Orbit

# Shared timescale: creating it is expensive, do it once per process.
ts = load.timescale()

class SGP4(Orbit):
	'''Orbit class define a propagation orbit with a TLE (Two Line Element)'''
	#The TLE property define a class of skyfield that is inicialice with a satellite TLE
	_TLE = None

	def __init__(self,sat):
		# Creates a Orbit class object from a TLE
		Orbit.__init__(self,sat)
	def _ECEF(self,datetime):
		# Return cartesian cordinates in ECEF [x,y,z]
		geocentric = self._TLE.at(ts.from_datetime(datetime))
		position = wgs84.geographic_position_of(geocentric)
		return position.itrs_xyz.m
	def _POS(self,datetime):
		# Return [latitude, longitude, elevation]
		geocentric = self._TLE.at(ts.from_datetime(datetime))
		position = wgs84.geographic_position_of(geocentric)
		return [position.latitude.degrees,position.longitude.degrees,position.elevation.m]
	def _ECI(self,datetime):
		# Return cartesian cordinates in ECI [x,y,z]
		geocentric = self._TLE.at(ts.from_datetime(datetime))
		return geocentric.position.m
	def _vectors(self,datetime_vector):
		# Vectorized propagation: one Skyfield call for the whole timeline
		# instead of one per timestep.
		t = ts.from_datetimes(datetime_vector)
		geocentric = self._TLE.at(t)
		position = wgs84.geographic_position_of(geocentric)
		# geocentric.position.m has shape (3, T) -> transpose to a list of T 3-vectors
		ECI = list(geocentric.position.m.T)
		ECEF = list(position.itrs_xyz.m.T)
		POS = list(np.column_stack((position.latitude.degrees,
									position.longitude.degrees,
									position.elevation.m)))
		return ECI,ECEF,POS
