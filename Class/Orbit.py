#!/usr/bin/env python3
class Orbit:
	'''Orbit class difine a propagation orbit with a TLE (Two Line Element)'''
	#The TLE property define a class of skyfield that is inicialice with a satellite TLE
	_TLE = None
	
	def __init__(self,sat):
		# Creates a Orbit class object from a TLE
		self._TLE = sat
