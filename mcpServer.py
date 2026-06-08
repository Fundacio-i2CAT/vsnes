#!/usr/bin/env python3
"""
Simplified Model Context Protocol (MCP) Server for Satellite Network Emulator

Tailored for a local workflow: prepare -> start -> stop
"""

from fastmcp import FastMCP
from pydantic import BaseModel, Field
from typing import Literal
import httpx
import logging
import sys
import os
import paramiko
import xml.etree.ElementTree as ET
import time
import asyncio
try:
    import tomllib
except ImportError:
    import tomli as tomllib
import json
from typing import Dict, Any, List, Optional, Union
# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

try:
    import libvirt
except ImportError:
    logger.warning("libvirt not found. VM management tools will be disabled.")
    # Mock libvirt to avoid NameError
    class MockLibvirt:
        def __init__(self):
            self.VIR_DOMAIN_RUNNING = 1
            self.VIR_DOMAIN_PAUSED = 2
            self.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_LEASE = 1
            self.VIR_IP_ADDR_TYPE_IPV4 = 1
        def open(self, uri): return None
        class libvirtError(Exception): pass
    libvirt = MockLibvirt()


# Configuration
API_BASE_URL = os.getenv("SNES_API_URL", "http://localhost:5050")
API_TIMEOUT = 60.0  # Increased timeout for longer operations

# VM / SSH Config
SSH_USERNAME = os.getenv("VM_SSH_USER", "debian")
SSH_PASSWORD = os.getenv("VM_SSH_PASS", "debian")
SSH_TIMEOUT = 10
LIBVIRT_URI = 'qemu:///system'



# Initialize FastMCP server
mcp = FastMCP("A simplified MCP server for local VSNES satellite network emulation control."
)
# ============================================================================
# HELPER CLASS: VM MANAGER (Libvirt + Paramiko)
# ============================================================================

class VMManager:
    """Helper class to handle Libvirt interactions and SSH connections."""
    
    def __init__(self):
        self.conn = None

    def _connect(self):
        """Establish connection to Libvirt."""
        try:
            self.conn = libvirt.open(LIBVIRT_URI)
            if self.conn is None:
                raise Exception(f"Failed to open connection to {LIBVIRT_URI}")
        except Exception as e:
            logger.error(f"Libvirt connection error: {e}")
            raise

    def _close(self):
        """Close Libvirt connection."""
        if self.conn:
            try:
                self.conn.close()
            except:
                pass
            self.conn = None

    def get_all_vms(self) -> List[Dict[str, Any]]:
        """List all VMs (active and inactive) with details."""
        self._connect()
        vms = []
        try:
            # List defined (inactive) and active domains
            domains = self.conn.listAllDomains()
            for domain in domains:
                state, _ = domain.state()
                name = domain.name()
                
                state_str = "off"
                if state == libvirt.VIR_DOMAIN_RUNNING:
                    state_str = "on"
                elif state == libvirt.VIR_DOMAIN_PAUSED:
                    state_str = "paused"
                
                ip = self._get_vm_ip(domain) if state_str == "on" else None
                
                vms.append({
                    "name": name,
                    "state": state_str,
                    "ip": ip or "Unknown"
                })
        except Exception as e:
            logger.error(f"Error listing VMs: {e}")
        finally:
            self._close()
        return vms

    def _get_vm_ip(self, domain) -> Optional[str]:
        """Extract IP address from Libvirt leases or XML."""
        try:
            # Method 1: Interface Addresses (ARP/DHCP Leases)
            ifaces = domain.interfaceAddresses(libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_LEASE)
            for _, val in ifaces.items():
                if val.get('addrs'):
                    for addr in val['addrs']:
                        if addr['type'] == libvirt.VIR_IP_ADDR_TYPE_IPV4:
                            ip = addr['addr']
                            if not ip.startswith('127.'):
                                return ip
        except Exception:
            pass # Fallback or silent fail
        return None

    def set_power_state(self, vm_name: str, action: str) -> str:
        """Start or Stop a VM."""
        self._connect()
        try:
            try:
                domain = self.conn.lookupByName(vm_name)
            except libvirt.libvirtError:
                return f"Error: VM '{vm_name}' not found."

            if action == "start":
                if domain.isActive():
                    return f"VM '{vm_name}' is already running."
                domain.create() # 'create' boots a defined domain
                return f"VM '{vm_name}' started."
            
            elif action == "stop":
                if not domain.isActive():
                    return f"VM '{vm_name}' is already stopped."
                # Try graceful shutdown first, then destroy
                try:
                    domain.shutdown() 
                    return f"VM '{vm_name}' shutdown signal sent."
                except:
                    domain.destroy() # Force off
                    return f"VM '{vm_name}' forced off."
            
            return "Invalid action."
        except Exception as e:
            return f"Error managing power for {vm_name}: {str(e)}"
        finally:
            self._close()

    def run_ssh_command(self, ip: str, command: str) -> Dict[str, Any]:
        """Run a command via SSH on a specific IP."""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        result = {"ip": ip, "command": command, "output": "", "error": "", "status": "failed"}
        
        try:
            client.connect(
                ip, 
                username=SSH_USERNAME, 
                password=SSH_PASSWORD, 
                timeout=SSH_TIMEOUT
            )
            stdin, stdout, stderr = client.exec_command(command, timeout=30)
            
            out_str = stdout.read().decode().strip()
            err_str = stderr.read().decode().strip()
            exit_code = stdout.channel.recv_exit_status()
            
            result["output"] = out_str
            result["error"] = err_str
            result["status"] = "success" if exit_code == 0 else "error"
            
        except Exception as e:
            result["error"] = str(e)
        finally:
            client.close()
        
        return result

