#!/usr/bin/env python3
from skyfield.api import load
from datetime import datetime,timedelta
import logging

ts = load.timescale()

class time_parameters:
	'''The time_parameters class define how each instant of time change during the emulation'''
	#The TimeInterval is a timedelta which inticate the minute elapse between every step of time
	_TimeInterval = None	#[min]
	
	#The contact_speed property defines the relation of emulation time with the real one when exist contact at least between two nodes
	_contact_speed = None	
	
	#The non_contact_speed property defines the relation of emulation time with the real one when not exist contact between any node	
	_non_contact_speed = None
	
	#The datetime_vector property defines a list of datetime objects. That objects define all the instants of the emulation.
	_datetime_vector= None
	
	#The marker property indicates in that position of datetime list is the emulation
	_marker = None 
	
	def __init__(self,TOMLTime):
		#Save in variable the information of TOML file related with time 
		logging.info("Initializing time parameters from TOML configuration")
		
		# Get TimeInterval with proper error handling
		try:
			TimeInterval = float(TOMLTime['TimeInterval'])
			if TimeInterval <= 0:
				raise ValueError("TimeInterval must be greater than 0")
			self._TimeInterval = timedelta(minutes=float(TimeInterval))
			logging.info(f"Time interval set to {TimeInterval} minutes")
		except KeyError:
			error_msg = "Missing 'TimeInterval' configuration in TOML"
			logging.error(error_msg)
			raise KeyError(error_msg)
		except ValueError as e:
			error_msg = f"Invalid TimeInterval value: {e}. Using default of 1 minute"
			logging.error(error_msg)
			self._TimeInterval = timedelta(minutes=1)
		
		# Get contact_speed with proper error handling
		try:
			contact_speed = float(TOMLTime['Contact_speed'])
			if contact_speed <= 0:
				raise ValueError("Contact_speed must be greater than 0")
			self._contact_speed = float(contact_speed)
			logging.info(f"Contact speed set to {contact_speed}x")
		except KeyError:
			error_msg = "Missing 'Contact_speed' configuration in TOML"
			logging.error(error_msg)
			raise KeyError(error_msg)
		except ValueError as e:
			error_msg = f"Invalid Contact_speed value: {e}. Using default of 1x"
			logging.error(error_msg)
			self._contact_speed = 1
		
		# Get non_contact_speed with proper error handling
		try:
			non_contact_speed = float(TOMLTime['Non_contact_speed'])
			if non_contact_speed <= 0:
				raise ValueError("Non_contact_speed must be greater than 0")
			self._non_contact_speed = float(non_contact_speed)
			logging.info(f"Non-contact speed set to {non_contact_speed}x")
		except KeyError:
			error_msg = "Missing 'Non_contact_speed' configuration in TOML"
			logging.error(error_msg)
			raise KeyError(error_msg)
		except ValueError as e:
			error_msg = f"Invalid Non_contact_speed value: {e}. Using default of 1x"
			logging.error(error_msg)
			self._non_contact_speed = 1
		
		# Get start_datetime with proper error handling
		try:
			start_date_time = TOMLTime['start_datetime']
			if len(start_date_time) <= 11:
				start_date_time += ' 00:00:00'
			start_date_time = start_date_time + '+00:00'
			start_date_time = datetime.fromisoformat(start_date_time)
			logging.info(f"Start datetime set to {start_date_time}")
		except KeyError:
			error_msg = "Missing 'start_datetime' configuration in TOML"
			logging.error(error_msg)
			raise KeyError(error_msg)
		except ValueError as e:
			error_msg = f"Invalid start_datetime format: {e}"
			logging.error(error_msg)
			raise ValueError(error_msg)
		
		# Get end_datetime with proper error handling
		try:
			end_date_time = TOMLTime['end_datetime']
			if len(end_date_time) <= 11:
				end_date_time += ' 00:00:00'
			end_date_time = end_date_time + '+00:00'
			end_date_time = datetime.fromisoformat(end_date_time)
			logging.info(f"End datetime set to {end_date_time}")
		except KeyError:
			error_msg = "Missing 'end_datetime' configuration in TOML"
			logging.error(error_msg)
			raise KeyError(error_msg)
		except ValueError as e:
			error_msg = f"Invalid end_datetime format: {e}"
			logging.error(error_msg)
			raise ValueError(error_msg)
		
		# Validate date range
		if end_date_time <= start_date_time:
			logging.warning("End datetime is before or equal to start datetime, swapping values")
			date_time = end_date_time
			end_date_time = start_date_time
			start_date_time = date_time
		
		# Generate datetime vector
		self._datetime_vector = []
		current_time = start_date_time
		while end_date_time > current_time:
			self._datetime_vector.append(current_time)
			current_time += self._TimeInterval
		self._marker = 0
		
		logging.info(f"Time parameters initialized with {len(self._datetime_vector)} time steps")
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
		self._marker +=1
		if self._marker >= len(self._datetime_vector):
			return True
		else:
			return False
