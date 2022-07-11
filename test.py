import unittest
from Class.Scenario import scenario
from Class.Time_parameters import time_parameters
from skyfield.api import load
import numpy as np
import sys, os
import toml
date_time = '2022-04-05 07:31:31+00:00'
class HiddenPrints:

    def __enter__(self):

        self._original_stdout = sys.stdout

        sys.stdout = open(os.devnull, 'w')


    def __exit__(self, exc_type, exc_val, exc_tb):

        sys.stdout.close()

        sys.stdout = self._original_stdout

class ScenarioTestCAse(unittest.TestCase):
	def setUp(self):
		with HiddenPrints():
			#Open file
			fo = open('test.toml', "r")
			self.TOMLfile = toml.load(fo, _dict=dict)
			self.scenarioTest = scenario(self.TOMLfile)
			# Close opened file
			fo.close()
	def test_AddSatellite(self):
		with HiddenPrints():
			SpaceSegment = self.TOMLfile['SpaceSegment']
			for SatelliteSistem in SpaceSegment['SatelliteSistem']:
				config_file = SatelliteSistem['TLE']
				satellites = load.tle_file(config_file)
				for sat in satellites:
					self.scenarioTest.AddSatellite(sat,SatelliteSistem)
			self.assertEqual(self.scenarioTest.get_number_of_nodes(),2)	
	def test_AddGroundStation(self):
		with HiddenPrints():
			self.scenarioTest.AddGroundStation(self.TOMLfile['GroundSegment']['GroundSistem'][0])
			self.assertEqual(self.scenarioTest.get_number_of_nodes(),2)		
	def test_step(self):
		self.assertFalse(self.scenarioTest.step())
		self.assertEqual(self.scenarioTest._time_parameters._marker,1)
		self.assertTrue(self.scenarioTest.step())
		self.assertEqual(self.scenarioTest._time_parameters._marker,0)
		self.assertFalse(self.scenarioTest.step())
		self.assertEqual(self.scenarioTest._time_parameters._marker,1)
	def test_reset(self):
		self.scenarioTest.step()
		self.scenarioTest.reset()
		self.assertEqual(self.scenarioTest._time_parameters._marker,0)
	def test_write_bash(self):
		self.scenarioTest.write_bash()
	def test_get_speed(self):
		self.assertEqual(self.scenarioTest.get_speed(),60)
	def test_get_number_of_nodes(self):
		self.assertEqual(self.scenarioTest.get_number_of_nodes(),2)
	def test_write_czml(self):
		with HiddenPrints():
			self.scenarioTest.write_czml()
class ChannelTestCAse(unittest.TestCase):
	def setUp(self):
		with HiddenPrints():
			#Open file
			fo = open('test.toml', "r")
			self.TOML = toml.load(fo, _dict=dict)
			self.scenarioTest = scenario(self.TOML)
			# Close opened file
			fo.close()
	def test_delete(self):
		self.scenarioTest._channel.delete()
		self.assertEqual(len(self.scenarioTest._channel._dalay_matrix),0)
		self.assertFalse(self.scenarioTest._channel.get_exist())
	def test_get_channel(self):
		self.assertEqual(self.scenarioTest._channel.get_channel(1,1),0)
		self.assertEqual(self.scenarioTest._channel.get_channel(0,1),-1)
		self.assertEqual(self.scenarioTest._channel.get_channel(0),[0,-1])
class TimeParametersTestCAse(unittest.TestCase):
	def setUp(self):
		with HiddenPrints():
			#Open file
			fo = open('test.toml', "r")
			TOMLfile = toml.load(fo, _dict=dict)
			self.Time_test = time_parameters(TOMLfile['Time'])
			# Close opened file
			fo.close()
	def test_get_speed(self):
		self.assertEqual(self.Time_test.get_speed(True),5)
		self.assertEqual(self.Time_test.get_speed(False),60)
	def test_get_datetimes(self):
		datetime_list = self.Time_test.get_datetimes()
		self.assertEqual(len(datetime_list),2)
		initial_datetime = self.Time_test.get_initial_date_time()
		end_datetime = self.Time_test.get_end_date_time()
		self.assertEqual(datetime_list[0],initial_datetime)
		self.assertEqual(datetime_list[-1],end_datetime)
		self.Time_test.step()
		date_time = self.Time_test.get_date_time()
		self.assertEqual(datetime_list[1],date_time)
		self.Time_test.reset()
		date_time = self.Time_test.get_date_time()
		self.assertEqual(initial_datetime,date_time)
	def test_get_TimeInterval(self):
		self.assertEqual(self.Time_test.get_TimeInterval(),30)
if __name__ == '__main__':
    unittest.main()