# Instantiate helper
vm_manager = VMManager()

# ============================================================================
# PART 1: SATELLITE EMULATOR TOOLS (HTTP API)
# ============================================================================

async def call_api(method: str, endpoint: str, json_data: Dict[str, Any] = None) -> Dict[str, Any]:
    """Helper: Make an HTTP request to the emulator API"""
    url = f"{API_BASE_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}
    
    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            if method.upper() == "GET":
                response = await client.get(url, headers=headers)
            elif method.upper() == "POST":
                response = await client.post(url, headers=headers, json=json_data)
            elif method.upper() == "DELETE":
                response = await client.delete(url, headers=headers)
            else:
                return {"status": "error", "message": f"Unsupported method: {method}"}
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"API Error {url}: {e}")
        return {"status": "error", "message": str(e)}

@mcp.tool()
async def prepare_simulation() -> Dict[str, Any]:
    """Load config and initialize scenario (Satellite Emulator)."""
    logger.info("Preparing simulation...")
    load = await call_api("POST", "/api/load-config")
    if load.get("status") == 'error': return load
    return await call_api("POST", "/api/init-scenario")

@mcp.tool()
async def start_simulation() -> Dict[str, Any]:
    """Start the physics and network simulation (Satellite Emulator)."""
    status = await call_api("GET", "/api/status")
    if not status.get('scenario_loaded', False):
        return {"status": "error", "message": "Scenario not loaded."}
    return await call_api("POST", "/api/simulation/start", {})

@mcp.tool()
async def stop_simulation() -> Dict[str, Any]:
    """Stop simulation, and reset system (Satellite Emulator)."""
    return await call_api("POST", "/api/reset")

@mcp.tool()
async def get_emulator_status() -> Dict[str, Any]:
    """Get the status of the Satellite Emulator API."""
    return await call_api("GET", "/api/status")

# ============================================================================
# PART 2: VM MANAGEMENT TOOLS (Direct Libvirt/SSH)
# ============================================================================

@mcp.tool()
def list_vms() -> List[Dict[str, str]]:
    """
    Lists all Virtual Machines managed by Libvirt/Virt-Manager.
    Returns a list of objects containing: name, state (on/off), and ip_address.
    """
    return vm_manager.get_all_vms()

