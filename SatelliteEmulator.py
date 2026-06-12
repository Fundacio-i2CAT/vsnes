#!/usr/bin/env python3
"""
VSNES CLI Launcher — Single orchestrator for all VSNES services.

Starts and manages:
  - API server (always)
  - Cesium web server (--web)
  - NTP server (--ntp)
  - MCP server (--mcp)
  - All services (--all)

Usage:
  python3 SatelliteEmulator.py              # API only (default)
  python3 SatelliteEmulator.py --all        # API + Web + NTP + MCP
  python3 SatelliteEmulator.py --web        # API + Web
  python3 SatelliteEmulator.py --mcp --ntp  # API + MCP + NTP
"""

import subprocess
import sys
import os
import signal
import time
import threading
import requests
import argparse
import re

_ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')

# ---------------------------------------------------------------------------
# Sticky-prompt + pinned sim-block helpers
# ---------------------------------------------------------------------------

_prompt_lock   = threading.Lock()
_current_prompt = ""
_sim_block      = []   # lines currently pinned at the bottom

def _redraw_sim_and_prompt():
    """Reprint the pinned block + prompt. Must be called with _prompt_lock held."""
    for bl in _sim_block:
        sys.stdout.write(f"{bl}\n")
    if _current_prompt:
        sys.stdout.write(_current_prompt)
    sys.stdout.flush()

def _erase_sim_and_prompt():
    """Erase prompt line + all pinned block lines. Must be called with _prompt_lock held."""
    sys.stdout.write('\r\x1b[2K')
    for _ in range(len(_sim_block)):
        sys.stdout.write('\x1b[1A\x1b[2K')

def _log_print(line):
    """Print a log line. Clears the prompt and lets the sim block re-pin on next refresh."""
    global _sim_block
    with _prompt_lock:
        sys.stdout.write('\r\x1b[2K')
        sys.stdout.write(f"{line}\n")
        _sim_block = []          # block scrolled away — will re-pin on next [SIM] refresh
        if _current_prompt:
            sys.stdout.write(_current_prompt)
        sys.stdout.flush()

def _sim_refresh(new_block):
    """Replace the entire pinned block (called on each new timestamp)."""
    global _sim_block
    with _prompt_lock:
        _erase_sim_and_prompt()
        _sim_block = list(new_block)
        _redraw_sim_and_prompt()

def _sim_append(line):
    """Add one line to the pinned block (called for each channel line)."""
    global _sim_block
    with _prompt_lock:
        sys.stdout.write('\r\x1b[2K')   # clear prompt only
        sys.stdout.write(f"{line}\n")
        _sim_block.append(line)
        if _current_prompt:
            sys.stdout.write(_current_prompt)
        sys.stdout.flush()

def _sim_clear():
    """Remove the pinned block entirely."""
    global _sim_block
    with _prompt_lock:
        _erase_sim_and_prompt()
        _sim_block = []
        if _current_prompt:
            sys.stdout.write(_current_prompt)
        sys.stdout.flush()

def _input(prompt=""):
    """input() wrapper that registers the prompt so background logs can reprint it."""
    global _current_prompt
    with _prompt_lock:
        _current_prompt = prompt
        sys.stdout.write(prompt)
        sys.stdout.flush()
    try:
        result = sys.stdin.readline()
        return result.rstrip("\n")
    finally:
        with _prompt_lock:
            _current_prompt = ""

SNES_DIR = os.path.dirname(os.path.abspath(__file__))
API_URL = "http://localhost:5050"
PYTHON = sys.executable

# ---------------------------------------------------------------------------
# Process manager
# ---------------------------------------------------------------------------

processes = {}  # name -> subprocess.Popen

def start_process(name, command, cwd=None):
    """Start a subprocess and track it."""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    try:
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=cwd or SNES_DIR,
            env=env,
            preexec_fn=os.setsid if os.name != 'nt' else None
        )
        processes[name] = proc
        return proc
    except Exception as e:
        print(f"  ✗ Failed to start {name}: {e}")
        return None


