import unittest
from Class.Functions import *
from Class.Scenario import scenario
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
class Test(unittest.TestCase):
	def setUp(self):
		with HiddenPrints():
			#Open file
			fo = open('test.toml', "r")
			TOML = toml.load(fo, _dict=dict)
			self.scenarioTest = scenario(TOML,False)
			# Close opened file
			fo.close()
		
	def test_ECEF2LLA(self):
		LLA1 = np.round(self.scenarioTest.node_list[0].get_LLA(),9)
		LLA2 = np.round(ECEF2LLA(self.scenarioTest.node_list[0].get_ECEF()),9)
		self.assertEqual(LLA1[0],LLA2[0])
		self.assertEqual(LLA1[1],LLA2[1])
		self.assertEqual(LLA1[2],LLA2[2])
		
		LLA1 = np.round(self.scenarioTest.node_list[1].LLA,9)
		LLA2 = np.round(ECEF2LLA(self.scenarioTest.node_list[1].ECEF),9)
		self.assertEqual(LLA1[0],LLA2[0])
		self.assertEqual(LLA1[1],LLA2[1])
		self.assertEqual(round(LLA1[2]),round(LLA2[2]))
	def test_LLA2ECEF(self):
		ECEF1 = np.round(self.scenarioTest.node_list[0].get_ECEF(esec = 0),8)
		ECEF2 = np.round(LLA2ECEF(self.scenarioTest.node_list[0].get_LLA(esec = 0)),8)
		self.assertEqual(ECEF1[0],ECEF2[0])
		self.assertEqual(ECEF1[1],ECEF2[1])
		self.assertEqual(ECEF1[2],ECEF2[2])
		ECEF1 = np.round(self.scenarioTest.node_list[1].ECEF,9)
		ECEF2 = np.round(LLA2ECEF(self.scenarioTest.node_list[1].LLA),9)
		self.assertEqual(ECEF1[0],ECEF2[0])
		self.assertEqual(ECEF1[1],ECEF2[1])
		self.assertEqual(ECEF1[2],ECEF2[2])
	def test_ECEF2NED(self):
		pseudoDistance = self.scenarioTest.node_list[0].get_ECEF(esec = 0)-self.scenarioTest.node_list[1].ECEF
		NED = ECEF2NED(pseudoDistance,self.scenarioTest.node_list[1].LLA)
		self.assertEqual(NED[0],405755.22698970186)
		self.assertEqual(NED[1],-6975330.3692563865)
		self.assertEqual(NED[2],6765020.245979368)
	def test_NED2AzimuthElevationDistance(self):
		pseudoDistance = self.scenarioTest.node_list[0].get_ECEF(esec = 0)-self.scenarioTest.node_list[1].ECEF
		NED = ECEF2NED(pseudoDistance,self.scenarioTest.node_list[1].LLA)
		alpha,beta,d = NED2AzimuthElevationDistance(NED)
		self.assertEqual(alpha,-86.67085399548415)
		self.assertEqual(beta,-44.07473501529871)
		self.assertEqual(d,9725501.015012575)
	def test_GroundBase2Satellite(self):
		LoS, delay = GroundBase2Satellite(self.scenarioTest.node_list[0].get_ECEF(esec = 0),self.scenarioTest.node_list[1].ECEF,self.scenarioTest.node_list[1].LLA,0,1e7)
		self.assertFalse(LoS)
		self.assertEqual(delay,-1)
		ECEF_SAT = np.array([4822180,168394,4166360])
		LoS, delay = GroundBase2Satellite(ECEF_SAT,self.scenarioTest.node_list[1].ECEF,self.scenarioTest.node_list[1].LLA,0,1e7)
		self.assertTrue(LoS)
		self.assertEqual(delay,0.14817670804304725)
	def test_Satellite2Satellite(self):
		ECEF1 = np.array([1e7,1e7,0])
		ECEF2 = np.array([-2e7,-1e7,1e6])
		LoS, delay = Satellite2Satellite(ECEF1,ECEF2,1e7)
		self.assertFalse(LoS)
		self.assertEqual(delay,-1)
		ECEF1 = np.array([1e7,1e7,0])
		ECEF2 = np.array([2e7,3e7,1e6])
		LoS, delay = Satellite2Satellite(ECEF1,ECEF2,1e7)
		self.assertFalse(LoS)
		self.assertEqual(delay,-1)
		ECEF1 = np.array([1e7,1e7,0])
		ECEF2 = np.array([0.5e7,1.5e7,0.25e6])
		LoS, delay = Satellite2Satellite(ECEF1,ECEF2,1e7)
		self.assertTrue(LoS)
		self.assertEqual(delay,23.58495283014151)
	def test_matrix_scenario(self):
		for n in range(0,self.scenarioTest.nNodes):
			for j in range(n,self.scenarioTest.nNodes):
				if n == j:
					self.assertEqual(self.scenarioTest.channel.get_channel(n,j),0)
				else:
					self.assertEqual(self.scenarioTest.channel.get_channel(n,j),self.scenarioTest.channel.get_channel(j,n))
	def test_update_matrix(self):
		dt = datetime.fromisoformat(date_time)
		self.scenarioTest.update(dt)
		vectorTest = [0, -1, -1, -1, -1, -1, -1, -1]
		self.assertEqual(self.scenarioTest.channel.get_channel(0),vectorTest)
		vectorTest = [-1, 8.793499320359917, 2.198849545424264, 3.761151311479712, 13.68470909188887, 12.127821074326253, 0, 11.761640148776557]
		self.assertEqual(self.scenarioTest.channel.get_channel(6),vectorTest)
		matrix1 =  self.scenarioTest.channel.get_channel()
		self.scenarioTest.update(date_time = dt)
		matrix2 =  self.scenarioTest.channel.get_channel()
		self.assertEqual(matrix1,matrix2)
		self.scenarioTest.set_date_time('2022-04-13 07:31:31')
		matrix1 =  self.scenarioTest.channel.get_channel()
		self.scenarioTest.update()
		matrix2 =  self.scenarioTest.channel.get_channel()
		self.assertEqual(matrix1,matrix2)
	'''def test_Exist_Node(self):
		with HiddenPrints():
			self.assertTrue(Exist_Node(self.scenarioTest.node_list,self.scenarioTest.node_list[1],self.scenarioTest.nNodes))
			self.assertTrue(Exist_Node(self.scenarioTest.node_list,self.scenarioTest.node_list[3],self.scenarioTest.nNodes))
			nActual = self.scenarioTest.nNodes
			self.scenarioTest.AddNode(line0_sat,line1_sat,line2_sat)
			self.assertEqual(self.scenarioTest.nNodes,nActual)
			self.scenarioTest.AddNode(line0_GS,line1_GS,line2_GS)
			self.assertEqual(self.scenarioTest.nNodes,nActual)'''
	def test_set_methods(self):
		self.assertTrue(self.scenarioTest.set_TotalTime(1))
		self.assertTrue(self.scenarioTest.set_TimeInterval(1))
		self.assertTrue(self.scenarioTest.set_date_time('2022-03-08 20:31:00'))
		self.assertTrue(self.scenarioTest.set_speed(1))
		self.assertEqual(self.scenarioTest.time_parameters.get_TotalTime(),1)
		self.assertEqual(self.scenarioTest.time_parameters.get_TimeInterval(),1)
		self.assertEqual(self.scenarioTest.time_parameters.get_date_time(),datetime.fromisoformat('2022-03-08 20:31:00'))
		self.assertEqual(self.scenarioTest.time_parameters.get_initial_date_time(),datetime.fromisoformat('2022-03-08 20:31:00'))
		self.assertEqual(self.scenarioTest.time_parameters.get_speed(),1)
	def test_step(self):
		self.scenarioTest.set_date_time('2022-03-08 20:31:00')
		self.scenarioTest.set_TotalTime(1)
		matrix = self.scenarioTest.channel.get_channel()
		n = 0
		while not(self.scenarioTest.step(False)):n+=1
		self.assertEqual(n,60)
		self.assertFalse(self.scenarioTest.channel.get_channel() == matrix)
	def test_reset(self):
		self.scenarioTest.set_date_time('2022-03-08 20:31:00')
		matrix1 = self.scenarioTest.channel.get_channel()
		self.scenarioTest.step(False)
		self.scenarioTest.reset()
		matrix2 = self.scenarioTest.channel.get_channel()		
		self.assertEqual(matrix1,matrix2)
		self.assertEqual(self.scenarioTest.time_parameters.get_date_time(),self.scenarioTest.time_parameters.get_initial_date_time())
		
if __name__ == '__main__':
    unittest.main()