@mcp.tool()
async def manage_vm_power(target: str, action: str) -> Dict[str, Any]:
    """
    Start or Stop Virtual Machines.
    
    Args:
        target: The name of the VM, or "all" to affect all VMs.
        action: Either "start" or "stop".
    """
    action = action.lower()
    if action not in ["start", "stop"]:
        return {"status": "error", "message": "Action must be 'start' or 'stop'"}

    vms = vm_manager.get_all_vms()
    results = []

    # Determine targets
    targets_to_process = []
    if target.lower() == "all":
        targets_to_process = [vm['name'] for vm in vms]
    else:
        # Verify single target exists
        if not any(vm['name'] == target for vm in vms):
            return {"status": "error", "message": f"VM '{target}' not found"}
        targets_to_process = [target]

    # Process
    for name in targets_to_process:
        logger.info(f"Performing {action} on {name}")
        # We run this in a thread because libvirt calls can be blocking
        msg = await asyncio.to_thread(vm_manager.set_power_state, name, action)
        results.append({
            "vm": name,
            "result": msg
        })

    return {"status": "completed", "details": results}

@mcp.tool()
async def execute_vm_command(target: str, command: str) -> Dict[str, Any]:
    """
    Execute a shell command via SSH on a VM (or all VMs).
    Note: The VM must be ON and have an IP address accessible.
    
    Args:
        target: The name of the VM, or "all".
        command: The shell command to execute (e.g., 'uptime', 'apt update').
    """
    vms = vm_manager.get_all_vms()
    results = []
    
    # Filter for targets that are ON and have IPs
    active_targets = []
    
    if target.lower() == "all":
        active_targets = [vm for vm in vms if vm['state'] == 'on' and vm['ip'] != 'Unknown']
    else:
        found = next((vm for vm in vms if vm['name'] == target), None)
        if not found:
            return {"status": "error", "message": f"VM '{target}' not found"}
        if found['state'] != 'on' or found['ip'] == 'Unknown':
            return {"status": "error", "message": f"VM '{target}' is not running or has no IP"}
        active_targets = [found]

    if not active_targets:
        return {"status": "warning", "message": "No valid running targets found."}

    logger.info(f"Executing command '{command}' on {len(active_targets)} VMs...")

    # Execute SSH commands (could be parallelized, doing sequential for safety here)
    for vm in active_targets:
        res = await asyncio.to_thread(vm_manager.run_ssh_command, vm['ip'], command)
        results.append({
            "vm_name": vm['name'],
            "ip": vm['ip'],
            "output": res['output'],
            "error": res['error'],
            "status": res['status']
        })

    return {"status": "completed", "results": results}

# ============================================================================
# PART 3: CONFIGURATION GENERATION TOOLS
# ============================================================================

SNES_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Pydantic Models ---

class SatelliteConfig(BaseModel):
    name: str = Field(description="Satellite name, e.g. 'SATELLITE-1'")
    group: str = Field(default="LEO", description="Orbital group name, e.g. 'LEO', 'GEO'")
    propagator: Literal["SGP4", "TwoBody"] = Field(default="SGP4")
    service: Literal["Standard", "Relay"] = Field(default="Standard")
    os: Literal["debian", "ubuntu", "alpine"] = Field(default="debian")
    username: str = Field(default="debian")
    password: str = Field(default="debian")
    is_external_vm: int = Field(default=1, description="1=Docker/external VM, 0=libvirt VM")
    ip_ext: str = Field(default="", description="IP on external network, e.g. '172.27.12.101'")
    interface: str = Field(default="eth0")

class GroundStationConfig(BaseModel):
    name: str = Field(description="Ground station name, e.g. 'Ibi_ES'")
    group: str = Field(default="GS")
    latitude: float = Field(description="Latitude in decimal degrees")
    longitude: float = Field(description="Longitude in decimal degrees")
    height: float = Field(default=15, description="Height in meters")
    os: Literal["debian", "ubuntu", "alpine"] = Field(default="debian")
    username: str = Field(default="debian")
    password: str = Field(default="debian")
    is_external_vm: int = Field(default=1)
    ip_ext: str = Field(default="", description="Required if is_external_vm=1")
    interface: str = Field(default="eth0")

