#!/usr/bin/env python3
from flask import Flask, request, jsonify
import subprocess
from Class.Scenario import scenario
import threading
import toml
import logging
import os
from flask_cors import CORS

from Class.log_config import setup_logging
setup_logging()
# Per-request access lines (GET /api/status every ~300ms from the GUI) drown
# the console and snes.log; keep only warnings/errors from werkzeug.
logging.getLogger('werkzeug').setLevel(logging.WARNING)


app = Flask(__name__)
cors = CORS(app, resources={r"/api/*": {"origins": "*"}})

@app.errorhandler(Exception)
def handle_global_exception(e):
    logging.error(f"Unhandled API Exception: {e}", exc_info=True)
    return jsonify({'error': str(e), 'type': type(e).__name__}), 500

# Global state management
global_state = {
    'system_status': 'IDLE',
    'scenario': None,
    'config': None,
    'is_czml_generated': False,
    'cesium_process': None,
    'ntp_process': None,
    'emulation_process': None
}

def loadConfigFile(config_path):	
    """Load TOML configuration file"""
    try:
        with open(config_path, "r") as fo:
            TOML = toml.load(fo, _dict=dict)
        logging.info(f"Configuration file '{config_path}' loaded successfully")
        return TOML
    except FileNotFoundError:
        error_msg = f"The configuration file '{config_path}' does not exist. Create a file or check the name."
        logging.error(error_msg)
        return None
    except toml.decoder.TomlDecodeError as e:
        error_msg = f"Error in format of file {config_path}. Verify that the information has been entered following the TOML format. Error: {e}"
        logging.error(error_msg)
        return None
    except Exception as e:
        error_msg = f"Unexpected error loading configuration file: {e}"
        logging.error(error_msg)
        return None

def validateConfig(TOML):
    """Structural validation of the loaded TOML. Returns (ok, errors)."""
    from Class.Node import NODE_TYPES
    from Class.routing import PROTOCOLS
    errors = []
    if not isinstance(TOML, dict):
        return False, ['config is not a valid TOML mapping']
    if not TOML.get('network'):
        errors.append("missing 'network'")

    # [Routing] protocol must be a registered protocol or 'none' (absent
    # section is fine: scenario defaults to 'none' with a warning).
    rp = TOML.get('Routing', {}).get('protocol')
    if rp is not None and rp != 'none' and rp not in PROTOCOLS:
        errors.append(f"[Routing] invalid protocol '{rp}' "
                      f"(one of: none, {', '.join(sorted(PROTOCOLS))})")
    sats = TOML.get('SpaceSegment', {}).get('SatelliteSistem', [])
    gs = TOML.get('GroundSegment', {}).get('GroundSistem', [])
    if not sats and not gs:
        errors.append("no satellites or ground stations defined")
    if not TOML.get('Channels', {}).get('Channel'):
        errors.append("no Channels defined")

    # Per-node validation: single lifecycle `type` key + per-type required keys.
    for node in list(sats) + list(gs):
        name = node.get('name', '<unnamed>')
        if 'is_external_vm' in node or 'is_docker' in node:
            errors.append(f"node {name}: 'is_external_vm'/'is_docker' are obsolete — "
                          f"use type = one of {NODE_TYPES}")
        ntype = node.get('type')
        if ntype is None:
            errors.append(f"node {name}: missing 'type' (one of {NODE_TYPES})")
            continue
        if ntype not in NODE_TYPES:
            errors.append(f"node {name}: invalid type '{ntype}' (one of {NODE_TYPES})")
            continue
        if ntype != 'vm' and not node.get('ip_ext'):
            errors.append(f"node {name}: 'ip_ext' required for type '{ntype}'")
        if ntype == 'vm' and not node.get('clone_VM', {}).get('name_VM'):
            errors.append(f"node {name}: clone_VM.name_VM required for type 'vm'")

    return (len(errors) == 0), errors

def InitScenario(TOML):
    """Initialize scenario from TOML configuration"""
    try:
        Scenario_instance = scenario(TOML)
        logging.info("Scenario created successfully")
        return Scenario_instance
    except (KeyError, ValueError, Exception) as e:
        error_msg = f"Error creating scenario: {e}"
        logging.error(error_msg)
        return None

def writeCZML(scn):
    """Write CZML file for scenario"""
    try:
        scn.write_czml()
        return True
    except Exception as e:
        logging.error(f"Error writing CZML: {e}")
        return False

