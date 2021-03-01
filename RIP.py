import socket
import struct
import select
import threading
import time
import ipaddress
from random import random, seed, randint
from pyroute2 import IPRoute
from pyroute2.netlink.exceptions import NetlinkError

from RIP_lib import *
from WebGUI import *

class RouteEntry(object):
	def __init__(self, ip, mask, nextHop, metric=RIP_METRIC_MIN, routeTag=0, family=RIP_ADDRESS_FAMILY):
		self.family = family
		self.routeTag = routeTag
		self.ip = ip
		self.mask = mask
		self.nextHop = nextHop

		if metric >= RIP_METRIC_INFINITY:
			self.metric = RIP_METRIC_INFINITY
		elif metric <= RIP_METRIC_MIN:
			self.metric = RIP_METRIC_MIN
		else:
			self.metric = metric

		self.lastUpdate = time.time()
		self.garbage = False

class RipPacket(object):
	def __init__(self, cmd=RIP_COMMAND_RESPONSE, version=2):
		self.command = cmd
		self.version = version
		self.unused = 0
		self.entry = []

	def size(self):
		return RIP_HEADER_SIZE + len(self.entry)*RIP_ENTRY_SIZE

class RIP:
	def __init__(self):
		self.routes = []
		self.garbage = []
		self.activeSockets = []
		self.sending = False
		self.rip_enable = False
		self.checking_timeout = True
		self.iproute = IPRoute()
		self.rip_neighbors = []

		self.interfaces = []
		self.addInterfaces()

		if self.createSocket(RIP_MULTICAST, RIP_UDP_PORT):
			self.rip_enable = True
			self.rip_neighbors.append(RIP_MULTICAST)

	def addInterfaces(self):
		# Adding interfaces to list using module pyroute2
		addresses = ()
		addresses = self.iproute.get_addr(family=2)

		print("Added interfaces:")
		for address in addresses:
			ip = [x[1]
				for x in address["attrs"] if x[0] == "IFA_ADDRESS"][0]
			prefix = address["prefixlen"]
			int_name = [x[1]
				for x in address["attrs"] if x[0] == "IFA_LABEL"][0]
			print(f'{ip}/{prefix} [{int_name}]')

			self.interfaces.append(ipaddress.IPv4Interface(f'{ip}/{prefix}'))

	def createSocket(self, ip, port):
		# Create socket with 'ip' on 'port'
		for sock in self.activeSockets:
			if sock.getsockname() == (ip, port):
				print (f'Socket {ip}:{port} was already open!')
				return False
		sock = socket.socket(socket.AF_INET, # Internet
							socket.SOCK_DGRAM) # UDP

		if ip == RIP_MULTICAST:
			# Set some options to make it multicast-friendly
			sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
			try:
				sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
			except AttributeError:
				pass # Some systems don't support SO_REUSEPORT
			# Setting TTL to value 2 on multicast sockets
			sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
		else:
			# Setting TTL to value 2 on not multicast sockets for multicast IP and another IP
			sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
			sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, 2)
			# Adding interface to multicast membership
			self.activeSockets[0].setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(RIP_MULTICAST) + socket.inet_aton(ip))

		# Bind to the port
		sock.bind((ip, port))

		self.activeSockets.append(sock)
		print (f'{self.activeSockets[-1].getsockname()[0]}:{self.activeSockets[-1].getsockname()[1]} -> SOCKET ADDED')
		return True

	def closeSocket(self, ip, port):
		# Closing socket with 'ip' on 'port'
		for sock in self.activeSockets:
			if sock.getsockname() == (ip, port):
				if ip != RIP_MULTICAST:
					print(ip)
					self.activeSockets[0].setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, socket.inet_aton(RIP_MULTICAST) + socket.inet_aton(ip))
				sock.close()
				self.activeSockets.remove(sock)
				print (f'{ip}:{port} -> SOCKET CLOSED')
				return True
		print (f'Socket {ip}:{port} wasn`t open!')
		return False

	def findSocket(self, ip, port):
		for sock in self.activeSockets:
			if sock.getsockname() == (ip, port):
				return True
		return False

	def updateTime(self):
		# Update time for sending RIP packets. Default time for sending RIP packets is 30 seconds + small random number from -5 to 5
		seed(time.time())
		rand = random() * 10 - 5
		return RIP_DEFAULT_UPDATE + rand

	def checkTimeout(self):
		# Checking timeouts for every route in routing table
		while self.checking_timeout:
			# Checking distributed routes
			for route in self.routes:
				# Checking all received routes
				if (time.time() - route.lastUpdate) > RIP_DEFAULT_TIMEOUT and route.nextHop != "0.0.0.0" and route.garbage != True:
					print (f'{route.ip}, {route.mask}, {route.nextHop}, {route.metric} -> WAS MOVED TO GARBAGE FROM ROUTES')
					route.metric = RIP_METRIC_INFINITY
					route.garbage = True
					self.garbage.append(route)
					break
				# Checking local routes which has metric infinity
				if (time.time() - route.lastUpdate) > RIP_DEFAULT_TIMEOUT and route.nextHop == "0.0.0.0" and route.metric == RIP_METRIC_INFINITY and route.garbage != True:
					route.garbage = True
					self.garbage.append(route)
			# Checking garbaged routes
			for route in self.garbage:
				if (time.time() - route.lastUpdate) > RIP_DEFAULT_GARBAGE + RIP_DEFAULT_TIMEOUT:
					print (f'{route.ip}, {route.mask}, {route.nextHop}, {route.metric} -> WAS REMOVED FROM GARBAGE')
					if route in self.routes:
						self.routes.remove(route)
						self.garbage.remove(route)
						if route.nextHop != "0.0.0.0":
							self.removeRoute(route)
						break
					else:
						self.garbage.remove(route)

		print("CHECKING TIMEOUT PAUSED!")

	def addRoute(self, ip, mask, nextHop, metric=RIP_METRIC_MIN, routeTag=0, family=RIP_ADDRESS_FAMILY):
		# Adding route to linux routing table
		replace = False
		# Checking, if route doesn't exists
		for route in self.routes:
			if route.ip == ip and  route.mask == mask and route.nextHop == nextHop and route.routeTag == routeTag and route.family == family:
				if route.metric == metric:
					# Updating last update time of existing route
					self.updateRoute(route)
				else:
					# Metric of existing route has been changed
					route.metric = metric
				return True
			elif route.ip == ip and  route.mask == mask and route.nextHop != nextHop:
				if route.metric <= metric:
					# Droping RTE
					return False
				if route.metric > metric:
					# Replacing route
					replace = True
					self.replaceRoute(route)
					break
		# Adding route to distributed routes
		self.routes.append(RouteEntry(ip, mask, nextHop, metric, routeTag, family))
		# Adding route to linux routing table
		if nextHop != '0.0.0.0':
			prefix = Mask2Prefix(mask)
			assignedInt = False

			for i in range(len(self.interfaces)):
				int_network = self.interfaces[i].network
				if ipaddress.IPv4Address(nextHop) in int_network:
					interface = self.interfaces[i]
					assignedInt = True
				if ipaddress.IPv4Network(f'{ip}/{prefix}') == int_network:
					return False
			if assignedInt == True:
				try:
					self.iproute.route("add",
										dst=ip,
										mask=prefix,
										gateway=str(interface.ip),
										metrics={"mtu": 1400,
												"hoplimit": 16})
					print(f'{ip}/{prefix} {str(interface.ip)} -> ROUTE ADDED')
					return True
				except NetlinkError as e:
					if e.code == 17:
						print(f'IP Address {ip} already exists.')
					else:
						raise e
			else:
				return False
		return True

	def updateRoute(self, route):
		# Updating last update of route
		route.lastUpdate = time.time()
		if route.garbage == True:
			route.garbage == False

	def replaceRoute(self, route):
		# Replacing route
		self.checking_timeout = False
		self.t_checking.join()
		self.removeRoute(route)
		self.routes.remove(route)
		self.checking_timeout = True
		self.t_checking = threading.Thread(target=self.checkTimeout)
		self.t_checking.start()
		print("CHECKING TIMEOUT UNPAUSED!")

	def removeRoute(self, route):
		# Removing route from linux routing table
		prefix = Mask2Prefix(route.mask)

		assignedInt = False
		for i in range(len(self.interfaces)):
			int_network = self.interfaces[i].network
			if ipaddress.IPv4Address(route.nextHop) in int_network:
				interface = self.interfaces[i]
				assignedInt = True
				break

		if assignedInt == True:
			try:
				self.iproute.route("delete",
									dst=route.ip,
									mask=prefix,
									gateway=str(interface.ip))
				print(f'{route.ip}/{prefix} {str(interface.ip)} -> ROUTE REMOVED')
				return True
			except NetlinkError as e:
				if e.code == 3:
					print(f'IP Address {route.ip} doesn`t exists.')
				else:
					raise e
		return False

	def addNetwork(self, network_ip):
		# Adding route from input and GUI
		try:
			ip = ipaddress.IPv4Address(network_ip)
		except:
			print("Wrong network address!")
			return False

		assignedInt = False
		for i in range(len(self.interfaces)):
			int_network = self.interfaces[i].network
			if ip in int_network:
				interface = self.interfaces[i]
				assignedInt = True
				break

		if assignedInt == True:
			# Adding network to route table
			if not self.addRoute(str(interface.network.network_address),str(interface.network.netmask), "0.0.0.0"):
				return False
			# Receiving RIP packets on assigned interface
			if not self.createSocket(str(interface.ip), RIP_UDP_PORT):
				return False
			# Starting sending and receiving RIP packets on RIP MULTICAST on assigned interface and checking distributed routes
			if self.sending == False:
				t_multicast_recv = threading.Thread(target=self.receivePacket, args=(RIP_MULTICAST, RIP_UDP_PORT))
				t_multicast_recv.start()
				self.t_checking = threading.Thread(target=self.checkTimeout)
				self.t_checking.start()
				self.sending = True
				self.sendPacket(RIP_MULTICAST, RIP_UDP_PORT, RIP_COMMAND_REQUEST)
				tSending = threading.Thread(target=self.sendPacket)
				tSending.start()
			return True
		print("The network isn't directly connected!")
		return False

	def removeNetwork(self, network_ip):
		# Removing route from input and GUI
		try:
			ip = ipaddress.IPv4Address(network_ip)
		except:
			print("Wrong network address!")
			return False

		assignedInt = False
		for i in range(len(self.interfaces)):
			int_network = self.interfaces[i].network
			if ip in int_network:
				interface = self.interfaces[i]
				assignedInt = True
				break

		if assignedInt == True:
			# Closing socket
			if not self.closeSocket(str(interface.ip), RIP_UDP_PORT):
				return False

			removed_routes = []
			for route in self.routes:
				# Finding out routes associated with the interface
				if ipaddress.IPv4Address(route.nextHop) in interface.network:
					removed_routes.append(route)
				if ipaddress.IPv4Address(route.ip)	in interface.network and route.nextHop == "0.0.0.0":
					removed_routes.append(route)

			for route in removed_routes:
				self.checking_timeout = False
				self.t_checking.join()
				# Setting infinity metric for removed route
				route.metric = RIP_METRIC_INFINITY
				# Starting timeout for removed local route
				if route.nextHop == "0.0.0.0":
					route.lastUpdate = time.time()
				self.checking_timeout = True
				self.t_checking = threading.Thread(target=self.checkTimeout)
				self.t_checking.start()
				print("CHECKING TIMEOUT UNPAUSED!")
			# If are all sockets closed set sending and receiving to false
			if len(self.activeSockets) == 1:
				self.sending = False
			# Sending request message to RIP multicast
			self.sendPacket(RIP_MULTICAST, RIP_UDP_PORT, RIP_COMMAND_REQUEST)
			return True

		print("The network isn't directly connected!")
		return False

	def setNeighbor(self, neighbor_ip):
		try:
			UDP_IP = ipaddress.IPv4Address(neighbor_ip)
			UDP_PORT = RIP_UDP_PORT
		except:
			print("Wrong network address!")
			return False

		assignedInt = False
		for i in range(len(self.interfaces)):
			int_network = self.interfaces[i].network
			if UDP_IP in int_network:
				interface = self.interfaces[i]
				assignedInt = True
				break

		if assignedInt == True and not UDP_IP.is_multicast:
			if self.findSocket(str(interface.ip), UDP_PORT):
				self.rip_neighbors.append(str(UDP_IP))
				return True
			else:
				print("Socket is closed!")
				return False

		print("The neighbor isn't directly connected!")
		return False

	def removeNeighbor(self, neighbor_ip):
		try:
			ip = ipaddress.IPv4Address(neighbor_ip)
		except:
			print("Wrong neighbor address!")
			return False

		if not ipaddress.IPv4Address(neighbor_ip).is_multicast:
			if self.rip_neighbors.remove(neighbor_ip):
				return True

		print(f'The neighbor {neighbor_ip} does not exists!')
		return False

	def sendPacket(self, ip=RIP_MULTICAST, port=RIP_UDP_PORT, command=RIP_COMMAND_RESPONSE):
		UDP_IP = ip
		UDP_PORT = RIP_UDP_PORT
		sendPkt = RipPacket(command)

		if sendPkt.command == RIP_COMMAND_REQUEST:
			# ! in struct.pack - network byte order
			rip_hdr = struct.pack(RIP_HEADER_PACK_FORMAT, sendPkt.command, sendPkt.version, sendPkt.unused)
			for sock in self.activeSockets:
				if sock.getsockname()[0] != RIP_MULTICAST:
					for interface in self.interfaces:
						if ipaddress.IPv4Address(sock.getsockname()[0]) in interface.network:
							assigned_interface = interface
							break
					sock.sendto(rip_hdr, (UDP_IP, UDP_PORT))
					print (f'SENT REQUEST TO {UDP_IP}:{UDP_PORT}')
					break
		else:
			while self.sending:
				# ! in struct.pack - network byte order
				rip_hdr = struct.pack(RIP_HEADER_PACK_FORMAT, sendPkt.command, sendPkt.version, sendPkt.unused)
				for IP in self.rip_neighbors:
					for sock in self.activeSockets:
						rip_rte = b''
						if sock.getsockname()[0] != RIP_MULTICAST:
							# Finding socket's interface
							assignedInt = False
							for interface in self.interfaces:
								if ipaddress.IPv4Address(sock.getsockname()[0]) in interface.network:
									# Condition for "neighbor" command.. Sending just on neighbor's interface
									if IP != RIP_MULTICAST:
										if ipaddress.IPv4Address(IP) in interface.network:
											assigned_interface = interface
											assignedInt = True
											break
									else:
										assigned_interface = interface
										assignedInt = True
										break
							# Packing routes to RTE of RIP packet
							if assignedInt == True:
								for route in self.routes:
									# Increasing metric for not directly connected routes
									if route.nextHop != "0.0.0.0":
										sendPkt.entry.append(struct.pack("!HH", route.family, route.routeTag) + socket.inet_aton(route.ip) + socket.inet_aton(route.mask) + socket.inet_aton("0.0.0.0") + struct.pack("!I", route.metric + 1))
									else:
										sendPkt.entry.append(struct.pack("!HH", route.family, route.routeTag) + socket.inet_aton(route.ip) + socket.inet_aton(route.mask) + socket.inet_aton("0.0.0.0") + struct.pack("!I", route.metric))
									if not (ipaddress.IPv4Address(route.nextHop) in assigned_interface.network or ipaddress.IPv4Address(route.ip) == assigned_interface.network.network_address):
										rip_rte = rip_rte + sendPkt.entry.pop(-1)
									# Sending packet to UDP IP on UDP PORT
								sock.sendto(rip_hdr + rip_rte, (IP, UDP_PORT))
								print (f'SENT RESPONSE TO {IP}:{UDP_PORT}')
				if UDP_IP != RIP_MULTICAST:
					break
				# Waiting for send next response message
				lastSent = time.time()
				updateTime = self.updateTime()
				while (time.time() - lastSent) < updateTime and self.sending:
					pass

	def receivePacket(self, ip, port):
		UDP_IP = ip
		UDP_PORT = port
		print (f'RECEIVING ON {UDP_IP}')

		for sock in self.activeSockets:
			if sock.getsockname() == (UDP_IP, UDP_PORT):
				receiveSocket = sock
				break

		while self.rip_enable:
			inputs = self.activeSockets
			outputs = []
			readable, writable, exceptional = select.select(inputs, outputs, inputs, 1)
			for s in readable:
				data, address = s.recvfrom(RIP_RECV_BUF_SIZE)
				own_interface = False
				for sock in self.activeSockets:
					if address[0] == sock.getsockname()[0]:
						own_interface = True

				if own_interface == False:
					pkt = RipPacket()
					hdr = data[:RIP_HEADER_SIZE]
					data = data[RIP_HEADER_SIZE:]
					pkt.command, pkt.version, zero = struct.unpack(RIP_HEADER_PACK_FORMAT, hdr)
					if pkt.command == RIP_COMMAND_REQUEST:
						# Receiving request message
						print(f'RECEIVED RIP REQUEST MESSAGE FROM {address[0]} on {s.getsockname()[0]}:')
						self.sendPacket(address[0], RIP_UDP_PORT)
					else:
						# Receiving response message
						print(f'RECEIVED RIP RESPONSE MESSAGE FROM {address[0]} on {s.getsockname()[0]}:')
						# Unpacking RIP packet
						while len(data) > 0 and len(data)%RIP_ENTRY_SIZE == 0:
							entry = data[:RIP_ENTRY_SIZE]
							data = data[RIP_ENTRY_SIZE:]
							family, tag, ip, mask, nextHop, metric = struct.unpack(RIP_ENTRY_PACK_FORMAT, entry)
							pkt.entry.append(RouteEntry(
											 socket.inet_ntoa(struct.pack("!I",ip)), socket.inet_ntoa(struct.pack("!I",mask)), socket.inet_ntoa(struct.pack("!I",nextHop)), metric, tag, family))
							if pkt.entry[-1].nextHop == "0.0.0.0":
								self.addRoute(pkt.entry[-1].ip, pkt.entry[-1].mask, address[0], pkt.entry[-1].metric, pkt.entry[-1].routeTag, pkt.entry[-1].family)
							else:
								self.addRoute(pkt.entry[-1].ip, pkt.entry[-1].mask, pkt.entry[-1].nextHop, pkt.entry[-1].metric, pkt.entry[-1].routeTag, pkt.entry[-1].family)
						for x in range(len(pkt.entry)):
							print(f'{pkt.entry[x].ip}, {pkt.entry[x].mask}, {pkt.entry[x].nextHop}, {pkt.entry[x].metric}')
		print("ENDING THREAD")

	def generateRoutes(self, count):
		# Generating more random routes
		seed(time.time())
		i = 0
		while i < int(count):
			ipClass = randint(1,3)
			if ipClass == 1:
				# CLASS A
				firstOct = randint(1, 126)
				secondOct = randint(0, 255)
				thirdOct = randint(0, 255)
			elif ipClass == 2:
				# CLASS B
				firstOct = randint(128, 191)
				secondOct = randint(0, 255)
				thirdOct = randint(0, 255)
			else:
				# CLASS C
				firstOct = randint(192, 223)
				secondOct = randint(0, 255)
				thirdOct = randint(0, 255)

			ip = str(firstOct) + "." + str(secondOct) + "." + str(thirdOct) + ".0"
			mask = self.maskInClass(firstOct)
			metric = randint(RIP_METRIC_MIN, RIP_METRIC_MAX)

			self.routes.append(RouteEntry(ip, mask, "0.0.0.0", metric))
			i += 1

	def maskInClass(self, firstOct):
		# Adding mask for IP address by classes
		if firstOct < 127:
			mask = "255.0.0.0"
		elif firstOct < 192:
			mask = "255.255.0.0"
		else:
			mask = "255.255.255.0"

		return mask

	def shutdownRIP(self):
		# Shutting down RIP
		print ("RIP is shutting down...")
		self.sending = False
		self.checking_timeout = False
		self.rip_enable = False
		while self.activeSockets:
			self.closeSocket(self.activeSockets[-1].getsockname()[0],self.activeSockets[-1].getsockname()[1])
		for route in self.routes:
			self.removeRoute(route)

	def inputCycle(self):
		# Inputing from terminal
		while True:
			command = input("(conifg-router)#")
			if command[0:2] == "no":
				if command[3:10] == "network":
					if self.removeNetwork(command[11:]):
						print("Network removed!")

				if command[3:11] == "neighbor":
					if self.removeNeighbor(command[12:]):
						print("Neighbor removed!")

			elif command[0:7] == "network":
				network_ip = command[8:]
				if self.addNetwork(network_ip):
					print("Network added!")

			elif command[0:8] == "neighbor":
				neighbor_ip = command[9:]
				if self.setNeighbor(neighbor_ip):
					print("Neighbor added!")

			elif command[0:15] == "generate random":
				count = command[16:]
				self.generateRoutes(count)

			elif command[0:8] == "generate":
				input_data = command[9:].split(" ")
				if len(input_data) == 4:
					network_ip = input_data[0]
					mask = input_data[1]
					nextHop = input_data[2]
					metric = int(input_data[3])
					self.routes.append(RouteEntry(network_ip, mask, nextHop, metric))
				else:
					print("Wrong input!")

			elif command == "show ip route":
				print ("IP ROUTES:")
				for route in self.routes:
					print (f'{route.ip}, {route.mask}, {route.nextHop}, {route.metric}, {time.ctime(route.lastUpdate)}')

			elif command == "show garbage":
				print ("GARBAGE ROUTES:")
				for route in self.garbage:
					print (f'{route.ip}, {route.mask}, {route.nextHop}, {route.metric}, {time.ctime(route.lastUpdate)}')

			elif command == "show ip neighbors":
				print ("RIP NEIGHBORS:")
				for i in range(1, len(self.rip_neighbors)):
					print (self.rip_neighbors[i])

			elif command == "exit":
				self.shutdownRIP()
				break
			else:
				print("Unknown command!")

if __name__ == "__main__":
	rip = RIP()
	tInput = threading.Thread(target=rip.inputCycle)
	tInput.start()

	gui = WebGUI(rip)
	gui.start_server()

	tInput.join()
	gui.stop_server()