class ChannelConfig(BaseModel):
    node1: str = Field(description="Source group name, e.g. 'LEO'")
    node2: str = Field(description="Target group name, e.g. 'GS'")
    min_elevation_angle: float = Field(default=0, description="Minimum elevation angle in degrees")
    threshold: float = Field(default=2e12, description="Distance threshold in meters")
    data_rate: int = Field(default=10000, description="Data rate in Mbit/s")
    packet_loss: float = Field(default=0, description="Packet loss percentage")
    correlated_losses: float = Field(default=0, description="Correlated packet burst loss percentage")

class TimeConfig(BaseModel):
    time_interval: float = Field(default=0.25, description="Simulation time step in minutes")
    contact_speed: float = Field(default=25, description="Simulation speed during contact events")
    non_contact_speed: float = Field(default=200, description="Simulation speed when no contact")
    start_datetime: str = Field(description="Start time 'YYYY-MM-DD HH:MM:SS'")
    end_datetime: str = Field(description="End time 'YYYY-MM-DD HH:MM:SS'")

class DockerServiceConfig(BaseModel):
    name: str = Field(description="Container name (also used as hostname)")
    ip_address: str = Field(description="Static IP on the Docker network")
    os: Literal["debian", "ubuntu", "alpine"] = Field(default="debian")


# --- Tool 1: get_config_guide ---

