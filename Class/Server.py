#!/usr/bin/env python3
from flask import Flask, render_template, jsonify, request, json
from flask_cors import CORS
import sys


app = Flask(__name__)
cors = CORS(app, resources={r"/api/*": {"origins": "*"}})


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
    try:
        name = request.args.get('name')
        if name is None:
            return jsonify({"error": "name parameter is required"})
        filename = f'Positions/{name}.json'
        with open(filename, 'r') as file:
            json_data = json.load(file)
            return jsonify(json_data)
    except Exception as e:
        print(f"Error reading file: {str(e)}")
        return jsonify({"error": "error"})

@app.route('/satsOrbit', methods=['GET'])
def check_orbit():
    try:
        name = request.args.get('name')
        if name is None:
            return jsonify({"error": "name parameter is required"})
        filename = f'Positions/{name}-total.json'
        with open(filename, 'r') as file:
            json_data = json.load(file)
            return jsonify(json_data)
    except Exception as e:
        print(f"Error reading file: {str(e)}")
        return jsonify({"error": "error"})

@app.route('/ScenarioCZML.czml')
def czmlData():
	return render_template('ScenarioCZML.czml')

EMU_bool = sys.argv[1]
timer_ms = sys.argv[2]

app.run(debug=True,host='0.0.0.0', port=5500)
