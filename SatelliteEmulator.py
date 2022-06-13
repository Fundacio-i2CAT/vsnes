from Class.Scenario import scenario
from datetime import datetime,timedelta
import webbrowser

import threading
import time
import subprocess
import toml
import sys
from collections import deque
stop_threads = False
def run(Scenario,EMU,CESIUM):
	global stop_threads
	time.sleep(1)
	webbrowser.open_new_tab('http://localhost:8081/')
	n_connections = int(1+(Scenario.get_number_of_nodes()-1)*Scenario.get_number_of_nodes()/2)
	queue = deque([], n_connections)
	String = Scenario._time_parameters.get_date_time().strftime("%m/%d/%Y, %H:%M:%S")
	for _ in range(len(queue)):
		sys.stdout.write("\x1b[1A\x1b[2K") # move up cursor and delete whole line
	queue.append(String)
	for i in range(len(queue)):
		sys.stdout.write(queue[i] + "\n") # reprint the lines
	for n in range(Scenario.get_number_of_nodes()):
		for j in range(n+1,Scenario.get_number_of_nodes()):
			String =  '-Delay %s -> %s:	 %fms'%(Scenario._node_list[n].name,Scenario._node_list[j].name,Scenario._channel.get_channel(n,j))
			for _ in range(len(queue)):
				sys.stdout.write("\x1b[1A\x1b[2K") # move up cursor and delete whole line
			queue.append(String)
			for i in range(len(queue)):
				sys.stdout.write(queue[i] + "\n") # reprint the linesprint (String)
	time.sleep(Scenario._time_parameters.get_TimeInterval()/Scenario.get_speed())
	while True:
		if stop_threads:
			break
		if Scenario.step(EMU,CESIUM):
			print('The emulation is over: press enter to shutdown')
			break
			
		String = Scenario._time_parameters.get_date_time().strftime("%m/%d/%Y, %H:%M:%S")
		for _ in range(len(queue)):
			sys.stdout.write("\x1b[1A\x1b[2K") # move up cursor and delete whole line
		queue.append(String)
		for i in range(len(queue)):
			sys.stdout.write(queue[i] + "\n") # reprint the lines
		for n in range(Scenario.get_number_of_nodes()):
			for j in range(n+1,Scenario.get_number_of_nodes()):
				String =  '-Delay %s -> %s:	 %fms'%(Scenario._node_list[n].name,Scenario._node_list[j].name,Scenario._channel.get_channel(n,j))
				for _ in range(len(queue)):
					sys.stdout.write("\x1b[1A\x1b[2K") # move up cursor and delete whole line
				queue.append(String)
				for i in range(len(queue)):
					sys.stdout.write(queue[i] + "\n") # reprint the linesprint (String)
		time.sleep(Scenario._time_parameters.get_TimeInterval()/Scenario.get_speed())

	for _ in range(len(queue)+2):
		sys.stdout.write("\x1b[1A\x1b[2K") # move up cursor and delete whole line
	subprocess.call('./shutdown_bash.sh')
def main():
	print ("Hi, you have started the satellite network emulator.")
	#Open file
	fo = open('config.toml', "r")
	TOML = toml.load(fo, _dict=dict)
	Scenario = scenario(TOML)
	while True:
		inp = input("Insert the action you wish to perform (insert 'help' to see all available actions): ").strip().lower()
		if inp == "help":
			print ("- help: shows all available actions\n- scenario: show the load nodes and his type\n- run_all: run the emulation and Cesium\n- run_emulator: run only the emulation\n- run_CESIUM: run only the visulization at Cesium\n- exit: program execution ends")
		elif inp == "scenario":
			print("The scenario is formed by ",Scenario.get_number_of_nodes()," Nodes")
			if Scenario._time_parameters.get_date_time() == None:
				print ('The emulator is working at current time')
			else:
				print ('Initialize:',Scenario._time_parameters.get_initial_date_time(),'	Ends:',Scenario._time_parameters.get_end_date_time())
			for n in range(0,Scenario.get_number_of_nodes()):
				print ('Node',n+1,": ",Scenario._node_list[n].name,"	",type(Scenario._node_list[n]).__name__,"	IP:",Scenario._node_list[n]._ip)
		elif inp == 'run' or inp == 'run_all' or inp == 'run all':
			Scenario.start_scenario(True,True)
		elif inp == 'emu' or inp == 'run_emu' or inp == 'run emu':
			Scenario.start_scenario(True,False)
		elif inp == 'cesium' or inp == 'run_cesium' or inp == 'run cesium':
			Scenario.start_scenario(False,True)
		elif inp == 'write_bash':
			Scenario.write_bash()
		elif inp == 'ssh' or inp == 'ssh_connection':
			while True:
				ans = input('Which VM do you want to connect to?').strip()
				if ans.lower() == 'all':
					for n in range(0,Scenario.get_number_of_nodes()):
						Scenario._node_list[n].ssh_connection()
					break
				else:
					Exist = False
					for n in range(0,Scenario.get_number_of_nodes()):
						if ans == Scenario._node_list[n].name:
							Scenario._node_list[n].ssh_connection()
							Exist = True
							break
					if Exist:
						break
		elif inp == "exit":
			while True:
				ans = input("Do you want delete all the VMs relete with the scenario?(Y/N):").strip().lower()
				if ans == 'y' or ans == 'yes':
					Scenario.delete_VMs()
					break
				elif ans == 'n' or ans == 'no':
					break
				else:
					print('ERROR: Invalid answer')
			break
		else:
			print (inp," is not one of the available actions")

if __name__ == "__main__":
	main()