_SIM_PREFIX = '[SIM]'
_SIM_CLEAR  = '[SIM_CLEAR]'

def stream_output(proc, prefix):
    """Continuously print subprocess stdout to console."""
    pending_block = []
    try:
        for line in iter(proc.stdout.readline, ''):
            if not line:
                continue
            stripped = _ANSI_ESCAPE.sub('', line).strip()
            if not stripped:
                continue
            if any(skip in stripped for skip in [
                'Detected change', 'Restarting with stat',
                'Debugger PIN', 'Press CTRL+C to quit',
                'development server',
                'GET /api/status', 'OPTIONS /api/status',   # GUI poll spam
                'GET /ScenarioCZML.czml', 'GET /satsPosition'
            ]):
                continue

            if stripped == _SIM_CLEAR:
                pending_block = []
                _sim_clear()
            elif stripped.startswith(_SIM_PREFIX):
                content = stripped[len(_SIM_PREFIX):]
                formatted = f"  [SIM] {content}"
                # Timestamp = start of a new block → refresh whole block
                if ',' in content and ':' in content and len(content) < 25:
                    pending_block = [formatted]
                    _sim_refresh(pending_block)
                else:
                    pending_block.append(formatted)
                    _sim_append(formatted)
            else:
                _log_print(f"  [{prefix}] {stripped}")
    except Exception:
        pass


def start_streamer(proc, prefix):
    """Start a daemon thread to stream a process output."""
    t = threading.Thread(target=stream_output, args=(proc, prefix), daemon=True)
    t.start()
    return t


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def cleanup():
    """Kill all managed processes."""
    print("\n  Cleaning up processes...")
    for name, proc in processes.items():
        try:
            if os.name != 'nt':
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            else:
                proc.terminate()
            print(f"  · {name} terminated")
        except:
            pass

    time.sleep(2)

    for pattern in [
        'apiServer.py',
        'Class/Server.py',
        'ntpserver.py',
        'mcpServer.py'
    ]:
        try:
            result = subprocess.run(
                f"pgrep -f '{pattern}'",
                shell=True, capture_output=True, text=True
            )
            for pid in result.stdout.strip().split('\n'):
                if pid.strip():
                    try:
                        os.kill(int(pid.strip()), signal.SIGKILL)
                    except:
                        pass
        except:
            pass

    time.sleep(1)
    remaining = 0
    for pattern in ['apiServer.py', 'Class/Server.py', 'ntpserver.py', 'mcpServer.py']:
        try:
            result = subprocess.run(f"pgrep -f '{pattern}'", shell=True, capture_output=True, text=True)
            remaining += len([p for p in result.stdout.strip().split('\n') if p.strip()])
        except:
            pass
    if remaining == 0:
        print("  ✓ All processes stopped cleanly")
    else:
        print(f"  ⚠ {remaining} processes may still be running")


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def wait_for_api(max_wait=30):
    """Wait until the API server responds."""
    print("  Waiting for API server...", end="", flush=True)
    for _ in range(max_wait):
        try:
            r = requests.get(f"{API_URL}/api/health", timeout=2)
            if r.status_code == 200:
                print(" Ready!")
                return True
        except:
            pass
        print(".", end="", flush=True)
        time.sleep(1)
    print(" FAILED")
    return False


def api_call(method, endpoint, json_data=None, timeout=300):
    """Make an API call, return (result_dict, success_bool)."""
    try:
        url = f"{API_URL}{endpoint}"
        r = requests.request(method, url, json=json_data, timeout=timeout)
        result = r.json()
        if r.status_code == 200:
            return result, True
        else:
            print(f"  ✗ {result.get('error', 'Failed')}")
            return result, False
    except requests.exceptions.ConnectionError:
        print("  ✗ API server is not responding")
        return None, False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return None, False


