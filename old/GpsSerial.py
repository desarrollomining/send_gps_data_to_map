import time
import json
import math
import thread
import datetime
import requests
import OpenSSL
from socket import *
from pynmea import nmea
from oraculus import Thing, USBDevnode
from serial import Serial, SerialException

class GpsSerial(Thing):

	def __init__(self, usbdevnode, baudrate = 9600, name="GPS", live_json_file_path="/run/dio/gps.json", log_id="GPS"):
		self.live_json_file_path = live_json_file_path
		self.usbdevnode = usbdevnode
		self.baudrate = baudrate
		self.log_id = log_id
		self.comport = None
		self.log("GpsSerial listener init [%s @ %s bps]" %(self.usbdevnode.getDevnode(), self.baudrate))
		self.lat = 0
		self.lon = 0
		self.last_lat = 0
		self.last_lon = 0
		self.angle = 0
		self.speed = 0
		self.buffer_length = 1024
		self.gprmc = nmea.GPRMC()
		self.instant_speed = 0 # Need to get averages? do the math somewhere else
		self.text_gprmc = None
		self.text_gpgga = None

		# Constants related to Vincenty distance estimation
		# EPSG:4326, WGS84 web map decimal degrees
		self.a = 6378137  # meters
		self.f = 1 / 298.257223563
		self.b = 6356752.314245  # meters; b = (1 - f)a
		self.MILES_PER_KILOMETER = 0.621371
		self.MAX_ITERATIONS = 200
		self.CONVERGENCE_THRESHOLD = 1e-12  # .000,000,000,001
		self.distance_from_last_point = 0   # Also used for match()ing.

		thread.start_new_thread(self.serialCommThread, ())

	def instantSpeed(self):
		return self.instant_speed

	def getCurrentVariables(self):
		data =  {
			'gps':{
				'device':{
					'class': 'GpsSerial',
					'usb_port': self.usbdevnode.getPort(),
					'tty': self.usbdevnode.getDevnode(),
					'hardware_version': self.usbdevnode.getHardwareVersion()
				},
				'data':{
					'latitude': self.lat,
					'longitude': self.lon,
					'last_latitude': self.last_lat,
					'last_longitude': self.last_lon,
					'speed': round(self.speed, 1),
					'distance': round(self.distance, 1),
					'nmea': self.text_gprmc,
					'datetime': self.getDateTime(),
					'angle': round(self.angle, 1)
				}
			}
		}
		return data


	def reportNoFix(self):
		self.lat = 0
		self.lon = 0
		self.speed = 0
		self.angle = 0
		self.distance = 0
		report = self.getCurrentVariables()
		return report

	def decodeGPRMC(self, line):
		try:
			self.text_gprmc = line
			self.gprmc.parse(line)
			self.last_lat = self.lat
			self.last_lon = self.lon
			self.lat = round(int(self.gprmc.lat[:2]) + (float(self.gprmc.lat[2:])/60),6)
			self.lon = round(int(self.gprmc.lon[:3]) + (float(self.gprmc.lon[3:])/60),6)
			if self.gprmc.lat_dir == 'S':
				self.lat = -self.lat
			if self.gprmc.lon_dir == 'W':
				self.lon = -self.lon
			self.angle = math.atan2(self.lon - self.last_lon, self.lat - self.last_lat) * 180/3.141592
			if self.angle < 0:
				self.angle = self.angle + 360
			self.distance = self.vincentyInverse((self.last_lat, self.last_lon), (self.lat, self.lon))
			self.speed = float(self.gprmc.spd_over_grnd) * 1.852 # knots -> km/h
			data = json.dumps(self.getCurrentVariables())
			self.log("decodeGPRMC(): %s" % data)
			return data
		except ValueError as exc:
			self.log("GPS NOFIX: Unable to find Lat/Lon in NMEA frame [%s]" % line)
			return json.dumps(self.reportNoFix())
		except:
			self.traceback()
			return None


	def serialCommThread(self):
		while True:
			if self.comport is None:
				try:
					self.comport = Serial(self.usbdevnode.getDevnode(), self.baudrate)
					self.log("GpsSerial initialized [%s]" % self.comport)
				except SerialException:
					self.reconnectSerial()

			try:
				data = self.comport.readline()
				if not data: break
				lines = data.split('\n')
				for line in lines:
					line = line.strip()
					if line == "":
						continue
					#self.log("GOT [%s]" % line)
					if "RMC" in line:
						self.log("GOT [%s]" % line)
						# result is a json-formatted STRING
						result = self.decodeGPRMC(line)
						if result is not None:
							self.writeFile(self.live_json_file_path, result)
							self.emit('gps', result)
						with open ("/NMEA.txt", "a") as myfile:
							myfile.write("%s | %s\n" % (self.getDateTime(), line))
						with open ("/NMEA_GPGGA.txt", "a") as myfile:
							myfile.write("%s | %s\n" % (self.getDateTime(), line))

					if "GPGSA" in line:
						gsa = nmea.GPGSA()
						gsa.parse(line)
						#self.log(vars(gsa))
					if "GPGSV" in line:
						gsv = nmea.GPGSV()
						gsv.parse(line)
						#self.log(vars(gsv))
					if "GPVTG" in line:
						vtg = nmea.GPVTG()
						vtg.parse(line)
						#self.log(vars(vtg))
					if "GPGGA" in line:
						gpa = nmea.GPGGA()
						gpa.parse(line)
						with open ("/NMEA_GPGGA.txt", "a") as myfile:
							myfile.write("%s | %s\n" % (self.getDateTime(), line))
						#self.log(vars(gpa))

			except SerialException:
				self.emit('gps', json.dumps({"error":"NO_GPS"}))
				self.reconnectSerial()

			except:
				self.traceback()

	def reconnectSerial(self):
		try:
			self.comport = Serial(self.usbdevnode.getDevnode(), self.baudrate)
			self.log("reconnectSerial [%s]" % self.comport)
		except:
			self.traceback()
		time.sleep(1)


	# This is Vincenty's inverse, sourced from https://pypi.python.org/pypi/vincenty/0.1.4
	def vincentyInverse(self, point1, point2, miles=False):
		"""
		Vincenty's formula (inverse method) to calculate the distance (in
		meters or miles) between two points on the surface of a spheroid

		Doctests:
		>>> vincenty((0.0, 0.0), (0.0, 0.0))  # coincident points
		0.0
		>>> vincenty((0.0, 0.0), (0.0, 1.0))
		111.319491
		>>> vincenty((0.0, 0.0), (1.0, 0.0))
		110.574389
		>>> vincenty((0.0, 0.0), (0.5, 179.5))  # slow convergence
		19936.288579
		>>> vincenty((0.0, 0.0), (0.5, 179.7))  # failure to converge
		>>> boston = (42.3541165, -71.0693514)
		>>> newyork = (40.7791472, -73.9680804)
		>>> vincenty(boston, newyork)
		298.396057
		>>> vincenty(boston, newyork, miles=True)
		185.414657
		"""

		# short-circuit coincident points
		if point1[0] == point2[0] and point1[1] == point2[1]:
			return 0.0

		U1 = math.atan((1 - self.f) * math.tan(math.radians(point1[0])))
		U2 = math.atan((1 - self.f) * math.tan(math.radians(point2[0])))
		L = math.radians(point2[1] - point1[1])
		Lambda = L

		sinU1 = math.sin(U1)
		cosU1 = math.cos(U1)
		sinU2 = math.sin(U2)
		cosU2 = math.cos(U2)

		for iteration in range(self.MAX_ITERATIONS):
			sinLambda = math.sin(Lambda)
			cosLambda = math.cos(Lambda)
			sinSigma = math.sqrt((cosU2 * sinLambda) ** 2 + (cosU1 * sinU2 - sinU1 * cosU2 * cosLambda) ** 2)

			if sinSigma == 0:
				return 0.0 # coincident points

			cosSigma = sinU1 * sinU2 + cosU1 * cosU2 * cosLambda
			sigma = math.atan2(sinSigma, cosSigma)
			sinAlpha = cosU1 * cosU2 * sinLambda / sinSigma
			cosSqAlpha = 1 - sinAlpha ** 2

			try:
				cos2SigmaM = cosSigma - 2 * sinU1 * sinU2 / cosSqAlpha
			except ZeroDivisionError:
				cos2SigmaM = 0

			C = self.f / 16 * cosSqAlpha * (4 + self.f * (4 - 3 * cosSqAlpha))
			LambdaPrev = Lambda
			Lambda = L + (1 - C) * self.f * sinAlpha * (sigma + C * sinSigma * (cos2SigmaM + C * cosSigma * (-1 + 2 * cos2SigmaM ** 2)))
			if abs(Lambda - LambdaPrev) < self.CONVERGENCE_THRESHOLD:
				break     # Successful convergence
		else:
			return None   # failure to converge

		uSq = cosSqAlpha * (self.a ** 2 - self.b ** 2) / (self.b ** 2)
		A = 1 + uSq / 16384 * (4096 + uSq * (-768 + uSq * (320 - 175 * uSq)))
		B = uSq / 1024 * (256 + uSq * (-128 + uSq * (74 - 47 * uSq)))

		deltaSigma = B * sinSigma * (cos2SigmaM + B / 4 * (cosSigma * (-1 + 2 * cos2SigmaM ** 2) - B / 6 * cos2SigmaM * (-3 + 4 * sinSigma ** 2) * (-3 + 4 * cos2SigmaM ** 2)))
		s = self.b * A * (sigma - deltaSigma)
		s /= 1000 # meters to kilometers
		if miles:
			s *= self.MILES_PER_KILOMETER
			return round(s, 6)       # miles
		else:
			return round(s*1000, 6)  # meters
