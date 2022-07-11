#!/usr/bin/env python3
from skyfield.api import load
from datetime import datetime,timedelta
ts = load.timescale()

class time_parameters:
	'''The time_parameters class define how the instant of time change during the emulation'''
	#The TimeInterval is a timedelta which inticate the minute elapse between every step of time
	_TimeInterval = None	#[min]
	
	#The contact_speed property defines the relation of the emulation time with the real one when exit contact at least between two nodes
	_contact_speed = None	
	
	#The non_contact_speed property defines the relation of the emulation time with the real one when  not exit contact between any node	
	_non_contact_speed = None
	
	#The datetime_vector property defines a list of datetime objects. That objects define all the instants of the emulation.
	_datetime_vector= None
	
	#The marker property indicates in that position of the datetime list is the emulation
	_marker = None 
	
	def __init__(self,TOMLTime):
		#Save in variable the information of TOML file related with time 
		TimeInterval = TOMLTime['TimeInterval']
		contact_speed = TOMLTime['Contact_speed']
		non_contact_speed = TOMLTime['Non_contact_speed']
		start_date_time = TOMLTime['start_datetime']
		end_date_time = TOMLTime['end_datetime']
		#Check if the value is correct. TimeInterval have to be greater than 0
		if float(TimeInterval) > 0: 
			self._TimeInterval = timedelta(minutes=float(TimeInterval))
		else:
			#When the value is not possible defines a default value
			print ('ERROR: invalid parameter, TimeInterval cannot be negative or equal to 0')
			self._TimeInterval = timedelta(minutes=1)
		#Check if the value is correct. contact_speed have to be greater than 0
		if float(contact_speed) > 0:
			self._contact_speed = float(contact_speed)
		else: 
			#When the value is not possible defines a default value
			print ('ERROR: invalid parameter, speed cannot be negative or equal to 0')
			self._contact_speed = 1
		#Check if the value is correct. non_contact_speed have to be greater than 0
		if float(non_contact_speed) > 0:
			self._non_contact_speed = float(non_contact_speed)
		else: 
			#When the value is not possible defines a default value
			print ('ERROR: invalid parameter, speed cannot be negative or equal to 0')
			self._non_contact_speed = 1
		
		date_time = start_date_time+'+00:00'
		date_time = datetime.fromisoformat(date_time)
		initial_date_time = date_time
		str_end_date_time = end_date_time+'+00:00'
		end_date_time = datetime.fromisoformat(str_end_date_time)
		if end_date_time <= initial_date_time:
			date_time =end_date_time
			end_date_time = initial_date_time
		self._datetime_vector = []
		while end_date_time > date_time:
			self._datetime_vector.append(date_time)
			date_time += self._TimeInterval
		self._marker = 0
		self.RealTime = False
	def get_speed (self,channel = True):
		#Return a speed. If channel is True, it returns contact speed if not returns non contact speed
		if channel:
			return self._contact_speed
		else:
			return self._non_contact_speed
	def get_datetimes(self):
		#Return datetime_vector
		return self._datetime_vector
	def get_initial_date_time(self):
		#Return the first position of datetime_vector
		return self._datetime_vector[0]
	def get_date_time(self):
		#Return the position of datetime_vector which the emulation is
		return self._datetime_vector[self._marker]
	def get_end_date_time(self):
		#Return the last position of datetime_vector
		return self._datetime_vector[-1]
	def get_TimeInterval(self):
		#Return TimeInterval in seconds
		return self._TimeInterval.seconds
	def get_interval(self):
		#Return a string with the initial datetime and the last
		return '%s/%s'%(self._datetime_vector[0].isoformat(),self._datetime_vector[-1].isoformat())
	def reset(self):
		# Put the marker in 0
		self._marker = 0
	def step(self):
		# Add one to the marker, If these is greater than the lenght of datetime_vector return True because the emulation is over
		if not(self.RealTime):
			self._marker +=1
			if self._marker >= len(self._datetime_vector):
				return True
			else:
				return False
		else:
			date_time = datetime.now(timezone(timedelta(hours=0)))
			return False
