import threading
from flask import Flask, flash, render_template, redirect, request, url_for
from werkzeug.serving import make_server

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev'

class WebGUI(object):
	def __init__(self, rip):
		global rip_global
		rip_global = rip

	@app.route('/', methods=['GET', 'POST'])
	def home():
		return render_template('base.html')

	@app.route('/add-network', methods=['GET', 'POST'])
	def add_network():
		if request.method == 'POST':
			network_ip = request.form['network_ip']

			if rip_global.addNetwork(network_ip):
				flash_msg = "Network added!"
			else:
				flash_msg = "Wrong network!"

			flash(flash_msg)
		return render_template('add-network.html')

	@app.route('/remove-network', methods=['GET', 'POST'])
	def remove_network():
		if request.method == 'POST':
			network_ip = request.form['network_ip']

			if rip_global.removeNetwork(network_ip):
				flash_msg = "Network removed!"
			else:
				flash_msg = "Wrong network!"

			flash(flash_msg)
		return render_template('remove-network.html')

	@app.route('/generate-random-networks', methods=['GET', 'POST'])
	def generate_random_networks():
		if request.method == 'POST':
			count = request.form['count']
			rip_global.generateRoutes(int(count))
			flash("Networks generated!")
		return render_template('generate-random.html')

	@app.route('/generate-own-network', methods=['GET', 'POST'])
	def generate_own_network():
		if request.method == 'POST':
			network_ip = request.form['network_ip']
			network_mask = request.form['network_mask']
			nextHop_ip = request.form['nextHop_ip']
			metric = request.form['metric']

			if rip_global.addRoute(network_ip, network_mask, nextHop_ip, metric):
				flash_msg = "Network generated!"
			else:
				flash_msg = "Wrong network!"

			flash(error)
		return render_template('generate-own.html')

	@app.route('/routing-table')
	def routing_table():
		routes = rip_global.routes
		return render_template('routing-table.html', routes=routes)

	def start_server(self):
		global server
		server = ServerThread(app)
		server.start()

	def stop_server(self):
		global server
		server.shutdown()

# Class for Flask thread
class ServerThread(threading.Thread):
	def __init__(self, app):
		threading.Thread.__init__(self)
		self.srv = make_server('127.0.0.1', 5000, app)
		self.ctx = app.app_context()
		self.ctx.push()

	def run(self):
		self.srv.serve_forever()

	def shutdown(self):
		self.srv.shutdown()
