#!/usr/bin/env python3
import subprocess
import paramiko
import time
# mother class of Satellite and GroundStation
path = '/var/lib/libvirt/images/'
class Node:
	''' A node describes network and VM properties and also the position in a time instant'''
	
	#Each node has a name property identifying the object it is describing
	_name = None
	
	#The nodeNumber is the position of the node in the list of node. This count starts in 1 insted of 0
	_nodeNumber = None
	#The ip property indicates the ip address witch the VM is connected to the VLAN
	_ip = None
	
	#The mask property indicates the the mask of the VLAN network address 
	_mask = None
	
	#The clone_VM property indicates the name of the VM that the software use to create the VM of this node
	_clone_VM = None
	
	#The username property indicates the user of the clone_VM
	_username = None
	
	#The password property indicates the password of the clone_VM
	_password = None
	
	#The position property define the position in a concret instat of time
	_position = None
	
	def __init__(self,name,channels,cloneVM,network,mask,nNodes):
		self._name = name
		self._nodeNumber = nNodes+1
		self._ip = network
		self.channels = channels
		self._clone_VM = cloneVM['name_VM']
		self._username = cloneVM['username']
		self._password = cloneVM['password']
		self._mask = mask
	@property
	def name(self):
		if self._name is not None:
        		return self._name
        		
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
	def _initial_configuration (self):
		#Sends configuration commands with ssh to the VM for change de username and defines the VLAN interface
		
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
				#Commmand to change the username to the name of the node
				command = 'echo %s|sudo -S hostnamectl set-hostname %s'%(self._password,self._name)
				#Execute the command
				ssh.exec_command(command)
				#Connect to port 22
				ssh.connect(VM_ip,22, self._username, self._password)
				#Command to make a VLAN interface in enp1s0 and add a ip address
				command = 'echo %s|sudo -S ip link add link enp1s0 name enp1s0.%d type vlan id %d;sudo ip addr add %s/%s dev enp1s0.%d; sudo ip link set dev enp1s0.%d up' %(self._password,self._nodeNumber,self._nodeNumber,str(self._ip),self._mask, self._nodeNumber,self._nodeNumber)
				#Execute the command
				ssh.exec_command(command)
				break
			except paramiko.ssh_exception.NoValidConnectionsError:
				pass
	def run_VM(self):
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
			errors = 1
			shutdown = False
			while errors != 0:
				errors = subprocess.run(['virt-clone', '--original', clone_VM, '--name', name, '--auto-clone']).returncode
				if errors > 0 and not(shutdown):
					subprocess.run(['virsh', 'shutdown', clone_VM])
					shutdown = True
			subprocess.run(['virsh', 'start', name])
		#Run the initial configuration with SSH
		self._initial_configuration()
	def delete_VM(self):
		#Delete the VM and the its images
		shell = 'virsh shutdown %s'%(self._name)
		subprocess.run(shell, capture_output = True, shell = True)
		shell = 'virsh undefine %s'%(self._name)
		subprocess.run(shell, capture_output = True, shell = True)
		shell = 'virsh destroy %s'%(self._name)
		subprocess.run(shell, shell = True)
		shell = 'find %s -type f -name %s*.qcow2 -delete'%(path,self._name)
		subprocess.run(shell, shell = True)
	def ssh_connection(self):
		#Open a terminal with ssh connection to the VM
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
			#Check if the terminal open with sshpass still opened. If it's not true, it open a new with ssh connection 
			shell = 'gnome-terminal -t %s -- ssh %s@%s'%(self._name,self._username,VM_ip)
			subprocess.run(shell, shell = True)
	def get_ECEF(self):
		#Return the last saved position in ECEF[m]
		return self._position.itrs_xyz.m
	def get_LLA(self):
		#Return the last saved position in Latitud[º], Longitud[º] and heigth [m]
		return [self._position.latitude.degrees,self._position.longitude.degrees,self._position.elevation.m]
