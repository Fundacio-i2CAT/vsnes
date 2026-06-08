#!/usr/bin/env python3
from Class.Orbit import Orbit
from sgp4 import exporter
import julian
from datetime import datetime,timedelta
import math
import numpy as np
from astropy.time import Time

#GLOBAL CONSTANTS
G = 6.67384e-11;            			# Gravitational constant [m3 kg-1 s-2]
M = 5.972e+24;              			# Earth mass [kg]
dOmegaEarth = 7.2921151467e-5			# Angular speed of Earth rotation [rad/s]
a_Earth = 6378137 				# Earth major semi axis [m]
e_2 = 0.00669437999014				# Square Earth eccentricity
c = 3e8					# Speed of light [m/s]
b = math.sqrt(a_Earth**2-(e_2*a_Earth**2))	# Earth menor semi axis [m]
MJ2022 = 59580.0 				# MJD on 1/1/2022 at 00:00 UTC (see http://leapsecond.com/java/cal.htm)


class TwoBody(Orbit):
	def __init__(self,sat):
		# Creates a Orbit class object from a TLE
		Orbit.__init__(self,sat)
		line1, line2 = exporter.export_tle(self._TLE.model)
		self.ToA,i0,Omega0,e,w,M0,n,self.ToAyear = self._Read_TLE(line1, line2)
		self.GAST = self._gast(self.ToA,self.ToAyear)
		self.a,self.i0,self.e,self.Omega, self.d_Omega,self.w, self.M0, self.n = self._Keplerian_parameters(i0,Omega0,e,w,M0,n,self.GAST)
		
	def _Read_TLE(self,L1 , L2):
		#Returns the parameters of interest of the TLE			
		vL1 = L1.split()
		# Time of Applicability [days]
		ToAyear = int(vL1[3][:2])
		ToA = float(vL1[3][2:])
		vL2 = L2.split()
		
		# Orbit inclination [degrees]
		i0 = float(vL2[2])
		# Right ascension of the ascending node at ToA [degrees]
		Omega0 = float(vL2[3])
		# Orbit eccentricity times 10^7
		e = float(vL2[4])
		# Argument of the perigee at ToA [degrees]
		w = float(vL2[5])
		# Mean Anomaly at ToA [degrees]
		M0 = float(vL2[6])
		# Mean motion (satellite angular speed of rotation) in [Revolutions/day]
		n = float(vL2[7])
		return ToA,i0,Omega0,e,w,M0,n,ToAyear
	def _gast(self,ToA,ToAyear):
		JYear = julian.to_jd(datetime.fromisoformat('20%d-01-01'%(ToAyear)), fmt='jd')	# JD on 1/1/year at 00:00 UTC
		JToA = JYear + ToA - 1							# ToA in JD
		JYear = julian.to_jd(datetime.fromisoformat('2022-01-01'), fmt='jd')
		
		# Greenwich Mean Sidereal Time (GMST) is the hour angle of the average position of the vernal equinox,
		# neglecting short term motions of the equinox due to nutation. GAST is GMST corrected for
		# the shift in the position of the vernal equinox due to nutation.
		# GAST at a given epoch is the RA of the Greenwich meridian at that epoch (usually in time units).
		
		#Find GAST in degrees at ToA
		J2000 = 2451545.0					# epoch is 1/1/2000 at 12:00 UTC
		midnight = round(JToA) - 0.5				# midnight of JToA
		days_since_midnight = JToA - midnight
		hours_since_midnight = days_since_midnight * 24
		days_since_epoch = JToA - J2000
		centuries_since_epoch = days_since_epoch / 36525
		whole_days_since_epoch = midnight - J2000
		GAST = 6.697374558 + 0.06570982441908 * whole_days_since_epoch + 1.00273790935 * hours_since_midnight + 0.000026 * centuries_since_epoch**2  # GAST in hours from ?
		GASTh = GAST - 24 * math.floor(GAST/24) 		# GAST in hours at ToA
		GASTdeg = 15 * 1.0027855 * GASTh			# GAST in degrees at ToA (approx. 361º/24h)
		GAST=GASTdeg*math.pi/180				# GAST in radians
		return GAST
	
	def _Keplerian_parameters(self,i0,Omega0,e,w,M0,n,GAST):	#Normalizes the Keplerian parameters for later use.
		# Return the Keplerian parameters in a format that can be operated on from the data extracted from the TLE.
		i0=i0*math.pi/180; 				# Orbit inclination [rad]
		Omega0=Omega0*math.pi/180			# Right ascention [rad]
		e = e / (10**7)				# Orbit eccentricity
		w=w*math.pi/180;				# Argument of the perigee at ToA [rad]
		M0=M0*math.pi/180 				# Mean Anomaly at ToA [rad]
		n=n*2*math.pi/(24*3600)			# Mean motion [rad/s]
		
		a=(G*M/(n**2))**(1/3)  		# Orbit major semi axis [m]
		Omega=Omega0-GAST			# Longitude of the ascending node at the ToA
		d_Omega=0				# Rate of change of the right ascension [rad/s]
		return a,i0,e,Omega, d_Omega,w, M0, n

	def _Kepler2ECEF(self,date_time):
		#Return the ECEF position of a satellite 
		dt = self._compute_esec(date_time)
		Mk = self.M0 + self.n * dt		# Mean anomaly computation
		Ek = []
		i = 1
		Ek.append(Mk)
		Ek.append(Mk + self.e * math.sin(Ek[i-1]))
		#Eccentric anomaly computation
		while abs(Ek[i]-Ek[i-1]) >= (1e-8):
			i += 1
			Ek.append(Mk + self.e * math.sin(Ek[i-1]))
		Sin_v = (math.sqrt(1-self.e**2)*math.sin(Ek[i]))/(1-self.e*math.cos(Ek[i]))	
		Cos_v = (math.cos(Ek[i])-self.e)/(1-self.e*math.cos(Ek[i]))
		v = math.atan2(Sin_v,Cos_v)	# True Anomaly
		u = v + self.w 			# Argument of latitude
		r_k = self.a*(1-self.e*math.cos(Ek[i]))	# Orbit radius (current distance to Earth center)
		Omegak = self.Omega+self.d_Omega * dt-dOmegaEarth*dt	# Current longitude of the ascending node
		x_p = r_k*math.cos(u)		# x coordinate within the orbital plane
		y_p = r_k*math.sin(u)		# y coordinate within the orbital plane
		
		x = x_p * math.cos(Omegak)-y_p*math.cos(self.i0)*math.sin(Omegak)	# ECEF x-coordinate [m]
		y = x_p * math.sin(Omegak)+y_p*math.cos(self.i0)*math.cos(Omegak)	# ECEF y-coordinate [m]
		z = y_p*math.sin(self.i0)						# ECEF z-coordinate [m]
		
		ECEF = []
		ECEF = np.array([x,y,z])
		return ECEF
	def _compute_esec (self,date_time):
		# Computes elapsed time from ToA [s] and GAST [deg] at ToA
		# ToA must be given in days of current year
		dt = date_time	
		JD = julian.to_jd(dt, fmt='jd')	# Julian Date in UTC
		# Compute current time in secs. from ToA
		JYear = julian.to_jd(datetime.fromisoformat('20%d-01-01'%(self.ToAyear)), fmt='jd')	# JD on 1/1/year at 00:00 UTC
		JToA = JYear + self.ToA - 1							# ToA in JD
		esec = 86400 * (JD - JToA)  		# time elapsed since the ToA in secs.
		return esec
	
	def _ECEF2ECI(self,ECEF,date_time):
		#Return the position in ECI from the position in ECEF
		#		(cos(GAST)	-sin(GAST)	0)
		# 	P_ECI=	(sin(GAST)	cos(GAST)	0) P_ECEF
		#		(0		0		1)
		
		gst = Time(date_time).sidereal_time("apparent", "greenwich").radian
		x_ECEF = ECEF[0]
		y_ECEF = ECEF[1]
		GAST = gst
		x = math.cos(GAST) * x_ECEF - math.sin(GAST) * y_ECEF
		y = math.sin(GAST)* x_ECEF + math.cos(GAST) * y_ECEF
		z = ECEF[2]
		ECI = np.array([x,y,z])
		return ECI
	def _vectors(self,datetime_vector):
		# Return cartesian cordinates in ECI [x,y,z]
		#Load a timescale in the datetime
		ECI = []
		ECEF = []
		POS = []
		for datetime in datetime_vector:
			ECEF_1 = self._Kepler2ECEF(datetime)
			ECEF.append(ECEF_1)
			ECI_1 = self._ECEF2ECI(ECEF_1,datetime)
			ECI.append(ECI_1)
		return ECI,ECEF,POS
	def _ECI(self,datetime):
		# Return cartesian cordinates in ECI [x,y,z]
		#Load a timescale in the datetime
		ECEF_1 = self._Kepler2ECEF(datetime)
		ECI_1 = self._ECEF2ECI(ECEF_1,datetime)
		return ECI_1
