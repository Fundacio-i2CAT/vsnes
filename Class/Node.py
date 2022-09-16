#!/usr/bin/env python3
import subprocess
import paramiko
import time
import sys
# mother class of Satellite and GroundStation
path = '/var/lib/libvirt/images/'
class Node:
	''' A node describes network and VM properties and also the position in a time instant'''
	
	#Each node has a name property identifying the object it is describing
	_name = None
	
	#The nodeNumber is the position of the node in the list of node. This count starts in 1 instead of 0
	_nodeNumber = None
	#The ip property indicates the ip address which the VM is connected to the VLAN
	_ip = None
	
	#The mask property indicates the the mask of the VLAN network address 
	_mask = None
	
	#The clone_VM property indicates the name of the VM that the software use to create the VM of this node
	_clone_VM = None
	
	#The username property indicates the user of the clone_VM
	_username = None
	
	#The password property indicates the password of the clone_VM
	_password = None
	
	#The position property define the position in a specific instat of time
	_position = None
	
	def __init__(self,name,Node,network,mask,nNodes):
		if name == None:
			self._name = name
		else:
			self._name = name.replace(' ','_').replace('/','-').replace('(','').replace(')','').replace("'",'').replace('"','')
			self._nodeNumber = nNodes+1
			self._ip = network
			try:
				self.group = Node['group']
			except KeyError:
				self.group = name
			try:
				self.service = Node['Service']
			except KeyError:
				self.service = None
			try:
				self.EmuScript = Node['Emulation_startup_script']
			except KeyError:
				self.EmuScript = None
			while True:
				try:
					cloneVM = Node['clone_VM']
					break
				except KeyError:
					Node['clone_VM'] = {}
			while True:
				try:
					self._clone_VM = cloneVM['name_VM']
					break
				except KeyError:
					cloneVM['name_VM'] = input('Insert the name of the %s clone VM:'%(name))
			while True:	
				try:		
					self._username = cloneVM['username']
					break
				except KeyError:
					cloneVM['username'] = input('Insert the username of the %s clone VM:'%(name))
			while True:
				try:
					self._password = cloneVM['password']
					break
				except KeyError:
					cloneVM['password'] = input('Insert the password of the %s clone VM:'%(name))
			while True:
				try:
					self._VM_interface = cloneVM['interface']
					break
				except KeyError:
					cloneVM['interface'] = input('Insert the interface of the %s clone VM:'%(name))
			while True:
				try:
					self.OS  = cloneVM['OS']
					break
				except KeyError:
					cloneVM['OS'] = input('Insert the OS of the %s clone VM:'%(name))
			self._mask = mask
			Node['clone_VM'] = cloneVM
	@property
	def name(self):
		if self._name is not None:
        		return self._name
        				
	def get_basic_data(self):
        	return '%s (ip:%s)'%(self._name,self._ip)
	def _get_VM_ip(self):
		#Search the ip of the VM associated to the node and return them
		while True:
			#Somtimes the code is faster then the DHCP protocol and the VM has no ip address yet. For this reason it repeat the command 
			try:
				#The command return two lines, one with the legend and other with information of the expecific VM
				#
				VM_ip = subprocess.run('virsh domifaddr %s'%(self._name), capture_output = True, text = True, shell = True).stdout.split('\n')[2].split()[3][:-3]
				return VM_ip
			except IndexError:
				pass
	def _get_Host_interface(self):
		#Search the ip of the VM associated to the node and return them
		while True:
			#Somtimes the code is faster then the DHCP protocol and the VM has no ip address yet. For this reason it repeat the command 
			try:
				#The command return two lines, one with the legend and other with information of the expecific VM
				#
				VM_ip = subprocess.run('virsh domifaddr %s'%(self._name), capture_output = True, text = True, shell = True).stdout.split('\n')[2].split()[0]
				return VM_ip
			except IndexError:
				pass
	def _initial_configuration (self,nNodes):
		#Sends configuration commands with ssh to the VM for change de username and defines the VLAN interface
		
		#Search the ip of the VM
		VM_ip = self._get_VM_ip()
		#Define a class object SSHClient
		ssh = paramiko.SSHClient()
		ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
		if self.OS == 'ubuntu':
			#Commmand to change the username to the name of the node
			command1 = 'echo %s|sudo -S hostnamectl set-hostname %s'%(self._password,self._name)
			#Command to make a VLAN interface and add a ip address
			if self.service == 'relay' or self.service == 'Relay' or self.service == 'RELAY':
				command2 = self._relay_Ubuntu(nNodes)
			else:
				command2 = self._standard_Ubuntu()
			
		else:
			#Commmand to change the username to the name of the node
			command1 = 'echo %s|su -c hostnamectl set-hostname %s'%(self._password,self._name)
			#Command to make a VLAN interface and add a ip address
			command2 = "echo %s|su -c 'ip link add link %s name %s.%d type vlan id %d';"%(self._password,self._VM_interface,self._VM_interface,self._nodeNumber,self._nodeNumber)
			command2 += "echo %s|su -c 'ip addr add %s/%s dev %s.%d';"%(self._password,str(self._ip),self._mask,self._VM_interface, self._nodeNumber)
			command2 += "echo %s|su -c 'ip link set dev %s.%d up'"%(self._password,self._VM_interface,self._nodeNumber)
		while True:
			#Repeats the action if the connection was unsuccessfull 
			try:
				#Connect to port 22
				ssh.connect(VM_ip,22, self._username, self._password)
				#Execute the command
				ssh.exec_command(command1)
				#Connect to port 22
				ssh.connect(VM_ip,22, self._username, self._password)
				#Execute the command
				ssh.exec_command(command2)
				break
			except paramiko.ssh_exception.NoValidConnectionsError:
				pass
	def arp_table(self,node_list):
		if self.check_VM():
			#Search the ip of the VM
			VM_ip = self._get_VM_ip()
			#Define a class object SSHClient
			ssh = paramiko.SSHClient()
			ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
			for Node in node_list:
				if Node.check_VM():
					MAC = subprocess.run('virsh domifaddr %s'%(Node.name), capture_output = True, text = True, shell = True).stdout.split('\n')[2].split()[1]
					if self.OS == 'ubuntu':
						command =  'echo %s|sudo -S arp -s %s %s'%(self._password,str(Node._ip),MAC)
					else:
						command =  "echo %s|su -c 'arp -s %s %s'"%(self._password,str(Node._ip),MAC)
					#Connect to port 22
					ssh.connect(VM_ip,22, self._username, self._password)
					#Execute the command
					ssh.exec_command(command)
	def _standard_Ubuntu(self):
		#Command to make a VLAN interface and add a ip address
		command = 'echo %s|sudo -S ip link add link %s name %s.%d type vlan id %d;'%(self._password,self._VM_interface,self._VM_interface,self._nodeNumber,self._nodeNumber)
		command += 'sudo ip addr add %s/%s dev %s.%d;'%(str(self._ip),self._mask,self._VM_interface, self._nodeNumber)
		command += 'sudo ip link set dev %s.%d up'%(self._VM_interface,self._nodeNumber)
		return command
	def _relay_Ubuntu(self,nNodes):
		command = 'echo %s|sudo -S ip link add link %s name %s.%d type vlan id %d;'%(self._password,self._VM_interface,self._VM_interface,self._nodeNumber,self._nodeNumber)
		command += 'sudo ip link set dev %s.%d up;'%(self._VM_interface,self._nodeNumber)
		nodeNumber2 = nNodes + self._nodeNumber
		command += 'sudo ip link add link %s name %s.%d type vlan id %d;'%(self._VM_interface,self._VM_interface,nodeNumber2,nodeNumber2)
		command += 'sudo ip link set dev %s.%d up;'%(self._VM_interface,nodeNumber2)
		command += 'sudo brctl addbr RelayBr;'
		command += 'sudo brctl addif RelayBr %s.%d;'%(self._VM_interface,self._nodeNumber)
		command += 'sudo brctl addif RelayBr %s.%d;'%(self._VM_interface,nodeNumber2)
		command += 'sudo ip addr add %s/%s dev RelayBr;'%(str(self._ip),self._mask)
		command += 'sudo ip link set dev RelayBr up;'
		command += 'sudo brctl setageing RelayBr 0;'
		command += 'sudo brctl setfd RelayBr 0;'
		command += 'sudo ip6tables -A FORWARD -m physdev --physdev-out %s.%d -j DROP;' % (self._VM_interface,self._nodeNumber)
		command += 'sudo ip6tables -A FORWARD -m physdev --physdev-in %s.%d -j DROP;' % (self._VM_interface,self._nodeNumber)
		command += 'sudo ip6tables -A INPUT -m physdev --physdev-in %s.%d -j DROP;' % (self._VM_interface,self._nodeNumber)
		command += 'sudo ip6tables -A FORWARD -m physdev --physdev-out %s.%d -j DROP;' % (self._VM_interface,nodeNumber2)
		command += 'sudo ip6tables -A FORWARD -m physdev --physdev-in %s.%d -j DROP;' % (self._VM_interface,nodeNumber2)
		command += 'sudo ip6tables -A INPUT -m physdev --physdev-in %s.%d -j DROP;' % (self._VM_interface,nodeNumber2)
		command += 'sudo iptables -A INPUT -m physdev --physdev-in %s.%d -j DROP;' % (self._VM_interface,nodeNumber2)
		command += 'sudo tc qdisc add dev %s.%d root netem loss 100' % (self._VM_interface,self._nodeNumber)
		command += '%'
		return command
	def run_VM(self,nNodes):
		#If the VM doesn't exist, it clones a VM and stard it with the initial configuration, if it exist stard and implies the initial configuration.
		name = self._name
		#Search a VM with the name of the node
		VM_status = subprocess.run('virsh list --all | grep -w %s'%(name), capture_output = True, text = True, shell = True).stdout
		if len(VM_status)>0:
			#If the VM exist cheak its state and start it if it is necesarry
			VM_status = VM_status.split()[2]
			if VM_status == 'shut':
				subprocess.run(['virsh', 'start', name])
			elif VM_status == 'paused':
				subprocess.run(['virsh', 'resume', name])
		else:
			#If the VM doesn't exist clone an existing VM and start it
			clone_VM = self._clone_VM
			VM_status = subprocess.run('virsh list --all | grep -w %s'%(clone_VM), capture_output = True, text = True, shell = True).stdout
			VM_status = VM_status.split()[2]
			if VM_status == 'running':
				subprocess.run(['virsh', 'shutdown', clone_VM])
			while VM_status == 'running':
				VM_status = subprocess.run('virsh list --all | grep -w %s'%(clone_VM), capture_output = True, text = True, shell = True).stdout
				VM_status = VM_status.split()[2]	
			errors = 1
			shutdown = False
			while errors != 0:
				errors = subprocess.run(['virt-clone', '--original', clone_VM, '--name', name, '--auto-clone']).returncode
				sys.stdout.write("\x1b[1A\x1b[2K") # move up cursor and delete whole line
				if errors > 0 and not(shutdown):
					subprocess.run(['virsh', 'shutdown', clone_VM])
					shutdown = True
			subprocess.run(['virsh', 'start', name])
		#Run the initial configuration with SSH
		self._initial_configuration(nNodes)
	def delete_VM(self):
		name = self._name
		#Search a VM with the name of the node
		VM_status = subprocess.run('virsh list --all | grep -w %s'%(name), capture_output = True, text = True, shell = True).stdout
		if len(VM_status)>0:
			#Delete the VM and the its images
			shell = 'virsh shutdown %s'%(self._name)
			subprocess.run(shell, capture_output = True, shell = True)
			shell = 'virsh undefine %s'%(self._name)
			subprocess.run(shell, capture_output = True, shell = True)
			shell = 'virsh destroy %s'%(self._name)
			subprocess.run(shell, shell = True)
			shell = 'sudo find %s -type f -name %s*.qcow2 -delete'%(path,self._name)
			subprocess.run(shell, shell = True)
	def ssh_connection(self):
		#Open a terminal with ssh connection to the VM
		if self.check_VM():
			while True:
				#Count the number of terminals that are open
				Terminals = subprocess.run('ls /dev/pts', capture_output = True, text = True, shell = True).stdout.split()
				nTerminals_before = len(Terminals)
				#Get the ip addres of the VM
				VM_ip = self._get_VM_ip()
				#Try to connect to the VM with sshpass
				shell = 'gnome-terminal -t %s -- sshpass -p %s ssh %s@%s'%(self._name,self._password,self._username,VM_ip)
				subprocess.run(shell, shell = True)
				time.sleep(0.1)
				#Count the number of terminals that are open
				Terminals = subprocess.run('ls /dev/pts', capture_output = True, text = True, shell = True).stdout.split()
				nTerminals = len(Terminals)
				if nTerminals_before == nTerminals:
					nTerminals_before = nTerminals
					#Check if the terminal open with sshpass still opened. If it's not true, it open a new with ssh connection 
					shell = 'gnome-terminal -t %s -- ssh %s@%s'%(self._name,self._username,VM_ip)
					subprocess.run(shell, shell = True)
					time.sleep(0.1)
					#Count the number of terminals that are open
					Terminals = subprocess.run('ls /dev/pts', capture_output = True, text = True, shell = True).stdout.split()
					nTerminals = len(Terminals)
					if nTerminals_before == nTerminals:
						#Solve a problem with the key
						shell = 'ssh-keygen -f "/home/ubuntu/.ssh/known_hosts" -R "%s"'%(VM_ip)
						subprocess.run(shell, shell = True)
					else: break
						
				else: break
		else:
			print("The %s's VM is not available. It doesn't exist or is shut off"%(self._name))
	def Emulation_startup_script(self,node_list):
		if self.check_VM() and self.EmuScript != None:
			try:
				my_script = open(self.EmuScript['script']).read()
			except FileNotFoundError:
				return
			cont = 1
			for variable in self.EmuScript['variables']:
				variable = variable.split('_')
				for Node in node_list:
					if Node.name == variable[0]:
						if variable[1] == 'ip':
							var = '$%d'%(cont)
							my_script = my_script.replace(var,str(self._ip))
				cont += 1
			my_script = my_script.replace('\n',';')
			#Search the ip of the VM
			VM_ip = self._get_VM_ip()
			#Define a class object SSHClient
			ssh = paramiko.SSHClient()
			ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
			while True:
				#Repeats the action if the connection was unsuccessfull 
				try:
					#Connect to port 22
					ssh.connect(VM_ip,22, self._username, self._password)
					#Execute the command
					ssh.exec_command(my_script)
					break
				except paramiko.ssh_exception.NoValidConnectionsError:
					pass
	def check_VM(self):
		name = self._name
		#Search a VM with the name of the node
		VM_status = subprocess.run('virsh list --all | grep -w %s'%(name), capture_output = True, text = True, shell = True).stdout
		if len(VM_status)>0:
			#If the VM exist cheak its state and start it if it is necesarry
			VM_status = VM_status.split()[2]
			if VM_status == 'shut' or VM_status == 'paused':
				return False
			else:
				return True
		else:
			return False