def api_upload(file_type, path=None):
    """Upload config or TLE file via multipart."""
    if file_type == "config":
        endpoint = "/api/upload-config"
        default = "config.toml"
    else:
        endpoint = "/api/upload-tle"
        default = "sample.tle"

    if path is None:
        path = os.path.join(SNES_DIR, default)

    if not os.path.exists(path):
        print(f"  ✗ File not found: {path}")
        return False

    try:
        with open(path, 'rb') as f:
            files = {'file': f}
            r = requests.post(f"{API_URL}{endpoint}", files=files, timeout=10)
            return r.status_code == 200
    except:
        return False


# ---------------------------------------------------------------------------
# Docker compose helper
# ---------------------------------------------------------------------------

def docker_compose(action, services=None):
    """Start/stop the node containers through the API server (POST /api/compose/*)."""
    endpoint = "/api/compose/up" if action == "up" else "/api/compose/down"
    payload = {"services": services} if (action == "up" and services) else None
    print(f"  Requesting docker compose {action} via API...")
    # 620s: the server runs compose with a 600s limit (first up may build the image)
    result, ok = api_call("POST", endpoint, json_data=payload, timeout=620)
    if result:
        for line in result.get('output', []):
            print(f"  {line}")
    if not ok:
        return False
    if result.get('containers'):
        print("  Containers:")
        for line in result['containers']:
            print(f"    {line}")
    print(f"  ✓ {result.get('message', f'docker compose {action} completed')}")
    return True


# ---------------------------------------------------------------------------
# Scenario loader helper
# ---------------------------------------------------------------------------

