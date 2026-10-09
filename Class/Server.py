#!/usr/bin/env python3
from flask import Flask, render_template, jsonify, request, json
from flask_cors import CORS
import os
import sys


app = Flask(__name__)
cors = CORS(app, resources={r"/api/*": {"origins": "*"}})

# Positions/ lives at the repo root (parent of Class/), regardless of the CWD
# the server is launched from.
_POSITIONS_DIR = os.environ.get(
    "POSITIONS_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Positions"),
)


def _load_nodes():
    with open(os.path.join(_POSITIONS_DIR, "nodes.json"), "r") as f:
        return json.load(f)


@app.route('/')
def index():
	# Read an existing CZML file
	data = {
		'EMU': EMU_bool,
		'title':'SNES',
		'timer' : timer_ms
	}
	print (data)
	return render_template('index.html',data = data)

@app.route('/satsPosition', methods=['GET'])
def check_locations():
    # Serve node positions from Positions/nodes.json, which Channel.update()
    # rewrites once per tick with every node's current state.
    #   /satsPosition            -> all nodes (JSON array)
    #   /satsPosition?name=SAT-1 -> single node (case-insensitive match)
    try:
        nodes = _load_nodes()
        name = request.args.get('name')
        if name is None:
            return jsonify(nodes)
        wanted = name.lower()
        for node in nodes:
            if str(node.get('name', '')).lower() == wanted:
                return jsonify(node)
        return jsonify({"error": f"node '{name}' not found"}), 404
    except Exception as e:
        print(f"Error reading file: {str(e)}")
        return jsonify({"error": "error"}), 500

@app.route('/satsOrbit', methods=['GET'])
def check_orbit():
    # Serve a node's pre-computed orbit array (Positions/<name>-total.json).
    # Case-insensitive: resolve the on-disk filename from nodes.json.
    try:
        name = request.args.get('name')
        if name is None:
            return jsonify({"error": "name parameter is required"}), 400
        # Resolve canonical (on-disk) name case-insensitively
        canonical = name
        try:
            wanted = name.lower()
            for node in _load_nodes():
                if str(node.get('name', '')).lower() == wanted:
                    canonical = node['name']
                    break
        except Exception:
            pass
        filename = os.path.join(_POSITIONS_DIR, f'{canonical}-total.json')
        with open(filename, 'r') as file:
            return jsonify(json.load(file))
    except FileNotFoundError:
        return jsonify({"error": f"orbit for '{name}' not found"}), 404
    except Exception as e:
        print(f"Error reading file: {str(e)}")
        return jsonify({"error": "error"}), 500

@app.route('/paper')
def paper_view():
	# Clean publication-style CZML viewer: white globe, black borders,
	# green orbits, cyan links, yellow coverage circles, no controls.
	return render_template('paper.html')

@app.route('/servicePlacement', methods=['GET'])
def service_placement():
	"""Satellites currently hosting a service"""
	path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
	                    'Positions', 'service_placement.json')
	try:
		with open(path) as f:
			return jsonify(json.load(f))
	except Exception:
		return jsonify({"serving": {}, "sim": "", "updated": 0})

@app.route('/ScenarioCZML.czml')
def czmlData():
	return render_template('ScenarioCZML.czml')

EMU_bool = sys.argv[1] if len(sys.argv) > 1 else "false"
timer_ms = sys.argv[2] if len(sys.argv) > 2 else "1000"

if __name__ == '__main__':
    port = int(os.environ.get("POSITION_API_PORT", "5580"))
    app.run(debug=True, host='0.0.0.0', port=port)
