from Class.Scenario import scenario
import toml

def main():
	CZML_BOOL = False
	print ("Hi, you have started the satellite network emulator.")
	config = input("Insert the name of the configuration file [config.toml]:").strip()
	if config == '':
		config = 'config.toml'
	try:
		#Open file
		fo = open(config, "r")
	except FileNotFoundError:
		print(config)
		print ('The configuration file does not exist. Create the file or check the name.')
		quit()
	try:	
		TOML = toml.load(fo, _dict=dict)
	except toml.decoder.TomlDecodeError:
		print ('Error in the format of the file %s. Verify that the information has been entered following the TOML format.'%(config))
		quit()
	Scenario = scenario(TOML)
	while True:
		inp = input("Insert the action you wish to perform (insert 'help' to see all available actions): ").strip().lower()
		if inp == "help":
			print ("- help: shows all available actions\n- scenario: show the load nodes and his type\n- start_VMs: create or start the VMs for every node.\n- delete_VM: delete a specific VM\- write_czml: write in ScenarioCZML.czml the requiret data to run Cesium for this scenario\n- ssh_connection: opens a new terminal with a SSH connection with some of the node's VM.\n- run_all: run the emulation and Cesium\n- run_emulator: run only the emulation\n- run_CESIUM: run only the visulization at Cesium\n- exit: program execution ends")
		elif inp == "scenario":
			print (Scenario.scenario_description())
		elif inp == 'write_czml' or inp == 'write czml':
			Scenario.write_czml()
			CZML_BOOL = True
		elif inp == 'start_vms' or inp == 'start vms' or inp == 'vm':
			Scenario.start_VMs()
		elif inp == 'run' or inp == 'run_all' or inp == 'run all':
			if not(CZML_BOOL):
				while True:
					ans = input("In this execution, the czml file has not been written. Do you want to load it?(Y/N):").strip().lower()
					if ans == 'y' or ans == 'yes':
						Scenario.write_czml()
						CZML_BOOL = True
						break
					elif ans == 'n' or ans == 'no':
						break
					else:
						print('ERROR: Invalid answer')
			Scenario.start_scenario(True,True)
		elif inp == 'emu' or inp == 'emulator' or inp == 'run_emu' or inp == 'run emu' or inp == 'run_emulator' or inp == 'run emulaotr':
			Scenario.start_scenario(True,False)
		elif inp == 'cesium' or inp == 'run_cesium' or inp == 'run cesium':
			if not(CZML_BOOL):
				while True:
					ans = input("In this execution, the czml file has not been written. Do you want to load it?(Y/N):").strip().lower()
					if ans == 'y' or ans == 'yes':
						Scenario.write_czml()
						CZML_BOOL = True
						break
					elif ans == 'n' or ans == 'no':
						break
					else:
						print('ERROR: Invalid answer')
			Scenario.start_scenario(False,True)
		elif inp == 'write_bash':
			Scenario.write_bash()
		elif inp == 'delete' or inp == 'delete_vm' or inp == 'delete vm':
			while True:
				ans = input('Which VM do you want to delete?').strip()
				if ans.lower() == 'all':
					for n in range(0,Scenario.get_number_of_nodes()):
						Scenario._node_list[n].delete_VM()
					break
				elif ans == 'exit':
					break
				else:
					Exist = False
					for n in range(0,Scenario.get_number_of_nodes()):
						if ans == Scenario._node_list[n].name:
							Scenario._node_list[n].delete_VM()
							Exist = True
							break
					if Exist:
						break
		elif inp == 'ssh' or inp == 'ssh_connection':
			while True:
				ans = input('Which VM do you want to connect to?').strip()
				if ans.lower() == 'all':
					for n in range(0,Scenario.get_number_of_nodes()):
						Scenario._node_list[n].ssh_connection()
					break
				elif ans == 'exit':
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
			Scenario.delete_VMs()
			break
		else:
			print (inp," is not one of the available actions")

if __name__ == "__main__":
	main()