@mcp.tool()
async def get_config_guide() -> Dict[str, Any]:
    """
    Returns a structured guide for configuring a satellite network emulation scenario.
    
    Call this FIRST before generate_config_toml. It provides:
    - What questions to ask the user, organized by section
    - Context-aware reasoning for each parameter
    - Suggested defaults and typical value ranges
    - Channel configuration guidance based on link type
    
    The LLM should use this guide to conduct a natural conversation with the user,
    then call generate_config_toml with the collected parameters.
    """
    return {
        "guide_version": "1.0",
        "workflow": [
            "1. Call this guide tool first",
            "2. Ask the user questions section by section",
            "3. Use reasoning below to provide smart suggestions",
            "4. Call generate_config_toml with all collected params",
            "5. Optionally call generate_docker_compose for container setup"
        ],
        "sections": {
            "time": {
                "title": "Simulation Time",
                "questions": [
                    "What start and end date/time for the simulation?",
                    "What simulation speed during contact? (default: 25x)",
                    "What simulation speed when no contact? (default: 200x)"
                ],
                "reasoning": "Contact speed controls how fast time advances when satellites are visible to ground stations. Lower = more detailed simulation. Non-contact speed jumps quickly between pass windows.",
                "defaults": {
                    "time_interval": 0.25,
                    "contact_speed": 25,
                    "non_contact_speed": 200
                }
            },
            "satellites": {
                "title": "Satellite Configuration",
                "questions_per_satellite": [
                    "Name (e.g. SATELLITE-1)",
                    "Orbital group name (e.g. LEO, GEO used for channel routing)",
                    "Propagator: SGP4 (uses TLE data, realistic) or TwoBody (simplified)",
                    "Service type: Standard (direct downlink) or Relay (routes through another satellite)",
                    "Operating system on the node (default: debian)",
                    "Credentials (default: debian/debian)",
                    "Is this an external VM/container? (default: yes)",
                    "External IP address (auto-assigned if left blank)"
                ],
                "reasoning": {
                    "propagator": "SGP4 requires a valid TLE in the TLE file matching the satellite name/number. TwoBody only needs orbital parameters and is good for testing.",
                    "service": "Relay satellites forward traffic from other nodes — useful for store-and-forward architectures. Standard satellites communicate directly with ground stations.",
                    "groups": "All satellites in the same orbit share a group name."
                }
            },
            "ground_stations": {
                "title": "Ground Station Configuration",
                "questions_per_station": [
                    "Name (e.g. Ibi_ES, Foggia_IT)",
                    "Latitude and longitude (decimal degrees)",
                    "Altitude in meters",
                    "Same OS/credential/network questions as satellites"
                ],
                "reasoning": {
                    "location": "Real geographic coordinates affect visibility windows. Use actual ground station locations for realistic scenarios.",
                    "group": "Ground stations typically share the 'GS' group so any satellite can route to any station."
                }
            },
            "channels": {
                "title": "Communication Channels",
                "questions_per_channel": [
                    "Which two groups does this channel connect? (e.g. LEO ↔ GS)",
                    "Minimum elevation angle (for ground links)",
                    "Distance threshold (when is link considered too far?)",
                    "Data rate in Mbit/s",
                    "Packet loss percentage",
                    "Correlated (burst) losses"
                ],
                "link_types": {
                    "satellite_to_satellite (ISL)": {
                        "description": "Inter-Satellite Link — typically in the same orbital plane or cross-plane",
                        "typical_values": {
                            "min_elevation_angle": "0 (not applicable in space)",
                            "threshold": "2e12 m (~6700 km orbital altitude context)",
                            "data_rate": "10000-50000 Mbit/s (optical ISLs can be very high)",
                            "packet_loss": "0-1% (very reliable in vacuum)"
                        },
                        "reasoning": "ISLs don't have atmospheric effects, so packet loss is minimal. Data rate can be very high, especially for optical links."
                    },
                    "ground_to_satellite (downlink/uplink)": {
                        "description": "Ground-to-satellite link — affected by atmosphere, weather, and elevation",
                        "typical_values": {
                            "min_elevation_angle": "10-20° (below 10° signal is very degraded)",
                            "threshold": "2e12 m",
                            "data_rate": "100-1000 Mbit/s (Ka-band, Ku-band typical)",
                            "packet_loss": "1-10% (weather-dependent, higher at low elevation)"
                        },
                        "reasoning": "Atmospheric attenuation increases at low elevation angles (longer path through atmosphere). Rain fade can cause 5-15% packet loss in Ka-band. Suggest 15° minimum elevation for reliable comms."
                    },
                    "ground_to_ground": {
                        "description": "Ground-to-ground link — typically via satellite relay or simulated fiber",
                        "typical_values": {
                            "min_elevation_angle": "0 (not applicable)",
                            "threshold": "5e12 m (higher threshold for relay paths)",
                            "data_rate": "1000-10000 Mbit/s",
                            "packet_loss": "0-2% (fiber-like reliability if relayed)"
                        },
                        "reasoning": "Ground-to-ground channels represent end-to-end user traffic through the satellite network. Higher threshold because the path may involve multiple hops."
                    }
                },
                "channel_strategy": "Ask the user what types of links they need. Common pattern:\n1. One ISL channel per satellite pair (LEO ↔ LEO2)\n2. One downlink channel per orbital group to ground (LEO ↔ GS)\n3. One ground-to-ground if end-to-end relay is needed (GS ↔ GS)\nSuggest these based on how many satellites/ground stations the user defined."
            },
            "tle_file": {
                "title": "Orbital Data",
                "question": "What TLE file to use? (default: sample.tle)",
                "reasoning": "If using SGP4 propagator, the TLE file must contain entries matching satellite names or catalog numbers. Celestrak is a good source for real TLE data."
            },
            "docker": {
                "title": "Container Deployment (optional)",
                "question": "Should nodes run as Docker containers? If yes, a docker-compose.yml can be generated after config.toml creation.",
                "reasoning": "Containers are lighter than VMs and start in seconds. Each container needs NET_ADMIN capability for network emulation (VXLAN, VLAN, TC)."
            }
        },
        "tips": [
            "Don't ask all questions at once — group them logically",
            "Offer to use defaults for most parameters",
            "Suggest channel configurations based on the satellites and ground stations defined",
            "If the user is unsure about IPs, let the tool auto-assign them",
            "For testing/educational scenarios, TwoBody propagator is simpler than SGP4"
        ]
    }


# --- Tool 2: generate_config_toml ---

