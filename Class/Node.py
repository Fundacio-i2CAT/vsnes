#!/usr/bin/env python3
import subprocess
import shlex
import paramiko
import time
import sys
import logging
import socket


from Class.log_config import setup_logging
setup_logging()
# mother class of Satellite and GroundStation
path = '/var/lib/libvirt/images/'

# Valid per-node lifecycle types (toml key `type`):
#   vm                 - internal libvirt VM: cloned from clone_VM.name_VM via
#                        virt-clone, started/stopped with virsh.
#   vm_external        - VM or physical device outside this host: VSNES only
#                        validates SSH reachability (ip_ext:22) and configures it.
#   container          - local Docker container managed by VSNES via the
#                        generated docker-compose.yml (created/started by us).
#   container_external - container on another host: validated over the network,
#                        never created/removed by VSNES.
NODE_TYPES = ('vm', 'vm_external', 'container', 'container_external')

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
			


			# Node lifecycle type — the single switch that decides how the node
			# is created, validated and reached (see NODE_TYPES above).
			if 'is_external_vm' in Node or 'is_docker' in Node:
				error_msg = (f"Node {name}: 'is_external_vm'/'is_docker' are obsolete — "
				             f"use type = one of {NODE_TYPES}")
				logging.error(error_msg)
				raise ValueError(error_msg)
			try:
				self.node_type = Node['type']
			except KeyError:
				error_msg = f"Missing 'type' for node {name}: must be one of {NODE_TYPES}"
				logging.error(error_msg)
				raise KeyError(error_msg)
			if self.node_type not in NODE_TYPES:
				error_msg = (f"Invalid type '{self.node_type}' for node {name}: "
				             f"must be one of {NODE_TYPES}")
				logging.error(error_msg)
				raise ValueError(error_msg)

			# ip_ext: management address. Required for every type except 'vm'
			# (internal VMs get their address from virsh domifaddr).
			self.ip_ext = Node.get('ip_ext') or None
			if self.node_type != 'vm' and not self.ip_ext:
				error_msg = (f"Missing 'ip_ext' for node {name} "
				             f"(required for type '{self.node_type}')")
				logging.error(error_msg)
				raise KeyError(error_msg)

			try:
				self._VM_interface = Node['interface']
			except KeyError:
				error_msg = f"Missing 'interface' configuration for node {name}"
				logging.error(error_msg)
				raise KeyError(error_msg)

			# clone_VM.name_VM: the libvirt base image — only meaningful (and
			# only required) for internal 'vm' nodes.
			self._clone_VM = Node.get('clone_VM', {}).get('name_VM')
			if self.node_type == 'vm' and not self._clone_VM:
				error_msg = (f"Missing 'name_VM' in clone_VM for node {name} "
				             f"(required for type 'vm')")
				logging.error(error_msg)
				raise KeyError(error_msg)

			self._mask = mask
			
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
		if self.node_type != 'vm':
			return self.ip_ext
		# Strip the trailing CIDR suffix (e.g. '/24') from the address field.
		return self._virsh_domifaddr_field(3, 'IP address', max_retries)[:-3]

	# ── type predicates ──────────────────────────────────────────────────────
	@property
	def is_container(self):
		"""Any Docker node (locally managed or external)."""
		return self.node_type in ('container', 'container_external')

	@property
	def is_internal_container(self):
		"""Docker container whose lifecycle VSNES owns (compose up/down)."""
		return self.node_type == 'container'

	@property
	def is_external(self):
		"""Node VSNES never creates/destroys — only validates over the network."""
		return self.node_type in ('vm_external', 'container_external')

	def exec_shell(self, script, timeout=60):
		'''Run a shell script inside this node, whatever it is: docker exec
		for containers, SSH for VMs/external devices. Returns
		(returncode, output). The routing layer uses only this — it never
		cares about the transport.'''
		if self.is_container:
			try:
				r = subprocess.run(['docker', 'exec', self._name, 'sh', '-c', script],
				                   capture_output=True, text=True, timeout=timeout)
				return r.returncode, (r.stderr or r.stdout).strip()
			except Exception as e:
				return 1, str(e)
		# VM / external device: SSH. Commands needing root get sudo -n (the
		# base VM ships passwordless sudo, matching the container image).
		try:
			ssh = paramiko.SSHClient()
			ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
			ssh.connect(self._get_VM_ip(), 22, self._username, self._password, timeout=10)
			_, stdout, stderr = ssh.exec_command(f'sudo -n sh -c {shlex.quote(script)}',
			                                     timeout=timeout)
			rc = stdout.channel.recv_exit_status()
			out = (stderr.read().decode(errors='replace') or
			       stdout.read().decode(errors='replace')).strip()
			ssh.close()
			return rc, out
		except Exception as e:
			return 1, str(e)

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
		if self.node_type != 'vm':
			ifb = getattr(self, '_ifb_iface', None)
			return ifb if ifb else self._VM_interface
		return self._virsh_domifaddr_field(0, 'host interface', max_retries)

	def _initial_configuration (self, nNodes, host_ip=None):
		# Sends configuration commands with ssh to the VM for change de username and defines the VLAN interface

		# Search the ip of the VM
		VM_ip = self._get_VM_ip()
		print("Intitial configuration of %s(ip:%s)"%(self._name,VM_ip))
		ssh = paramiko.SSHClient()
		ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

		if self.OS == 'ubuntu' or self.OS == 'debian' or self.OS == 'debian/ubuntu':
			# Command to change the hostname or write to file
			if self.node_type != 'vm':
				command1 = f'echo {self._name} > ~/hostname.txt;'
			else:
				# hostnamectl requires systemd-hostnamed (D-Bus), which may time out in lightweight VMs.
				# Writing directly to /etc/hostname is equivalent and has no dependencies.
				# Underscores are not valid in hostnames (RFC 952); replace with hyphens.
				# Also map it in /etc/hosts or every sudo warns 'unable to resolve host'.
				safe_hostname = self._name.replace('_', '-')
				command1 = (f'echo {self._password}|sudo -S bash -c "'
				            f'echo {safe_hostname} > /etc/hostname && hostname {safe_hostname}; '
				            f'grep -q {safe_hostname} /etc/hosts || '
				            f'echo 127.0.1.1 {safe_hostname} >> /etc/hosts"')

			# Command to make a VLAN interface and add a ip address
			print('Standard configuration')
			command2 = self._standard_Ubuntu(host_ip)

		else:
			# Command to change the hostname or write to file
			if self.node_type != 'vm':
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
				break
			except Exception as e:
				print(f"SSH connection error on {self._name}: {e}, retrying...")
				time.sleep(1)
		else:
			raise TimeoutError(f"Initial configuration of '{self._name}' failed: SSH unreachable after {max_retries} attempts")

	def _standard_Ubuntu(self, host_ip=None):
		iface = self._VM_interface   # e.g. 'eth0'
		n     = self._nodeNumber
		vname = '%s.%d' % (iface, n) # e.g. 'eth0.1'
		if self.is_container:
			# Docker containers: IFB-based tc is applied on the host; no vxlan needed.
			# The emulated 10.0.0.x address rides eth0 as a secondary IP so its
			# traffic crosses the same veth the host-side shaping captures.
			return 'sudo ip addr add %s/%s dev %s 2>/dev/null || true' % (str(self._ip), self._mask, iface)
		elif self.node_type == 'vm_external':
			# External VMs/devices: vxlan tunnel back to THIS host so eth0 stays
			# intact for management SSH. The remote must be the emulator host's
			# address (resolved by Scenario at prepare time) — the host side
			# builds the matching vxlan with remote <node.ip_ext>.
			if not host_ip:
				raise ValueError(
					f"Node '{self._name}': vm_external needs the emulator host IP "
					f"for the vxlan remote (Scenario._host_ip() failed?)")
			command  = 'sudo ip link add %s type vxlan id %d00 remote %s dev %s dstport 4789 2>/dev/null || true;'%(vname,n,host_ip,iface)
			command += 'sudo ip link set dev %s address 02:00:00:00:00:0%d 2>/dev/null || true;'%(vname,n)
			command += 'sudo ip addr add %s/%s dev %s 2>/dev/null || true;'%(str(self._ip),self._mask,vname)
			command += 'sudo ip link set dev %s up'%(vname)
		else:
			ip = str(self._ip)
			command = (
				f'echo {self._password}|sudo -S bash -c "'
				f'ip link add link {iface} name {vname} type vlan id {n} 2>/dev/null || true; '
				f'ip link set dev {vname} up; '
				# Early-boot races (networkd still settling) can silently drop a
				# one-shot addr add — verify it stuck and retry a few times.
				f'for i in 1 2 3 4 5; do '
				f'ip addr add {ip}/{self._mask} dev {vname} 2>/dev/null; '
				f'ip -4 addr show dev {vname} | grep -q \\"{ip}/\\" && break; '
				f'sleep 2; done"'
			)
		return command

	# ── lifecycle: start by node type ────────────────────────────────────────
	def start(self, nNodes, host_ip=None):
		'''Start/validate this node according to its `type` and apply the
		initial network configuration (hostname + emulated address).'''
		{
			'vm':                 self._start_libvirt_vm,
			'vm_external':        self._start_external,
			'container':          self._start_internal_container,
			'container_external': self._start_external,
		}[self.node_type](nNodes, host_ip)

	def _start_libvirt_vm(self, nNodes, host_ip=None):
		'''Internal libvirt VM: virt-clone from the base image if missing,
		start/resume it, then configure over SSH.'''
		name = self._name
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
			if not VM_status:
				raise RuntimeError(f"Base VM '{clone_VM}' for node '{name}' not found in libvirt")
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

			# Reset the clone's machine-id BEFORE first boot. Clones inherit the
			# base image's /etc/machine-id; systemd-networkd derives the DHCP
			# client-id (DUID) from it, so identical machine-ids make dnsmasq
			# hand ONE lease to the whole constellation — every clone steals the
			# previous one's address, virsh domifaddr goes empty and SSH lands
			# on the wrong VM. A truncated machine-id regenerates uniquely at
			# first boot.
			#
			# virt-clone leaves the qcow2 owned libvirt-qemu:kvm mode 0600, so
			# unprivileged libguestfs can't open it — make it accessible first
			# (sudo chmod is expected in sudoers NOPASSWD; libvirt's dynamic
			# ownership re-tightens permissions when the VM starts).
			blk = subprocess.run(f'virsh domblklist {name} --details',
			                     capture_output=True, text=True, shell=True).stdout
			for line in blk.splitlines():
				if ' disk ' in f' {line} ':
					subprocess.run(['sudo', '-n', '/usr/bin/chmod', '666',
					                line.split()[-1]], capture_output=True)
			r = subprocess.run(['virt-sysprep', '--quiet', '--operations',
			                    'machine-id', '-d', name],
			                   capture_output=True, text=True)
			if r.returncode != 0:
				logging.warning(f"virt-sysprep machine-id reset failed for '{name}' "
				                f"({r.stderr.strip()[:150]}) — clones may fight "
				                f"over one DHCP lease")

			subprocess.run(['virsh', 'start', name])
			logging.info(f"VM '{name}' started successfully")

		# Run the initial configuration with SSH
		self._initial_configuration(nNodes, host_ip)

	def _start_external(self, nNodes, host_ip=None):
		'''External VM/device or external container: never created by VSNES.
		Fail fast if unreachable, then configure over SSH.'''
		name = self._name
		logging.info(f"Validating external node '{name}' ({self.ip_ext})")
		if not self.check_VM():
			raise ConnectionError(
				f"External node '{name}' unreachable at {self.ip_ext}:22 — "
				f"check the device/VM is up and SSH is enabled")
		self._initial_configuration(nNodes, host_ip)

	def _start_internal_container(self, nNodes, host_ip=None):
		'''Local Docker container (created by start_from_compose beforehand):
		verify it is running and add the emulated address via docker exec —
		no SSH round-trip needed for the common all-container case.'''
		name = self._name
		if not self.check_VM():
			raise RuntimeError(
				f"Container '{name}' is not running — compose up should have "
				f"started it (check docker-compose.yml has a service for it)")
		cmd = f'ip addr add {self._ip}/{self._mask} dev {self._VM_interface}'
		r = subprocess.run(['docker', 'exec', name, 'sh', '-c', f'{cmd} 2>/dev/null || true'],
		                   capture_output=True, text=True, timeout=15)
		if r.returncode != 0:
			raise RuntimeError(f"Failed to configure container '{name}': {r.stderr.strip()}")
		logging.info(f"Container '{name}' configured with {self._ip}/{self._mask} on {self._VM_interface}")

	def delete_VM(self):
		name = self._name
		logging.info(f"Deleting VM '{name}'")
		
		# Search a VM with the name of the node
		cmd_status = f'virsh list --all | grep -w {name}'
		VM_status = subprocess.run(cmd_status, capture_output=True, text=True, shell=True).stdout
		
		if len(VM_status) > 0:
			# Resolve the domain's actual disk paths BEFORE undefining — clones
			# created with virt-clone --auto-clone live next to the base image
			# (not necessarily /var/lib/libvirt/images), so a fixed-path find
			# would silently leave the qcow2 behind.
			blk = subprocess.run(f'virsh domblklist {self._name} --details',
			                     capture_output=True, text=True, shell=True).stdout
			disk_paths = [line.split()[-1] for line in blk.splitlines()
			              if ' disk ' in f' {line} ' and line.strip().endswith('.qcow2')]

			logging.info(f"VM '{name}' found, shutting down...")
			shell = f'virsh shutdown {self._name}'
			subprocess.run(shell, capture_output=True, shell=True)

			logging.info(f"Undefining VM '{name}'...")
			shell = f'virsh undefine {self._name}'
			subprocess.run(shell, capture_output=True, shell=True)

			logging.info(f"Destroying VM '{name}'...")
			shell = f'virsh destroy {self._name}'
			subprocess.run(shell, shell=True)

			logging.info(f"Deleting disk images for VM '{name}': {disk_paths}")
			for p in disk_paths:
				r = subprocess.run(['rm', '-f', p], capture_output=True, text=True)
				if r.returncode != 0:   # not owner-writable dir -> root fallback
					subprocess.run(f'sudo rm -f {p}', shell=True)
			# legacy fallback for images in the default pool
			shell = f'sudo find {path} -type f -name {self._name}*.qcow2 -delete'
			subprocess.run(shell, shell=True, capture_output=True)

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
		'''Is this node up? Per type: container -> docker inspect; external
		VM/device/container -> TCP connect to ip_ext:22; internal vm -> virsh.'''
		name = self._name
		if self.node_type == 'container':
			try:
				r = subprocess.run(
					['docker', 'inspect', '-f', '{{.State.Running}}', name],
					capture_output=True, text=True, timeout=5)
				return r.returncode == 0 and r.stdout.strip() == 'true'
			except Exception:
				return False
		elif self.is_external:
			self.VM_ip = self._get_VM_ip()
			sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			sock.settimeout(5)
			result = sock.connect_ex((self.VM_ip, 22))
			sock.close()
			return result == 0
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