def StartVMSimulation(scn):
    """Start VMs for simulation"""
    try:
        return scn.start_scenario_VM()
    except Exception as e:
        logging.error(f"Error starting VM simulation: {e}")
        return False

def startSimulation(scn, isCZML, isEMU, password=None):
    """Start simulation with specified parameters"""
    try:
        if not(isCZML):
            writeCZML(scn)
            global_state['is_czml_generated'] = True
            
        scn.start_scenario(isEMU, password=password)
        return True
    except Exception as e:
        logging.error(f"Error starting simulation: {e}")
        return False

def stopSimulation(scn, password=None):
    """Stop the running simulation"""
    try:
        scn.stop_simulation(password=password)
        return True
    except Exception as e:
        logging.error(f"Error stopping simulation: {e}")
        return False
    
def deleteVMbyName(scenario, name):
    """Delete specific VM by name"""
    try:
        for n in range(0, scenario.get_number_of_nodes()):
            if name == scenario._node_list[n].name:
                scenario._node_list[n].delete_VM()
                return True
        return False
    except Exception as e:
        logging.error(f"Error deleting VM {name}: {e}")
        return False
    
def stopVMbyName(scenario, name):
    """Stop specific VM by name"""
    try:
        for n in range(0, scenario.get_number_of_nodes()):
            if name == scenario._node_list[n].name:
                scenario._node_list[n].stop_VM()
                return True
        return False
    except Exception as e:
        logging.error(f"Error stopping VM {name}: {e}")
        return False
    
def stopAllVMs(scenario):
    """Stop all VMs"""
    try:
        for n in range(0, scenario.get_number_of_nodes()):
            scenario._node_list[n].stop_VM()
        return True
    except Exception as e:
        logging.error(f"Error stopping all VMs: {e}")
        return False

def deleteAllVMs(scenario):
    """Delete all VMs"""
    try:
        for n in range(0, scenario.get_number_of_nodes()):
            scenario._node_list[n].delete_VM()
        return True
    except Exception as e:
        logging.error(f"Error deleting all VMs: {e}")
        return False

def compose_error_lines(output):
    """Pull the real failure lines out of docker compose output.

    Compose writes its per-container progress ('Container X  Creating') to
    stderr, so a failed run buries the one line that matters — typically a
    name conflict with a container left over from an earlier project — under
    dozens of 'Creating'/'Created' lines. Returns the offending lines, or the
    tail of the output if nothing matches the known error shapes.
    """
    hits = [ln.strip() for ln in (output or '').splitlines()
            if ('Error' in ln or 'error' in ln
                or 'no such service' in ln or 'Conflict' in ln)]
    return hits or [ln.strip() for ln in (output or '').splitlines()[-5:] if ln.strip()]


def run_docker_compose(action, services=None):
    """Run docker compose up -d / down for the node containers.
    Returns (result_dict, http_status).

    `up` is scoped to the LOADED SCENARIO: it never recreates running
    containers (--no-recreate, a live k3s cluster must survive) and never
    starts services outside the scenario's node set (+ registry). A caller-
    supplied services list is validated against that set."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    compose_file = os.path.join(base_dir, 'docker-compose.yml')
    if not os.path.exists(compose_file):
        return {'error': f'docker-compose.yml not found in {base_dir}'}, 500

    if action == 'up':
        scn = global_state.get('scenario')
        if scn is None:
            return {'error': 'No scenario loaded. Use /api/load-config first — '
                             'compose up is scoped to the scenario\'s nodes'}, 400
        allowed = set(scn.compose_service_names()) | {'registry'}
        if services:
            bad = [s for s in services if s not in allowed]
            if bad:
                return {'error': f'services not in the loaded scenario: {bad}',
                        'allowed': sorted(allowed)}, 400
            targets = list(services)
        else:
            targets = sorted(allowed)
        cmd = ['docker', 'compose', 'up', '-d', '--no-recreate', '--no-build'] + targets
    else:
        cmd = ['docker', 'compose', 'down']

    logging.info(f"Running: {' '.join(cmd)}")
    try:
        # 600s: first `up` may need to build the node image (k3s download etc.)
        proc = subprocess.run(cmd, cwd=base_dir, capture_output=True, text=True, timeout=600)
    except FileNotFoundError:
        return {'error': 'docker not found — is Docker installed and in PATH?'}, 500
    except subprocess.TimeoutExpired:
        return {'error': f'docker compose {action} timed out after 600s'}, 504

    output = (proc.stdout + proc.stderr).strip()
    if proc.returncode != 0:
        causes = compose_error_lines(output)
        logging.error(f"docker compose {action} failed (exit {proc.returncode}): "
                      + " | ".join(causes))
        return {'error': f'docker compose {action} failed (exit {proc.returncode})',
                'causes': causes,
                'output': output.splitlines()}, 500

    result = {'message': f'docker compose {action} completed successfully',
              'output': output.splitlines()}
    if action == 'up':
        ps = subprocess.run(['docker', 'compose', 'ps', '--format', '{{.Name}}\t{{.Status}}'],
                            cwd=base_dir, capture_output=True, text=True)
        result['containers'] = ps.stdout.strip().splitlines() if ps.stdout.strip() else []
    return result, 200


# API Routes
@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'Satellite Network Emulator API',
        'scenario_loaded': global_state['scenario'] is not None
    })

@app.route('/api/upload-config', methods=['POST'])
def upload_config():
    """Upload configuration file"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    try:
        file.save('config.toml')
        return jsonify({'message': 'Configuration file uploaded successfully as config.toml'})
    except Exception as e:
        logging.error(f"Error saving uploaded file: {e}")
        return jsonify({'error': 'Failed to save the uploaded file'}), 500