@mcp.tool()
async def generate_config_toml(
    satellites: List[SatelliteConfig],
    ground_stations: List[GroundStationConfig],
    channels: List[ChannelConfig],
    time_config: TimeConfig,
    tle_file: str = "sample.tle",
    network: str = "10.0.0.0/24",
    network_ext: str = "172.27.12.0/24",
    unicast_flooding: int = 0,
    output_path: str = "config.toml",
    overwrite: bool = False
) -> Dict[str, Any]:
    """
    Generate a VSNES config.toml file for satellite network emulation.
    
    The LLM should call get_config_guide first to understand what to ask the user,
    then use this tool with the collected parameters.
    
    Args:
        satellites: List of satellite configurations.
        ground_stations: List of ground station configurations.
        channels: List of communication channels between node groups.
        time_config: Time simulation parameters.
        tle_file: TLE orbit data filename.
        network: Internal emulation network subnet.
        network_ext: External Docker/VM network subnet.
        unicast_flooding: Enable/disable unicast flooding (0 or 1).
        output_path: Where to write the config.toml file (relative to SNES root).
        overwrite: Whether to overwrite if file exists.
    """
    full_path = os.path.join(SNES_DIR, output_path)
    
    if os.path.exists(full_path) and not overwrite:
        return {"status": "error", "message": f"File '{output_path}' already exists. Set overwrite=True to replace."}
    
    # Auto-assign IPs for external VMs if not provided
    ext_parts = network_ext.split('.')
    ext_base = f"{ext_parts[0]}.{ext_parts[1]}.{ext_parts[2]}"
    
    ip_counter = 101
    for sat in satellites:
        if not sat.ip_ext and sat.is_external_vm:
            sat.ip_ext = f"{ext_base}.{ip_counter}"
            ip_counter += 1
    
    for gs in ground_stations:
        if not gs.ip_ext and gs.is_external_vm:
            gs.ip_ext = f"{ext_base}.{ip_counter}"
            ip_counter += 1
    
    # Generate TOML content
    lines = []
    lines.append(f"network = '{network}'")
    lines.append(f"network_ext = '{network_ext}'")
    lines.append(f"unicast_flooding = {unicast_flooding}")
    
    # Time section
    lines.append("[Time]")
    lines.append(f"\tTimeInterval = {time_config.time_interval}\t\t#[min]")
    lines.append(f"\tContact_speed = {time_config.contact_speed}")
    lines.append(f"\tNon_contact_speed = {time_config.non_contact_speed}")
    lines.append(f"\tstart_datetime = '{time_config.start_datetime}'")
    lines.append(f"\tend_datetime = '{time_config.end_datetime}'")
    
    # Space Segment
    lines.append("[SpaceSegment]")
    lines.append(f"\tTLE = '{tle_file}'")
    
    for sat in satellites:
        lines.append("\t[[SpaceSegment.SatelliteSistem]]")
        lines.append(f"\t\tpropagator = '{sat.propagator}'\t\t#TwoBody or SGP4")
        lines.append(f"\t\tService = '{sat.service}'\t#Standard or Relay")
        lines.append(f"\t\tname = '{sat.name}' ")
        lines.append(f"\t\tgroup = '{sat.group}'")
        lines.append(f"\t\tOS = '{sat.os}'\t#ubuntu o alpines")
        lines.append(f"\t\tusername = '{sat.username}'")
        lines.append(f"\t\tpassword = '{sat.password}'")
        lines.append(f"\t\tis_external_vm = {sat.is_external_vm}")
        if sat.ip_ext:
            lines.append(f"\t\tip_ext = '{sat.ip_ext}'")
        lines.append(f"\t\tinterface = '{sat.interface}'")
        lines.append(f"\t\t[SpaceSegment.SatelliteSistem.clone_VM]")
        lines.append(f"\t\t\tname_VM = '{sat.name}' ")
    
    # Ground Segment
    lines.append("[GroundSegment]")
    
    for gs in ground_stations:
        lines.append("\t[[GroundSegment.GroundSistem]]")
        lines.append(f"\t\tname = '{gs.name}'")
        lines.append(f"\t\tgroup = '{gs.group}'")
        lines.append(f"\t\tlatitude = {gs.latitude}")
        lines.append(f"\t\tlongitude = {gs.longitude}")
        lines.append(f"\t\theight = {gs.height}")
        lines.append(f"\t\tOS = '{gs.os}' #ubuntu o alpine")
        lines.append(f"\t\tusername = '{gs.username}'")
        lines.append(f"\t\tpassword = '{gs.password}'")
        lines.append(f"\t\tis_external_vm = {gs.is_external_vm}")
        if gs.ip_ext:
            lines.append(f"\t\tip_ext = '{gs.ip_ext}'")
        lines.append(f"\t\tinterface = '{gs.interface}'")
        lines.append(f"\t\t[GroundSegment.GroundSistem.clone_VM]")
        lines.append(f"\t\t\tname_VM = '{gs.name}'")
    
    # Channels
    lines.append("[Channels]")
    
    for ch in channels:
        lines.append("\t[[Channels.Channel]]")
        lines.append(f"\t\tNode1 = '{ch.node1}' #Group name")
        lines.append(f"\t\tNode2 = '{ch.node2}'")
        lines.append(f"\t\tMin_elevation_angle = {ch.min_elevation_angle}\t\t#[deg]")
        lines.append(f"\t\tThreshold = {ch.threshold}\t\t\t#[m]")
        lines.append(f"\t\tData_rate =  {ch.data_rate}\t\t\t#[Mbit]")
        lines.append(f"\t\tPacket_loss = {ch.packet_loss}\t\t\t#[%]")
        lines.append(f"\t\tCorrelated_losses = {ch.correlated_losses}\t\t#[%] Emulate packet burst losses")
    
    toml_content = '\n'.join(lines) + '\n'
    
    # Write file
    try:
        with open(full_path, 'w') as f:
            f.write(toml_content)
    except Exception as e:
        return {"status": "error", "message": f"Failed to write file: {e}"}
    
    return {
        "status": "success",
        "message": f"config.toml written to {full_path}",
        "path": full_path,
        "content": toml_content,
        "summary": {
            "satellites": len(satellites),
            "ground_stations": len(ground_stations),
            "channels": len(channels),
            "external_vms": sum(1 for s in satellites if s.is_external_vm) + sum(1 for g in ground_stations if g.is_external_vm)
        }
    }


