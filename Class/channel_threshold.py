#!/usr/bin/env python3

class threshold:
	def __init__(self,threshold):
		self.id = threshold['id']
		self.inter_satellite = threshold['inter-satellite_threshold']
		self.Ground2Satellite = threshold['Ground2Satellite_threshold']
	def get_id (self):
		return self.id
	def get_Satellite2Satellite (self):
		return self.inter_satellite
	def get_Ground2Satellite (self):
		return self.Ground2Satellite