@app.route('/api/upload-tle', methods=['POST'])
def upload_tle():
    """Upload TLE file"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    try:
        file.save('sample.tle')
        return jsonify({'message': 'TLE file uploaded successfully as sample.tle'})
    except Exception as e:
        logging.error(f"Error saving uploaded file: {e}")
        return jsonify({'error': 'Failed to save the uploaded file'}), 500

@app.route('/api/load-config', methods=['POST'])
def load_config():
    """Stage 1 (load): load config.toml, validate it, and create the scenario
    nodes. Does NOT start any VM/container. Optional JSON body:
      {"isCzml": bool (default true), "isDockercompose": bool (default false)}
    """
    config_path = 'config.toml'
    logging.info(f"Loading: {config_path}")
    TOML = loadConfigFile(config_path)
    if TOML is None:
        return jsonify({'error': 'Failed to load configuration file'}), 400

    ok, errors = validateConfig(TOML)
    if not ok:
        return jsonify({'error': 'Invalid configuration', 'details': errors}), 400

    # Create the nodes (moved here from init-scenario).
    Scenario_instance = InitScenario(TOML)
    if Scenario_instance is None:
        return jsonify({'error': 'Failed to create scenario nodes'}), 400

    data = request.get_json(silent=True) or {}
    isCzml = data.get('isCzml', True)
    isDockercompose = data.get('isDockercompose', False)
    if isCzml:
        writeCZML(Scenario_instance)
        global_state['is_czml_generated'] = True
    if isDockercompose:
        Scenario_instance.generate_docker_compose()  # stub

    global_state['config'] = TOML
    global_state['scenario'] = Scenario_instance
    global_state['system_status'] = 'CONFIG_LOADED'
    logging.info(f"Configuration loaded and nodes created: {config_path}")

    return jsonify({
        'message': f"Configuration loaded and {Scenario_instance.get_number_of_nodes()} nodes created",
        'isCzml': isCzml,
        'isDockercompose': isDockercompose,
        'config_summary': {
            'network': TOML.get('network'),
            'satellites': len(TOML.get('SpaceSegment', {}).get('SatelliteSistem', [])),
            'ground_stations': len(TOML.get('GroundSegment', {}).get('GroundSistem', [])),
            'channels': len(TOML.get('Channels', {}).get('Channel', []))
        }
    })

@app.route('/api/init-scenario', methods=['POST'])
def init_scenario():
    """Stage 2 (init/prepare): start/configure the nodes, install routing rules,
    and apply the channel shaping — leaving the scenario ready to run. Runs in
    the background; start checks readiness. Optional JSON body:
      {"isVM": bool (default true), "password": str} — routing protocol comes from the toml [Routing] section
    isVM=false skips ALL node/network config (contacts/timing only).
    """
    scn = global_state['scenario']
    if scn is None:
        return jsonify({'error': 'No scenario. Use /api/load-config first'}), 400
    if global_state.get('system_status') in ['PREPARING_VMS', 'RUNNING_SIMULATION']:
        return jsonify({'error': f"Conflict: System is currently {global_state['system_status']}."}), 409

    data = request.get_json(silent=True) or {}
    isVM = data.get('isVM', True)
    if 'isOlsr' in data:
        logging.warning("init-scenario: 'isOlsr' is deprecated and ignored — "
                        "the routing protocol comes from the toml [Routing] section")
    password = data.get('password')

    global_state['system_status'] = 'PREPARING_VMS'
    scn._prepared = False
    scn._prepare_error = None

    def _prep():
        # Whatever happens, leave PREPARING_VMS: it is the state that makes
        # init/start return 409, so staying in it after the thread is gone
        # locks the API out until a server restart. 'is_prepared' (not the
        # status) is what distinguishes success from failure.
        try:
            scn.prepare_scenario(isVM=isVM, password=password)
            scn._prepared = True
            logging.info("prepare_scenario finished — scenario ready to run")
        except Exception as e:
            logging.error(f"prepare_scenario failed: {e}")
            scn._prepared = False
            scn._prepare_error = str(e)
        finally:
            global_state['system_status'] = 'SCENARIO_INIT'

    t = threading.Thread(target=_prep, daemon=True)
    t.start()
    scn._prepare_thread = t
    logging.info(f"Scenario preparation started (isVM={isVM}, "
                 f"routing={scn._routing_protocol})")

    return jsonify({
        'message': 'Scenario preparation started',
        'isVM': isVM,
        'routing_protocol': scn._routing_protocol,
        'scenario_info': {
            'number_of_nodes': scn.get_number_of_nodes()
        }
    })

@app.route('/api/scenario', methods=['GET'])
def get_scenario():
    """Get current scenario description"""
    if global_state['scenario'] is None:
        return jsonify({'error': 'No scenario initialized'}), 400
    
    return jsonify({
        'description': global_state['scenario'].scenario_description(),
        'number_of_nodes': global_state['scenario'].get_number_of_nodes(),
        'is_czml_generated': global_state['is_czml_generated']
    })

@app.route('/api/write-czml', methods=['POST'])
def write_czml():
    """Generate CZML file for current scenario"""
    if global_state['scenario'] is None:
        return jsonify({'error': 'No scenario initialized'}), 400
    
    if writeCZML(global_state['scenario']):
        global_state['is_czml_generated'] = True
        return jsonify({'message': 'CZML file generated successfully'})
    else:
        return jsonify({'error': 'Failed to generate CZML file'}), 500

@app.route('/api/start-vms', methods=['POST'])
def start_vms():
    """Start all VMs for the scenario"""
    if global_state['scenario'] is None:
        return jsonify({'error': 'No scenario initialized'}), 400
    
    if global_state.get('system_status') in ['PREPARING_VMS', 'RUNNING_SIMULATION']:
        return jsonify({'error': f"Conflict: System is currently {global_state['system_status']}."}), 409
        
    global_state['system_status'] = 'PREPARING_VMS'
    try:
        global_state['scenario'].start_VMs()
        return jsonify({'message': 'VMs started successfully'})
    except Exception as e:
        global_state['system_status'] = 'SCENARIO_INIT' # rollback status
        return jsonify({'error': f'Failed to start VMs: {str(e)}'}), 500

@app.route('/api/delete-vm/<vm_name>', methods=['DELETE'])
def delete_vm(vm_name):
    """Delete a specific VM by name"""
    if global_state['scenario'] is None:
        return jsonify({'error': 'No scenario initialized'}), 400
    
    if deleteVMbyName(global_state['scenario'], vm_name):
        return jsonify({'message': f'VM {vm_name} deleted successfully'})
    else:
        return jsonify({'error': f'VM {vm_name} not found or deletion failed'}), 404
    
@app.route('/api/stop-vm/<vm_name>', methods=['POST'])
def stop_vm(vm_name):
    """Stop a specific VM by name"""
    if global_state['scenario'] is None:
        return jsonify({'error': 'No scenario initialized'}), 400
    
    if stopVMbyName(global_state['scenario'], vm_name):
        return jsonify({'message': f'VM {vm_name} stopped successfully'})
    else:
        return jsonify({'error': f'VM {vm_name} not found or stopping failed'}), 404
    
@app.route('/api/delete-all-vms', methods=['DELETE'])
def delete_all_vms():
    """Delete all VMs"""
    if global_state['scenario'] is None:
        return jsonify({'error': 'No scenario initialized'}), 400
    
    if deleteAllVMs(global_state['scenario']):
        return jsonify({'message': 'All VMs deleted successfully'})
    else:
        return jsonify({'error': 'Failed to delete VMs'}), 500

@app.route('/api/stop-all-vms', methods=['POST'])
def stop_all_vms():
    """Stop all VMs"""
    if global_state['scenario'] is None:
        return jsonify({'error': 'No scenario initialized'}), 400
    
    if stopAllVMs(global_state['scenario']):
        return jsonify({'message': 'All VMs stopped successfully'})
    else:
        return jsonify({'error': 'Failed to stop VMs'}), 500


def _set_node_killed(node_name, killed):
    """Force-remove (or restore) a node in the live channel matrix. Returns
    (payload, http_code)."""
    scenario = global_state['scenario']
    if scenario is None:
        return {'error': 'No scenario initialized'}, 400
    channel = getattr(scenario, '_channel', None)
    if channel is None:
        return {'error': 'Scenario has no channel matrix'}, 400
    names = {n.name for n in getattr(scenario, '_node_list', [])}
    if node_name not in names:
        return {'error': f'Node {node_name} not found'}, 404
    if killed:
        channel.kill_node(node_name)
    else:
        channel.revive_node(node_name)
    return {
        'message': f"Node {node_name} {'killed' if killed else 'revived'}",
        'node': node_name,
        'killed': killed,
        'killed_nodes': sorted(channel._killed),
    }, 200


@app.route('/api/node/<node_name>/kill', methods=['POST'])
def kill_node(node_name):
    """Logically remove a node from the matrix: all its links go to 100% loss
    on the next tick, every other pair keeps working. Reversible via revive."""
    result, code = _set_node_killed(node_name, True)
    return jsonify(result), code


@app.route('/api/node/<node_name>/revive', methods=['POST'])
def revive_node(node_name):
    """Undo a kill: the node's real link delays resume on the next tick."""
    result, code = _set_node_killed(node_name, False)
    return jsonify(result), code