# --- Tool 3: generate_docker_compose ---

@mcp.tool()
async def generate_docker_compose(
    config_path: Optional[str] = None,
    services: Optional[List[DockerServiceConfig]] = None,
    network_subnet: str = "172.27.12.0/24",
    output_path: str = "docker-compose.yml",
    docker_dir: str = "docker",
    overwrite: bool = False,
    generate_dockerfile: bool = False
) -> Dict[str, Any]:
    """
    Generate docker-compose.yml for VSNES satellite network emulation nodes.
    Can read from an existing config.toml or accept explicit service definitions.
    
    Args:
        config_path: Path to config.toml to extract external VM nodes from. Overrides 'services'.
        services: Explicit list of Docker services (used if config_path is None).
        network_subnet: Subnet for the Docker network.
        output_path: Output path for docker-compose.yml.
        docker_dir: Directory containing Dockerfile (relative to SNES root).
        overwrite: Whether to overwrite existing file.
        generate_dockerfile: If True, also create Dockerfile and entrypoint.sh if they don't exist.
    """
    full_output = os.path.join(SNES_DIR, output_path)
    
    if os.path.exists(full_output) and not overwrite:
        return {"status": "error", "message": f"File '{output_path}' already exists. Set overwrite=True to replace."}
    
    # Collect services
    node_services = []
    
    if config_path:
        # Parse config.toml
        full_config = os.path.join(SNES_DIR, config_path)
        if not os.path.exists(full_config):
            return {"status": "error", "message": f"Config file not found: {config_path}"}
        
        try:
            with open(full_config, 'rb') as f:
                config = tomllib.load(f)
        except Exception as e:
            return {"status": "error", "message": f"Failed to parse TOML: {e}"}
        
        # Extract satellites
        for sat in config.get("SpaceSegment", {}).get("SatelliteSistem", []):
            if sat.get("is_external_vm", 0) == 1 and sat.get("ip_ext"):
                node_services.append({
                    "name": sat["name"],
                    "ip_address": sat["ip_ext"],
                    "os": sat.get("OS", "debian")
                })
        
        # Extract ground stations
        for gs in config.get("GroundSegment", {}).get("GroundSistem", []):
            if gs.get("is_external_vm", 0) == 1 and gs.get("ip_ext"):
                node_services.append({
                    "name": gs["name"],
                    "ip_address": gs["ip_ext"],
                    "os": gs.get("OS", "debian")
                })
    
    elif services:
        node_services = [{"name": s.name, "ip_address": s.ip_address, "os": s.os} for s in services]
    else:
        return {"status": "error", "message": "Either config_path or services must be provided."}
    
    if not node_services:
        return {"status": "error", "message": "No external VM nodes found to create containers for."}
    
    # Generate docker-compose.yml
    lines = ["services:"]
    service_names = []
    
    for node in node_services:
        safe_name = node["name"].replace(" ", "-").lower()
        service_names.append(node["name"])
        lines.append(f"  {safe_name}:")
        lines.append(f"    build: ./{docker_dir}")
        lines.append(f"    container_name: {node['name']}")
        lines.append(f"    hostname: {node['name']}")
        lines.append(f"    cap_add:")
        lines.append(f"      - NET_ADMIN")
        lines.append(f"      - SYS_ADMIN")
        lines.append(f"      - NET_RAW")
        lines.append(f"    sysctls:")
        lines.append(f"      - net.ipv4.ip_forward=1")
        lines.append(f"    networks:")
        lines.append(f"      vsnes:")
        lines.append(f"        ipv4_address: {node['ip_address']}")
        lines.append(f"    restart: unless-stopped")
        lines.append("")
    
    lines.append("networks:")
    lines.append("  vsnes:")
    lines.append("    name: vsnes_net")
    lines.append("    driver: bridge")
    lines.append("    ipam:")
    lines.append("      config:")
    lines.append(f"        - subnet: {network_subnet}")
    lines.append("")
    
    compose_content = '\n'.join(lines)
    
    # Write docker-compose.yml
    try:
        with open(full_output, 'w') as f:
            f.write(compose_content)
    except Exception as e:
        return {"status": "error", "message": f"Failed to write file: {e}"}
    
    result = {
        "status": "success",
        "message": f"docker-compose.yml written to {full_output}",
        "path": full_output,
        "content": compose_content,
        "services_created": service_names,
        "container_count": len(node_services)
    }
    
    # Optionally generate Dockerfile + entrypoint.sh
    if generate_dockerfile:
        docker_path = os.path.join(SNES_DIR, docker_dir)
        os.makedirs(docker_path, exist_ok=True)
        
        dockerfile_path = os.path.join(docker_path, "Dockerfile")
        entrypoint_path = os.path.join(docker_path, "entrypoint.sh")
        
        dockerfile_content = """FROM debian:12

RUN apt-get update && apt-get install -y --no-install-recommends \\
    openssh-server iproute2 iptables iputils-ping arp-scan net-tools sudo procps kmod \\
    && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /run/sshd
RUN useradd -m -s /bin/bash debian && echo 'debian:debian' | chpasswd && echo 'debian ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config && \\
    sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 22
ENTRYPOINT ["/entrypoint.sh"]
"""
        entrypoint_content = """#!/bin/bash
set -e
exec /usr/sbin/sshd -D
"""
        
        files_created = []
        
        if not os.path.exists(dockerfile_path):
            with open(dockerfile_path, 'w') as f:
                f.write(dockerfile_content)
            files_created.append(f"{docker_dir}/Dockerfile")
        
        if not os.path.exists(entrypoint_path):
            with open(entrypoint_path, 'w') as f:
                f.write(entrypoint_content)
            os.chmod(entrypoint_path, 0o755)
            files_created.append(f"{docker_dir}/entrypoint.sh")
        
        if files_created:
            result["dockerfiles_created"] = files_created
    
    return result

if __name__ == "__main__":
    logger.info("Starting Satellite & VM Manager MCP Server")
    mcp.run(transport="http", host="0.0.0.0", port=8560)