def do_load_scenario():
    """Prompt for config, upload it, load and init the scenario. Returns True on success."""
    config_path_input = _input("Configuration file [config.toml]: ").strip()
    if not config_path_input:
        config_path_input = "config.toml"
    config_path = os.path.join(SNES_DIR, config_path_input) if not os.path.isabs(config_path_input) else config_path_input
    print(f"  Loading configuration: {os.path.basename(config_path)}")
    if not api_upload("config", config_path):
        print("  ✗ Failed to upload configuration file.")
        return False
    result, ok = api_call("POST", "/api/load-config")
    if not ok:
        return False
    summary = result.get('config_summary', {})
    print(f"  ✓ {result.get('message')}")
    print(f"    Satellites:      {summary.get('satellites', 0)}")
    print(f"    Ground stations: {summary.get('ground_stations', 0)}")
    print(f"    Channels:        {summary.get('channels', 0)}")
    result, ok = api_call("POST", "/api/init-scenario", timeout=60)
    if not ok:
        return False
    print(f"  ✓ {result.get('message')}")
    return True


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="VSNES Satellite Network Emulator — CLI Launcher"
    )
    parser.add_argument('--all', action='store_true', help='Start all services (Web + NTP + MCP)')
    parser.add_argument('--web', action='store_true', help='Start Cesium web server')
    parser.add_argument('--ntp', action='store_true', help='Start NTP server')
    parser.add_argument('--mcp', action='store_true', help='Start MCP server')
    args = parser.parse_args()

    if args.all:
        start_web = start_ntp = start_mcp = True
    else:
        start_web = args.web
        start_ntp = args.ntp
        start_mcp = args.mcp

    print("""
╔══════════════════════════════════════════════════╗
║          VSNES — Satellite Network Emulator      ║
║                    CLI Launcher                   ║
╚══════════════════════════════════════════════════╝
    """)

    services = ["API"]
    if start_web: services.append("Web/Cesium")
    if start_ntp: services.append("NTP")
    if start_mcp: services.append("MCP")
    print(f"  Starting: {' + '.join(services)}\n")

    if start_web:
        proc = start_process("web", f"{PYTHON} Class/Server.py True 500.0".split())
        if proc:
            start_streamer(proc, "WEB")
            print(f"  ✓ Web server starting → http://localhost:5580")

    if start_ntp:
        proc = start_process("ntp", f"{PYTHON} ntpserver.py --port 12345".split())
        if proc:
            start_streamer(proc, "NTP")
            print(f"  ✓ NTP server starting → port 12345")

    if start_mcp:
        proc = start_process("mcp", [PYTHON, os.path.join(SNES_DIR, "mcpServer.py")])
        if proc:
            start_streamer(proc, "MCP")
            print(f"  ✓ MCP server starting → http://localhost:8560")

    proc = start_process("api", [PYTHON, os.path.join(SNES_DIR, "apiServer.py")])
    if proc:
        start_streamer(proc, "API")

    if not wait_for_api():
        print("\n  ✗ Failed to start API server.")
        cleanup()
        sys.exit(1)

    print(f"\n  ┌──────────────────────────────────────────────┐")
    print(f"  │  API:  http://localhost:5050                  │")
    if start_web:
        print(f"  │  GUI:  http://localhost:5580                  │")
    if start_ntp:
        print(f"  │  NTP:  port 12345                             │")
    if start_mcp:
        print(f"  │  MCP:  http://localhost:8560                  │")
    print(f"  └──────────────────────────────────────────────┘\n")

    time.sleep(0.5)

    CZML_BOOL = False
    SCENARIO_LOADED = False

    while True:
        inp = _input("\nInsert the action you wish to perform (insert 'help' to see all available actions): ").strip().lower()

        if inp == "help":
            print("- help: shows all available actions")
            print("- load_scenario: load a configuration file and initialize the scenario")
            print("- scenario: show the loaded nodes and their type")
            print("- start_vms: create or start the VMs for every node")
            print("- compose_up [services...]: start the Docker node containers (docker compose up -d)")
            print("- compose_down: stop and remove the Docker node containers (docker compose down)")
            print("- delete_vm: delete a specific VM")
            print("- write_czml: write ScenarioCZML.czml data for Cesium")
            print("- run_all: run the emulation and Cesium")
            print("- run_emulator: run only the emulation")
            print("- run_cesium: run only the visualization at Cesium")
            print("- stop: stop the running simulation")
            print("- shutdown_vms: stop all VMs")
            print("- exit: program execution ends")

        elif inp in ('load_scenario', 'load scenario', 'load'):
            SCENARIO_LOADED = do_load_scenario()

        elif inp == "scenario":
            result, ok = api_call("GET", "/api/scenario")
            if ok:
                print(result.get('description', 'No scenario loaded'))

        elif inp in ('write_czml', 'write czml'):
            result, ok = api_call("POST", "/api/write-czml")
            if ok:
                CZML_BOOL = True
                print("  ✓ CZML file written successfully")

        elif inp in ('start_vms', 'vm'):
            result, ok = api_call("POST", "/api/start-vms", timeout=120)
            if ok:
                print(f"  ✓ {result.get('message')}")

        elif inp.startswith('compose_up') or inp.startswith('compose up'):
            # optional service names after the command, e.g. "compose_up satellite-1 ibi_es"
            services = inp.replace('compose_up', '', 1).replace('compose up', '', 1).split()
            docker_compose("up", services)

        elif inp in ('compose_down', 'compose down'):
            docker_compose("down")

        elif inp in ('run', 'run_all', 'run all'):
            if not SCENARIO_LOADED:
                print("  No scenario loaded. Starting load_scenario...")
                SCENARIO_LOADED = do_load_scenario()
                if not SCENARIO_LOADED:
                    continue
            if not CZML_BOOL:
                while True:
                    ans = _input("In this execution, the czml file has not been written. Do you want to load it?(Y/N): ").strip().lower()
                    if ans in ('y', 'yes'):
                        result, ok = api_call("POST", "/api/write-czml")
                        if ok:
                            CZML_BOOL = True
                        break
                    elif ans in ('n', 'no'):
                        break
                    else:
                        print('ERROR: Invalid answer')
            sudo_pass = _input("Enter sudo password for host network config (or press Enter to skip): ").strip()
            result, ok = api_call("POST", "/api/simulation/start",
                                  json_data={"generate_czml": CZML_BOOL, "run_vms": True, "password": sudo_pass or None}, timeout=300)
            if ok:
                print(f"  ✓ {result.get('message')}")

        elif inp in ('emu', 'emulator', 'run_emu', 'run emu', 'run_emulator', 'run emulator'):
            if not SCENARIO_LOADED:
                print("  No scenario loaded. Starting load_scenario...")
                SCENARIO_LOADED = do_load_scenario()
                if not SCENARIO_LOADED:
                    continue
            sudo_pass = _input("Enter sudo password for host network config (or press Enter to skip): ").strip()
            result, ok = api_call("POST", "/api/simulation/start",
                                  json_data={"generate_czml": CZML_BOOL, "run_vms": True, "password": sudo_pass or None}, timeout=300)
            if ok:
                print(f"  ✓ {result.get('message')}")

        elif inp in ('cesium', 'run_cesium', 'run cesium'):
            if not SCENARIO_LOADED:
                print("  No scenario loaded. Starting load_scenario...")
                SCENARIO_LOADED = do_load_scenario()
                if not SCENARIO_LOADED:
                    continue
            if not CZML_BOOL:
                while True:
                    ans = _input("In this execution, the czml file has not been written. Do you want to load it?(Y/N): ").strip().lower()
                    if ans in ('y', 'yes'):
                        result, ok = api_call("POST", "/api/write-czml")
                        if ok:
                            CZML_BOOL = True
                        break
                    elif ans in ('n', 'no'):
                        break
                    else:
                        print('ERROR: Invalid answer')
            result, ok = api_call("POST", "/api/visualization/start",
                                  json_data={"generate_czml": CZML_BOOL}, timeout=60)
            if ok:
                print(f"  ✓ {result.get('message')}")

        elif inp == 'stop':
            result, ok = api_call("POST", "/api/simulation/stop", timeout=60)
            if ok:
                print(f"  ✓ {result.get('message')}")

        elif inp in ('shutdown_vms', 'shutdown vms'):
            result, ok = api_call("POST", "/api/stop-all-vms", timeout=60)
            if ok:
                print(f"  ✓ {result.get('message')}")

        elif inp in ('delete', 'delete_vm', 'delete vm'):
            while True:
                ans = _input('Which VM do you want to delete? ').strip()
                if ans.lower() == 'all':
                    result, ok = api_call("DELETE", "/api/delete-all-vms", timeout=60)
                    if ok:
                        print(f"  ✓ {result.get('message')}")
                    break
                elif ans == 'exit':
                    break
                else:
                    result, ok = api_call("DELETE", f"/api/delete-vm/{ans}", timeout=30)
                    if ok:
                        print(f"  ✓ {result.get('message')}")
                        break
                    else:
                        print(f"  VM '{ans}' not found, try again or type 'exit'")

        elif inp == "exit":
            while True:
                ans = _input("Do you want to delete all the VMs related with the scenario?(Y/N): ").strip().lower()
                if ans in ('y', 'yes'):
                    result, ok = api_call("DELETE", "/api/delete-all-vms", timeout=60)
                    break
                elif ans in ('n', 'no'):
                    break
                else:
                    print('ERROR: Invalid answer')

            try:
                requests.post(f"{API_URL}/api/reset", timeout=10)
            except:
                pass
            cleanup()
            print("  Goodbye!")
            break

        else:
            print(f"  '{inp}' is not one of the available actions")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Interrupted. Cleaning up...")
        for pattern in ['apiServer.py', 'Class/Server.py', 'ntpserver.py', 'mcpServer.py']:
            try:
                result = subprocess.run(f"pgrep -f '{pattern}'", shell=True, capture_output=True, text=True)
                for pid in result.stdout.strip().split('\n'):
                    if pid.strip():
                        try:
                            os.kill(int(pid.strip()), signal.SIGKILL)
                        except:
                            pass
            except:
                pass
        print("  Goodbye!")
        sys.exit(0)