@app.route('/api/compose/up', methods=['POST'])
def compose_up():
    """Start the Docker node containers (docker compose up -d).
    Optional JSON body: {"services": ["satellite-1", "ibi_es", ...]}"""
    data = request.get_json(silent=True) or {}
    services = data.get('services') or []
    if not isinstance(services, list) or not all(isinstance(s, str) for s in services):
        return jsonify({'error': "'services' must be a list of service names"}), 400
    result, code = run_docker_compose('up', services)
    return jsonify(result), code

@app.route('/api/compose/down', methods=['POST'])
def compose_down():
    """Stop and remove the Docker node containers (docker compose down)."""
    result, code = run_docker_compose('down')
    return jsonify(result), code


@app.route('/api/compose/generate', methods=['POST'])
def compose_generate():
    """Generate docker-compose.yml from the loaded scenario (one service per
    type='container' node + registry). The single source of truth for compose
    generation — the MCP tool delegates here."""
    scn = global_state.get('scenario')
    if scn is None:
        return jsonify({'error': 'No scenario loaded. Use /api/load-config first'}), 400
    if not scn.generate_docker_compose():
        return jsonify({'error': 'compose generation failed (no container nodes?)'}), 500
    return jsonify({'message': 'docker-compose.yml generated',
                    'services': scn.compose_service_names() + ['registry']})


