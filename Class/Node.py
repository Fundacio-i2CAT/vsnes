#!/usr/bin/env python3
import subprocess
import paramiko
import time
import sys
import logging
import socket


from Class.log_config import setup_logging
setup_logging()
# mother class of Satellite and GroundStation
path = '/var/lib/libvirt/images/'

class Node:
	''' A node describes network and VM properties and also the position in a time instant'''
	
	_name = None
	_nodeNumber = None
	_ip = None
	_mask = None
	_clone_VM = None
	_username = None
	_password = None
	_position = None
	
	def __init__(self, name, Node, network, mask, nNodes):
		if name is None:
			self._name = name
		else:
			self._name = name.replace(' ','_').replace('/','-').replace('(','').replace(')','').replace("'",'').replace('"','')
			self._nodeNumber = nNodes + 1
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
			try:
				self.OS = Node['OS']
			except KeyError:
				self.OS = "alpine"
				logging.warning(f"OS not specified for node {name}, defaulting to 'alpine'")

			try:
				self._username = Node['username']
			except KeyError:
				error_msg = f"Missing 'username' configuration for node {name}"
				logging.error(error_msg)
				raise KeyError(error_msg)
			try:
				self._password = Node['password']
			except KeyError:
				error_msg = f"Missing 'password' configuration for node {name}"
				logging.error(error_msg)
				raise KeyError(error_msg)
			


			try:
				self.is_external_vm = Node['is_external_vm']
			except KeyError:
				self.is_external_vm = 0
				logging.warning(f"is_external_vm not specified for node {name}, defaulting to 0 (internal)")

			# is_docker=1 in config forces Docker/IFB mode without needing docker inspect.
			# Auto-detected via docker inspect if not set.
			try:
				self._is_docker_flag = bool(int(Node.get('is_docker', 0)))
			except (TypeError, ValueError):
				self._is_docker_flag = False

			try:
				self.ip_ext = Node['ip_ext']
			except KeyError:
				self.ip_ext = None


			try:
				self._VM_interface = Node['interface']
			except KeyError:
				error_msg = f"Missing 'interface' configuration for node {name}"
				logging.error(error_msg)
				raise KeyError(error_msg)
			
			try:
				cloneVM = Node['clone_VM']
			except KeyError:
				Node['clone_VM'] = {}
				cloneVM = Node['clone_VM']
			
			try:
				self._clone_VM = cloneVM['name_VM']
			except KeyError:
				error_msg = f"Missing 'name_VM' configuration in clone_VM for node {name}"
				logging.error(error_msg)
				raise KeyError(error_msg)
			
			self._mask = mask
			Node['clone_VM'] = cloneVM
			
			logging.info(f"Node '{self._name}' initialized successfully with IP {self._ip}")

	@property
	def name(self):
		if self._name is not None:
				return self._name

	def get_basic_data(self):
			return f'{self._name} (ip:{self._ip})'

	def _virsh_domifaddr_field(self, field_index, what, max_retries=240):
		# `virsh domifaddr` prints a 2-line header then the interface row; the
		# row's fields are: Name MAC Protocol Address. Poll while libvirt/DHCP
		# is still bringing the VM up (up to ~2 min). field_index selects the
		# column (0 = interface name, 3 = address/CIDR).
		for _ in range(max_retries):
			try:
				cmd = f'virsh domifaddr {self._name}'
				out = subprocess.run(cmd, capture_output=True, text=True, shell=True).stdout
				return out.split('\n')[2].split()[field_index]
			except IndexError:
				time.sleep(0.5)  # not ready yet; avoid a busy loop
		raise TimeoutError(f"Could not obtain {what} for VM '{self._name}' after {max_retries} attempts")

	def _get_VM_ip(self, max_retries=240):
		# Search the ip of the VM associated to the node and return it.
		if self.is_external_vm:
			return self.ip_ext
		# Strip the trailing CIDR suffix (e.g. '/24') from the address field.
		return self._virsh_domifaddr_field(3, 'IP address', max_retries)[:-3]

	def _is_docker_container(self):
		"""Return True if this external-VM node is a local Docker container.
		Checks the config flag first (is_docker=1); falls back to docker inspect."""
		if not self.is_external_vm:
			return False
		if getattr(self, '_is_docker_flag', False):
			return True
		if not hasattr(self, '_docker_checked'):
			try:
				r = subprocess.run(
					['docker', 'inspect', '--format', '{{.State.Pid}}', self._name],
					capture_output=True, text=True, timeout=5)
				self._docker_checked = r.returncode == 0 and r.stdout.strip().isdigit()
			except Exception:
				self._docker_checked = False
		return self._docker_checked

	def get_docker_veth(self):
		"""Return the host-side veth interface name for this Docker container."""
		try:
			peer_idx = subprocess.run(
				['docker', 'exec', self._name, 'cat', '/sys/class/net/eth0/iflink'],
				capture_output=True, text=True, timeout=5).stdout.strip()
			links = subprocess.run(['ip', 'link', 'show'], capture_output=True, text=True).stdout
			for line in links.split('\n'):
				if line.startswith(f'{peer_idx}:'):
					return line.split(':')[1].strip().split('@')[0]
		except Exception as e:
			logging.error(f'get_docker_veth {self._name}: {e}')
		return None

	def get_docker_mac(self):
		"""Return the eth0 MAC address of this Docker container (aa:bb:cc:dd:ee:ff)."""
		try:
			r = subprocess.run(
				['docker', 'exec', self._name, 'cat', '/sys/class/net/eth0/address'],
				capture_output=True, text=True, timeout=5)
			if r.returncode == 0:
				return r.stdout.strip()
		except Exception as e:
			logging.error(f'get_docker_mac {self._name}: {e}')
		return None

	def _get_Host_interface(self, max_retries=240):
		# For Docker containers return the IFB name cached by write_bash(); for
		# external VMs return the configured interface; for internal VMs poll virsh.
		if self.is_external_vm:
			ifb = getattr(self, '_ifb_iface', None)
			return ifb if ifb else self._VM_interface
		return self._virsh_domifaddr_field(0, 'host interface', max_retries)

	def _initial_configuration (self, nNodes):
		# Sends configuration commands with ssh to the VM for change de username and defines the VLAN interface
		
		# Search the ip of the VM
		VM_ip = self._get_VM_ip()
		print("Intitial configuration of %s(ip:%s)"%(self._name,VM_ip))
		command3 = None		# Define a class object SSHClient
		ssh = paramiko.SSHClient()
		ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
		
		if self.OS == 'ubuntu' or self.OS == 'debian' or self.OS == 'debian/ubuntu':
			# Command to change the hostname or write to file
			if self.is_external_vm:
				command1 = f'echo {self._name} > ~/hostname.txt;'
			else:
				# hostnamectl requires systemd-hostnamed (D-Bus), which may time out in lightweight VMs.
				# Writing directly to /etc/hostname is equivalent and has no dependencies.
				# Underscores are not valid in hostnames (RFC 952); replace with hyphens.
				safe_hostname = self._name.replace('_', '-')
				command1 = f'echo {self._password}|sudo -S bash -c "echo {safe_hostname} > /etc/hostname && hostname {safe_hostname}"'
			
			# Command to make a VLAN interface and add a ip address
			if self.service in ['relay', 'Relay', 'RELAY']:
				command2 = self._relay_Ubuntu()
				command3 = self._relay_Ubuntu_ext(VM_ip)
			else:
				if self.service in ['batman', 'Batman', 'BATMAN']:
					command2 = self._batman_Ubuntu()
				else:
					print('Standard configuration')
					command2 = self._standard_Ubuntu()
			
		else:
			# Command to change the hostname or write to file
			if self.is_external_vm:
				command1 = f'echo {self._name} > ~/hostname.txt;'
			else:
				safe_hostname = self._name.replace('_', '-')
				command1 = f'echo {self._password}|su -c "echo {safe_hostname} > /etc/hostname && hostname {safe_hostname}"'
			
			# Command to make a VLAN interface and add a ip address
			command2 = f"echo {self._password}|su -c 'ip link add link {self._VM_interface} name {self._VM_interface}.1 type vlan id {self._nodeNumber}';"
			command2 += f"echo {self._password}|su -c 'ip addr add {self._ip}/{self._mask} dev {self._VM_interface}.1';"
			command2 += f"echo {self._password}|su -c 'ip link set dev {self._VM_interface}.1 up'"
		
		max_retries = 120
		for attempt in range(max_retries):
			# Repeats the action if the connection was unsuccessfull
			try:
				#Connect to port 22
				ssh.connect(VM_ip, 22, self._username, self._password, timeout=10)

				# Execute command 1 and check for success
				stdin, stdout, stderr = ssh.exec_command(command1)
				exit_status_1 = stdout.channel.recv_exit_status()
				if exit_status_1 != 0:
					print(f"Error executing command 1 on {self._name}:")
					print(stderr.read().decode())

				# Execute command 2 and check for success
				stdin, stdout, stderr = ssh.exec_command(command2)
				errores = stderr.read().decode('utf-8')
				exit_status_2 = stdout.channel.recv_exit_status()
				if exit_status_2 != 0:
					print(f"Error executing command 2 on {self._name}:")
					print(errores)

				ssh.close()
					#If the node is a VM in Relay mode, it configures the external VM
				if command3 != None:
					ssh.connect(self.VM_ip, 22, self._username, self._password, timeout=10)

					#Execute command 1 and check for success
					stdin, stdout, stderr = ssh.exec_command(command3)
					exit_status_3 = stdout.channel.recv_exit_status()
					if exit_status_3 != 0:
						print(f"Error executing command 3 on external VM:")
						print(stderr.read().decode())

					ssh.close()
				break
			except Exception as e:
				print(f"SSH connection error on {self._name}: {e}, retrying...")
				time.sleep(1)
		else:
			raise TimeoutError(f"Initial configuration of '{self._name}' failed: SSH unreachable after {max_retries} attempts")

	def _standard_Ubuntu(self):
		iface = self._VM_interface   # e.g. 'eth0'
		n     = self._nodeNumber
		vname = '%s.%d' % (iface, n) # e.g. 'eth0.1'
		if self.is_external_vm:
			# Docker containers: IFB-based tc is applied on the host; no vxlan needed.
			# The emulated 10.0.0.x address rides eth0 as a secondary IP so its
			# traffic crosses the same veth the host-side shaping captures.
			if self._is_docker_container():
				return 'sudo ip addr add %s/%s dev %s 2>/dev/null || true' % (str(self._ip), self._mask, iface)
			# Real external VMs: vxlan tunnel so eth0 stays intact for management SSH.
			command  = 'sudo ip link add %s type vxlan id %d00 remote 172.27.12.11 dev %s dstport 4789 2>/dev/null || true;'%(vname,n,iface)
			command += 'sudo ip link set dev %s address 02:00:00:00:00:0%d 2>/dev/null || true;'%(vname,n)
			command += 'sudo ip addr add %s/%s dev %s 2>/dev/null || true;'%(str(self._ip),self._mask,vname)
			command += 'sudo ip link set dev %s up'%(vname)
		else:
			command = (
				f'echo {self._password}|sudo -S bash -c "'
				f'ip link add link {iface} name {vname} type vlan id {n} 2>/dev/null || true; '
				f'ip addr add {str(self._ip)}/{self._mask} dev {vname} 2>/dev/null || true; '
				f'ip link set dev {vname} up"'
			)
		return command

	def _relay_Ubuntu(self):
		command = 'echo %s|sudo -S ip link add link %s name %s.%d type vlan id %d;'%(self._password,self._VM_interface,self._VM_interface,self._nodeNumber,self._nodeNumber)
		command += 'echo %s|sudo -S ip addr add %s/%s dev %s.%d;'%(self._password,str(self._ip),self._mask,self._VM_interface, self._nodeNumber)
		command += 'echo %s|sudo -S ip link set dev %s.%d up;'%(self._password,self._VM_interface,self._nodeNumber)
		command += 'echo %s|sudo -S sysctl -w net.ipv4.ip_forward=1;'%(self._password) 
		# command += 'echo %s|sudo -S iptables -t nat -A POSTROUTING -o %s.%d -j MASQUERADE' % (self._password,self._VM_interface,self._nodeNumber)
		
		# TODO: Fixed configuratoin of iptables for relay mode (assuming external VM in 192.168.122.40, if enp1s0.2, and relay VM in 10.0.0.2)
		# 1. Flush all existing rules in the FORWARD chain and NAT table
		# sudo iptables -F FORWARD
		# sudo iptables -t nat -F PREROUTING
		# sudo iptables -t nat -F POSTROUTING
		# 2. Set a default DROP policy
		# sudo iptables -P FORWARD DROP
		# 3. Add the new, correct rules
		# Allow established connections
		# sudo iptables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
		# Allow NEW traffic from .40 via enp1s0 to be forwarded out enp1s0.2
		# sudo iptables -A FORWARD -i enp1s0 -o enp1s0.2 -s 192.168.122.40 -m conntrack --ctstate NEW -j ACCEPT
		# DNAT return traffic: if a packet arrives on enp1s0.2 (and unfortunately is leaked to enp1s0) for this router, send it to .40
		# sudo iptables -t nat -A PREROUTING -i enp1s0.2 -d 10.0.0.2 -j DNAT --to-destination 192.168.122.40
		# sudo iptables -t nat -A PREROUTING -i enp1s0 -d 10.0.0.2 -j DNAT --to-destination 192.168.122.40
		# Allow the DNAT'd traffic to be forwarded from enp1s0.2 out to enp1s0
		# sudo iptables -A FORWARD -i enp1s0.2 -o enp1s0 -d 192.168.122.40 -j ACCEPT
		# Masquerade outbound traffic from .40 leaving enp1s0.2
		# sudo iptables -t nat -A POSTROUTING -s 192.168.12TODO2.40 -o enp1s0.2 -j MASQUERADE

		#command += 'sudo tc qdisc add dev %s.%d root netem loss 100' % (self._VM_interface,self._nodeNumber)
		#command += '%'
		return command
	def _relay_Ubuntu_ext(self, VM_ip):
		command = 'echo %s|sudo -S ip route add 10.0.0.0/24 via %s dev vsnes;'%(self._password,VM_ip)
		#print(command)
		return command
	def _batman_Ubuntu(self):
		command = 'echo %s|sudo -S ip link add link %s name %s.%d type vlan id %d;'%(self._password,self._VM_interface,self._VM_interface,self._nodeNumber,self._nodeNumber)
		#sudo ip link set enp1s0.1 down
		#sudo ip addr flush dev enp1s0.1
		#sudo ip link set enp1s0.1 up
		command += 'echo %s|sudo -S ip link set dev %s.%d up;'%(self._password,self._VM_interface,self._nodeNumber)
		command += 'echo %s|sudo -S sysctl -w net.ipv4.ip_forward=1;'%(self._password) 
		command += 'echo %s|sudo -S modprobe batman-adv;'%(self._password) 
		command += 'echo %s|sudo -S batctl if add %s.%d;'%(self._password,self._VM_interface,self._nodeNumber)
		command += 'echo %s|sudo -S ip link set bat0 up;'%(self._password)
		command += 'echo %s|sudo -S ip addr add %s/%s dev bat0;'%(self._password,str(self._ip),self._mask)
		command += 'echo %s|sudo -S iptables -t nat -A POSTROUTING -o %s.%d -j MASQUERADE' % (self._password,self._VM_interface,self._nodeNumber)
		#command += 'sudo tc qdisc add dev %s.%d root netem loss 100' % (self._VM_interface,self._nodeNumber)
		#command += '%'
		return command

	def run_VM(self, nNodes):
		# If the VM doesn't exist, it clones a VM and stard it with the initial configuration, if it exist stard and implies the initial configuration.
		name = self._name

		if self.is_external_vm:
			logging.info(f"Using external host for node '{name}'")
			self._initial_configuration(nNodes)
		else:

			logging.info(f"Starting VM for node '{name}'")
			
			# Search a VM with the name of the node
			cmd_status = f'virsh list --all | grep -w {name}'
			VM_status = subprocess.run(cmd_status, capture_output=True, text=True, shell=True).stdout
			
			if len(VM_status) > 0:
				# If the VM exist check its state and start it if it is necesarry
				VM_status = VM_status.split()[2]
				if VM_status == 'shut':
					logging.info(f"VM '{name}' is shut down, starting...")
					subprocess.run(['virsh', 'start', name])
				elif VM_status == 'paused':
					logging.info(f"VM '{name}' is paused, resuming...")
					subprocess.run(['virsh', 'resume', name])
			else:
				# If the VM doesn't exist clone an existing VM and start it
				logging.info(f"VM '{name}' does not exist, cloning from '{self._clone_VM}'")
				clone_VM = self._clone_VM
				cmd_clone_status = f'virsh list --all | grep -w {clone_VM}'
				VM_status = subprocess.run(cmd_clone_status, capture_output=True, text=True, shell=True).stdout
				VM_status = VM_status.split()[2]
				
				if VM_status == 'running':
					logging.info(f"Source VM '{clone_VM}' is running, shutting down for cloning...")
					subprocess.run(['virsh', 'shutdown', clone_VM])
				
				while VM_status == 'running':
					VM_status = subprocess.run(cmd_clone_status, capture_output=True, text=True, shell=True).stdout
					VM_status = VM_status.split()[2]	
					time.sleep(1) # Prevent busy waiting

				errors = 1
				shutdown = False
				while errors != 0:
					errors = subprocess.run(['virt-clone', '--original', clone_VM, '--name', name, '--auto-clone']).returncode
					sys.stdout.write("\x1b[1A\x1b[2K") # move up cursor and delete whole line
					if errors > 0 and not(shutdown):
						logging.warning(f"Clone failed, shutting down source VM '{clone_VM}'")
						subprocess.run(['virsh', 'shutdown', clone_VM])
						shutdown = True
						time.sleep(2) # Give it time to shut down

				subprocess.run(['virsh', 'start', name])
				logging.info(f"VM '{name}' started successfully")
			
			# Run the initial configuration with SSH
			self._initial_configuration(nNodes)

	def delete_VM(self):
		name = self._name
		logging.info(f"Deleting VM '{name}'")
		
		# Search a VM with the name of the node
		cmd_status = f'virsh list --all | grep -w {name}'
		VM_status = subprocess.run(cmd_status, capture_output=True, text=True, shell=True).stdout
		
		if len(VM_status) > 0:
			# Delete the VM and the its images
			logging.info(f"VM '{name}' found, shutting down...")
			shell = f'virsh shutdown {self._name}'
			subprocess.run(shell, capture_output=True, shell=True)
			
			logging.info(f"Undefining VM '{name}'...")
			shell = f'virsh undefine {self._name}'
			subprocess.run(shell, capture_output=True, shell=True)
			
			logging.info(f"Destroying VM '{name}'...")
			shell = f'virsh destroy {self._name}'
			subprocess.run(shell, shell=True)
			
			logging.info(f"Deleting disk images for VM '{name}'...")
			shell = f'sudo find {path} -type f -name {self._name}*.qcow2 -delete'
			subprocess.run(shell, shell=True)
			
			logging.info(f"VM '{name}' deleted successfully")
		else:
			logging.warning(f"VM '{name}' not found for deletion")

	def stop_VM(self):
		name = self._name
		logging.info(f"Stopping VM '{name}'")
		
		# Search a VM with the name of the node
		cmd_status = f'virsh list --all | grep -w {name}'
		VM_status = subprocess.run(cmd_status, capture_output=True, text=True, shell=True).stdout
		if len(VM_status) > 0:
			# If the VM exist check its state and stop it if it is necesarry
			VM_status = VM_status.split()[2]
			if VM_status == 'running':
				logging.info(f"VM '{name}' is running, shutting down...")
				subprocess.run(['virsh', 'shutdown', name])
			elif VM_status == 'paused':
				logging.info(f"VM '{name}' is paused, resuming before shutdown...")
				subprocess.run(['virsh', 'resume', name])
				subprocess.run(['virsh', 'shutdown', name])
		else:
			logging.warning(f"VM '{name}' not found for stopping")

	def Emulation_startup_script(self, node_list):
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
							var = f'${cont}'
							my_script = my_script.replace(var, str(self._ip))
				cont += 1
			my_script = my_script.replace('\n',';')
			# Search the ip of the VM
			VM_ip = self._get_VM_ip()
			# Define a class object SSHClient
			ssh = paramiko.SSHClient()
			ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
			max_retries = 60
			for _ in range(max_retries):
				# Repeats the action if the connection was unsuccessfull
				try:
					# Connect to port 22
					ssh.connect(VM_ip, 22, self._username, self._password, timeout=10)
					# Execute the command
					ssh.exec_command(my_script)
					break
				except paramiko.ssh_exception.NoValidConnectionsError:
					time.sleep(1) # Wait before retry
			else:
				logging.error(f"EmuScript for '{self._name}' not executed: SSH unreachable after {max_retries} attempts")

	def check_VM(self):
		name = self._name
		if self.is_external_vm:
			self.VM_ip = self._get_VM_ip()
			sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			result = sock.connect_ex((self.VM_ip, 22))
			sock.close()
			if result == 0:
				return True
			else:
				return False
		else:

			#Search a VM with the name of the node
			cmd_status = f'virsh list --all | grep -w {name}'
			VM_status = subprocess.run(cmd_status, capture_output = True, text = True, shell = True).stdout
			if len(VM_status)>0:
				#If the VM exist cheak its state and start it if it is necesarry
				VM_status = VM_status.split()[2]
				if VM_status == 'shut' or VM_status == 'paused':
					return False
				else:
					return True
			else:
				return False
