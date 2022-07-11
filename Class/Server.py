from flask import Flask, render_template
import sys

app = Flask(__name__)

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
@app.route('/ScenarioCZML.czml')
def czmlData():
	return render_template('ScenarioCZML.czml')

EMU_bool = sys.argv[1]
timer_ms = sys.argv[2]

app.run(debug=True, port=5000)