@app.route('/api/visualization/start', methods=['POST'])
def start_visualization():
    """Start Cesium visualization only"""
    if global_state['scenario'] is None:
        return jsonify({'error': 'No scenario initialized'}), 400
    
    data = request.get_json(silent=True) or {}
    generate_czml = data.get('generate_czml', not global_state['is_czml_generated'])
    password = data.get('password')
    
    if startSimulation(global_state['scenario'], not generate_czml, False, password=password):
        if generate_czml:
            global_state['is_czml_generated'] = True
        return jsonify({'message': 'Visualization started successfully'})
    else:
        return jsonify({'error': 'Failed to start visualization'}), 500

@app.route('/api/simulation/start', methods=['POST'])
def start_simulation():
    """Stage 3 (start): start ONLY the simulation clock. Preparation (init) must
    be finished — if it is still running, returns a waiting message. The saved
    isVM decides whether per-tick network updates apply; positions/timing always
    advance. Also restarts the clock after a natural end (status
    SIMULATION_ENDED): the rules are still applied, so it just replays from the
    reset marker — no re-prepare needed. Optional JSON body to override the saved
    values:
      {"isVM": bool, "password": str}
    """
    scn = global_state['scenario']
    if scn is None:
        return jsonify({'error': 'No scenario initialized'}), 400
    if global_state.get('system_status') == 'RUNNING_SIMULATION':
        return jsonify({'error': 'Simulation is already running'}), 409

    # Readiness: prepare (init) must have run and finished.
    prep_t = getattr(scn, '_prepare_thread', None)
    if prep_t is None:
        return jsonify({'error': 'Scenario not prepared. Use /api/init-scenario first'}), 412
    if prep_t.is_alive():
        return jsonify({'message': 'Scenario is still preparing, please wait...'}), 202
    if not getattr(scn, '_prepared', False):
        return jsonify({'error': 'Scenario preparation failed — check logs'}), 500

    data = request.get_json(silent=True) or {}
    isVM = data.get('isVM')          # None -> use the value saved at init
    password = data.get('password')  # None -> use the value saved at init

    try:
        scn.start_clock(isVM=isVM, password=password)
    except Exception as e:
        logging.error(f"start_clock failed: {e}")
        return jsonify({'error': f'Failed to start simulation clock: {e}'}), 500

    global_state['system_status'] = 'RUNNING_SIMULATION'
    emu_proc = getattr(scn, '_emulator_process', None)
    if emu_proc is not None and not emu_proc.is_alive():
        # The scenario is still prepared — only the clock failed. Rolling back
        # to PREPARING_VMS would 409 every later init/start attempt.
        global_state['system_status'] = 'SCENARIO_INIT'
        return jsonify({'error': 'Clock thread failed to start'}), 500
    return jsonify({'message': 'Simulation clock started', 'isVM': getattr(scn, '_isVM', True)})

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get current system status"""
    status = {
        'system_status': global_state.get('system_status', 'IDLE'),
        'scenario_loaded': global_state['scenario'] is not None,
        'config_loaded': global_state['config'] is not None,
        'is_czml_generated': global_state['is_czml_generated'],
        'cesium_running': global_state['cesium_process'] is not None,
        'is_preparing': bool(global_state['scenario'] is not None
                             and getattr(global_state['scenario'], '_prepare_thread', None) is not None
                             and global_state['scenario']._prepare_thread.is_alive()),
        'is_prepared': bool(global_state['scenario'] is not None
                            and getattr(global_state['scenario'], '_prepared', False)),
        # Back-compat alias (was: existence of the old VM startup thread).
        'is_creating_VM': bool(global_state['scenario'] is not None
                               and getattr(global_state['scenario'], '_prepare_thread', None) is not None
                               and global_state['scenario']._prepare_thread.is_alive()),
        # Why the last preparation failed (None if it succeeded or never ran).
        # Without this a failed prepare is indistinguishable from one that
        # simply hasn't finished: both just show "not prepared".
        'prepare_error': getattr(global_state['scenario'], '_prepare_error', None)
                         if global_state['scenario'] is not None else None
    }
    
    if global_state['scenario']:
        scn = global_state['scenario']
        status['number_of_nodes'] = scn.get_number_of_nodes()
        # Live speed telemetry: configured multiplier vs the one the clock
        # loop is actually sustaining (EMA over real tick periods), plus how
        # many ticks overran their budget. Lets a degrading run be caught in
        # its first minutes instead of after the campaign.
        try:
            status['configured_speed'] = scn.get_speed()
        except Exception:
            status['configured_speed'] = None
        status['achieved_multiplier'] = getattr(scn, '_achieved_multiplier', None)
        status['tick_overruns'] = getattr(scn, '_overrun_count', None)
        # Read simulation_time from file (child process can't share memory)
        sim_time_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "simulation_time.txt")
        if os.path.exists(sim_time_file):
            try:
                with open(sim_time_file, "r") as f:
                    status['simulation_time'] = f.read().strip()
            except Exception:
                status['simulation_time'] = None
        else:
            if hasattr(global_state['scenario'], '_time_parameters') and global_state['scenario']._time_parameters:
                tp = global_state['scenario']._time_parameters
                status['simulation_time'] = tp.get_date_time().isoformat() if hasattr(tp, 'get_date_time') else None

        # Check if emulator process is still alive
        emu_proc = getattr(global_state['scenario'], '_emulator_process', None)
        if emu_proc is not None and not emu_proc.is_alive():
            # Thread dead: distinguish a natural end (timeline finished, marker
            # reset to zero, tc/OLSR rules STILL applied) from a fresh/stopped
            # scenario. SIMULATION_ENDED means "rules still live — run to restart
            # the clock, or stop to remove them".
            ended = getattr(global_state['scenario'], '_ended', False)
            new_status = 'SIMULATION_ENDED' if ended else 'SCENARIO_INIT'
            global_state['system_status'] = new_status
            status['system_status'] = new_status
        else:
            status['system_status'] = global_state.get('system_status', 'IDLE')
    
    return jsonify(status)

@app.route('/api/simulation/stop', methods=['POST'])
def stop_simulation_endpoint():
    """Stop the running simulation without full reset"""
    if global_state['scenario'] is None:
        return jsonify({'error': 'No simulation is running'}), 400

    data = request.get_json(silent=True) or {}
    password = data.get('password')

    if stopSimulation(global_state['scenario'], password=password):
        global_state['system_status'] = 'SCENARIO_INIT'
        return jsonify({'message': 'Simulation stopped successfully'})
    else:
        return jsonify({'error': 'Failed to stop simulation'}), 500

@app.route('/api/reset', methods=['POST'])
def reset_state():
    """Reset the API state — stops simulation if running, then clears all state"""
    
    data = request.get_json(silent=True) or {}
    password = data.get('password')

    # Gracefully stop simulation only if one is active
    if global_state['scenario'] is not None:
        if not stopSimulation(global_state['scenario'], password=password):
            logging.warning("stop_simulation() returned False during reset — continuing anyway")

    # Stop running processes
    if global_state['cesium_process']:
        global_state['cesium_process'].terminate()
    if global_state['emulation_process']:
        global_state['emulation_process'].terminate()
    if global_state['ntp_process']:
        global_state['ntp_process'].terminate()

    # Reset state
    global_state['system_status'] = 'IDLE'
    global_state['scenario'] = None
    global_state['config'] = None
    global_state['is_czml_generated'] = False
    global_state['cesium_process'] = None
    global_state['emulation_process'] = None
    global_state['ntp_process'] = None

    return jsonify({'message': 'API state reset successfully'})



@app.route('/api/help', methods=['GET'])
def api_help():
    """Get API documentation"""
    help_text = {
        'endpoints': {
            'GET /api/health': 'Health check',
            'POST /api/upload-config': 'Upload configuration TOML file',
            'POST /api/upload-tle': 'Upload TLE file',
            'POST /api/load-config': 'Load configuration file from uploaded TOML',
            'POST /api/init-scenario': 'Initialize scenario from loaded config',
            'GET /api/scenario': 'Get current scenario description',
            'POST /api/start-cesium': 'Start Cesium visualization server',
            'POST /api/write-czml': 'Generate CZML file',
            'POST /api/start-vms': 'Start all VMs',
            'DELETE /api/delete-vm/<name>': 'Delete specific VM',
            'DELETE /api/delete-all-vms': 'Delete all VMs',
            'POST /api/stop-vm/<name>': 'Stop specific VM',
            'POST /api/stop-all-vms': 'Stop all VMs',
            'POST /api/node/<name>/kill': 'Remove a node from the matrix (its links -> 100% loss)',
            'POST /api/node/<name>/revive': 'Restore a killed node',
            'POST /api/compose/up': 'Start Docker node containers (optional JSON {"services": [...]})',
            'POST /api/compose/down': 'Stop and remove Docker node containers',
            'POST /api/simulation/start': 'Start emulation and visualization',
            'POST /api/visualization/start': 'Start visualization only',
            'GET /api/status': 'Get current system status',
            'POST /api/reset': 'Stop and reset API state',
            'GET /api/help': 'This help message'
        }
    }
    return jsonify(help_text)

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == "__main__":
    logging.info("Starting Satellite Network Emulator API")
    print("API Available at: http://localhost:5050")
    print("API documentation: http://localhost:5050/api/help")
    
    app.run(host='0.0.0.0', port=5050, debug=True, use_reloader=False)
