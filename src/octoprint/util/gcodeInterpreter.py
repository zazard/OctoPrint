# coding=utf-8
from __future__ import absolute_import
__author__ = "Gina Häußge <osd@foosel.net> based on work by David Braam"
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'
__copyright__ = "Copyright (C) 2013 David Braam, Gina Häußge - Released under terms of the AGPLv3 License"


import math
import os
import base64
import zlib
import logging

from octoprint.settings import settings


class Vector3D(object):
	"""
	3D vector value

	Supports addition, subtraction and multiplication with a scalar value (float, int) as well as calculating the
	length of the vector.

	Examples:

	>>> a = Vector3D(1.0, 1.0, 1.0)
	>>> b = Vector3D(4.0, 4.0, 4.0)
	>>> a + b == Vector3D(5.0, 5.0, 5.0)
	True
	>>> b - a == Vector3D(3.0, 3.0, 3.0)
	True
	>>> abs(a - b) == Vector3D(3.0, 3.0, 3.0)
	True
	>>> a * 2 == Vector3D(2.0, 2.0, 2.0)
	True
	>>> a * 2 == 2 * a
	True
	>>> a.length == math.sqrt(a.x ** 2 + a.y ** 2 + a.z ** 2)
	True
	>>> copied_a = Vector3D(a)
	>>> a == copied_a
	True
	>>> copied_a.x == a.x and copied_a.y == a.y and copied_a.z == a.z
	True
	"""

	def __init__(self, *args, **kwargs):
		self.x = kwargs.get("x", 0.0)
		self.y = kwargs.get("y", 0.0)
		self.z = kwargs.get("z", 0.0)

		if len(args) == 3:
			self.x = args[0]
			self.y = args[1]
			self.z = args[2]

		elif len(args) == 1:
			# copy constructor
			other = args[0]
			if not isinstance(other, Vector3D):
				raise ValueError("Object to copy must be a Vector3D instance")

			self.x = other.x
			self.y = other.y
			self.z = other.z

	@property
	def length(self):
		return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

	def __add__(self, other):
		if isinstance(other, Vector3D):
			return Vector3D(self.x + other.x,
			                self.y + other.y,
			                self.z + other.z)
		elif isinstance(other, (tuple, list)) and len(other) == 3:
			return Vector3D(self.x + other[0],
			                self.y + other[1],
			                self.z + other[2])
		else:
			raise ValueError("other must be a Vector3D instance or a list or tuple of length 3")

	def __sub__(self, other):
		if isinstance(other, Vector3D):
			return Vector3D(self.x - other.x,
			                self.y - other.y,
			                self.z - other.z)
		elif isinstance(other, (tuple, list)) and len(other) == 3:
			return Vector3D(self.x - other[0],
			                self.y - other[1],
			                self.z - other[2])
		else:
			raise ValueError("other must be a Vector3D instance or a list or tuple")

	def __mul__(self, other):
		if isinstance(other, (int, float)):
			return Vector3D(self.x * other,
			                self.y * other,
			                self.z * other)
		else:
			raise ValueError("other must be a float or int value")

	def __rmul__(self, other):
		return self.__mul__(other)

	def __neg__(self):
		return Vector3D(-self.x, -self.y, -self.z)

	def __abs__(self):
		return Vector3D(abs(self.x), abs(self.y), abs(self.z))

	def __eq__(self, other):
		if not isinstance(other, Vector3D):
			return False
		return self.x == other.x and self.y == other.y and self.z == other.z

	def __str__(self):
		return "Vector3D(x={}, y={}, z={}, length={})".format(self.x, self.y, self.z, self.length)


class MinMax3D(object):
	"""
	Tracks minimum and maximum of recorded values

	Examples:

	>>> minmax = MinMax3D()
	>>> minmax.record(Vector3D(2.0, 2.0, 2.0))
	>>> minmax.min.x == 2.0 == minmax.max.x and minmax.min.y == 2.0 == minmax.max.y and minmax.min.z == 2.0 == minmax.max.z
	True
	>>> minmax.record(Vector3D(1.0, 2.0, 3.0))
	>>> minmax.min.x == 1.0 and minmax.min.y == 2.0 and minmax.min.z == 2.0
	True
	>>> minmax.max.x == 2.0 and minmax.max.y == 2.0 and minmax.max.z == 3.0
	True
	>>> minmax.size == Vector3D(1.0, 0.0, 1.0)
	True
	"""

	def __init__(self):
		self.min = Vector3D(None, None, None)
		self.max = Vector3D(None, None, None)

	def record(self, coordinate):
		for c in ("x", "y", "z"):
			current_min = getattr(self.min, c)
			current_max = getattr(self.max, c)
			value = getattr(coordinate, c)
			setattr(self.min, c, value if current_min is None or value < current_min else current_min)
			setattr(self.max, c, value if current_max is None or value > current_max else current_max)

	@property
	def size(self):
		return abs(self.max - self.min)


class AnalysisAborted(Exception):
	pass


class gcode(object):
	def __init__(self):
		self._logger = logging.getLogger(__name__)
		self.layerList = None
		self.extrusionAmount = [0]
		self.extrusionVolume = [0]
		self.totalMoveTimeMinute = 0
		self.filename = None
		self.progressCallback = None
		self._abort = False
		self._filamentDiameter = 0
		self._minMax = MinMax3D()

	@property
	def dimensions(self):
		size = self._minMax.size
		return dict(width=size.x,
		            depth=size.y,
		            height=size.z)

	@property
	def printing_area(self):
		return dict(minX=self._minMax.min.x,
		            minY=self._minMax.min.y,
		            minZ=self._minMax.min.z,
		            maxX=self._minMax.max.x,
		            maxY=self._minMax.max.y,
		            maxZ=self._minMax.max.z)

	def load(self, filename, printer_profile, throttle=None):
		if os.path.isfile(filename):
			self.filename = filename
			self._fileSize = os.stat(filename).st_size

			import codecs
			with codecs.open(filename, encoding="utf-8", errors="replace") as f:
				self._load(f, printer_profile, throttle=throttle)

	def abort(self):
		self._abort = True

	def _load(self, gcodeFile, printer_profile, throttle=None):
		filePos = 0
		readBytes = 0
		class memory:
			pos = Vector3D(0.0, 0.0, 0.0)
			posOffset = Vector3D(0.0, 0.0, 0.0)
			currentE = [0.0]
			totalExtrusion = [0.0]
			maxExtrusion = [0.0]
			currentExtruder = 0
			totalMoveTimeMinute = 0.0
			absoluteE = True
			scale = 1.0
			posAbs = True
			fwretractTime = 0
			fwretractDist = 0
			fwrecoverTime = 0
			feedrate_multiplicator = 1.0
			flowrate_multiplicator = 1.0
			feedrate = min(printer_profile["axes"]["x"]["speed"], printer_profile["axes"]["y"]["speed"])
			if feedrate == 0:
				# some somewhat sane default if axes speeds are insane...
				feedrate = 2000
			offsets = printer_profile["extruder"]["offsets"]
			mm_per_arc_segment = 1
			n_arc_correction = 25


		def g0_g1_command(x, y, z, e, f):
			oldPos = memory.pos
			newPos = Vector3D(x if x is not None else memory.pos.x,
							  y if y is not None else memory.pos.y,
							  z if z is not None else memory.pos.z)

			if memory.posAbs:
				memory.pos = newPos * memory.scale + memory.posOffset
			else:
				memory.pos += newPos * memory.scale
			if f is not None and f != 0:
				memory.feedrate = f

			if e is not None:
				if memory.absoluteE:
					# make sure e is relative
					e -= memory.currentE[memory.currentExtruder]
				# If move includes extrusion, calculate new min/max coordinates of model
				if e > 0.0:
					# extrusion -> relevant for print area & dimensions
					self._minMax.record(memory.pos)
					memory.totalExtrusion[memory.currentExtruder] += e
					memory.currentE[memory.currentExtruder] += e
					memory.maxExtrusion[memory.currentExtruder] = max(memory.maxExtrusion[memory.currentExtruder],
															   memory.totalExtrusion[memory.currentExtruder])
			else:
				e = 0.0

			# move time in x, y, z, will be 0 if no movement happened
			moveTimeXYZ = abs((oldPos - memory.pos).length / memory.feedrate)

			# time needed for extruding, will be 0 if no extrusion happened
			extrudeTime = abs(e / memory.feedrate)

			# time to add is maximum of both
			memory.totalMoveTimeMinute += max(moveTimeXYZ, extrudeTime)

		def g2_g3_command(target, offset, e, f, clockwise):
			radius = math.hypot(offset.x, offset.y)
			center = memory.pos + offset
			extruder_travel = e
			if memory.absoluteE:
				extruder_travel -= memory.currentE[memory.currentExtruder]

			r_axis = -offset
			rt_axis = target - center

			angular_travel = math.atan2(r_axis.x * rt_axis.y - r_axis.y * rt_axis.x,
										r_axis.x * rt_axis.x + r_axis.y * rt_axis.y)
			if (not clockwise and angular_travel <= 0.00001) or (clockwise and angular_travel < -0.000001):
				angular_travel += 2.0 * math.pi
			if clockwise:
				angular_travel -= 2.0 * math.pi

			if self._memory.position == target and angular_travel == 0:
				angular_travel += 2.0 * math.pi

			mm_of_travel = math.fabs(angular_travel) * radius
			if mm_of_travel < 0.001:
				return

			segments = int(math.floor(mm_of_travel / memory.mm_per_arc_segment))
			if segments == 0:
				segments = 1

			theta_per_segment = angular_travel / segments
			extrude_per_segment = extruder_travel / segments

			cos_t = 1 - 0.5 * theta_per_segment * theta_per_segment
			sin_t = theta_per_segment

			arc_target = Vector3D(0.0, 0.0, 0.0)

			e_target = memory.currentE[memory.currentExtruder] if memory.absoluteE else 0

			count = 0
			for i in range(1, segments):
				if count < memory.n_arc_correction:
					r_axis = Vector3D(r_axis.x * cos_t - r_axis.y * sin_t, r_axis.x * sin_t + r_axis.y * cos_t,
									  r_axis.z)
					count += 1
				else:
					cos_ti = math.cos(i * theta_per_segment)
					sin_ti = math.sin(i * theta_per_segment)
					r_axis = Vector3D(-offset.x * cos_ti + offset.y * sin_ti, -offset.x * sin_ti - offset.y * cos_ti)
					count = 0

				arc_target.x = center.x + r_axis.x
				arc_target.y = center.y + r_axis.y
				e_target += extrude_per_segment

				g0_g1_command(arc_target.x, arc_target.y, memory.pos.z, e_target, f)

			g0_g1_command(target.x, target.y, memory.pos.z, e, f)

		for line in gcodeFile:
			if self._abort:
				raise AnalysisAborted()
			filePos += 1
			readBytes += len(line)

			if isinstance(gcodeFile, (file)):
				percentage = float(readBytes) / float(self._fileSize)
			elif isinstance(gcodeFile, (list)):
				percentage = float(filePos) / float(len(gcodeFile))
			else:
				percentage = None

			try:
				if self.progressCallback is not None and (filePos % 1000 == 0) and percentage is not None:
					self.progressCallback(percentage)
			except:
				pass

			if ';' in line:
				comment = line[line.find(';')+1:].strip()
				if comment.startswith("filament_diameter"):
					filamentValue = comment.split("=", 1)[1].strip()
					try:
						self._filamentDiameter = float(filamentValue)
					except ValueError:
						try:
							self._filamentDiameter = float(filamentValue.split(",")[0].strip())
						except ValueError:
							self._filamentDiameter = 0.0
				elif comment.startswith("CURA_PROFILE_STRING") or comment.startswith("CURA_OCTO_PROFILE_STRING"):
					if comment.startswith("CURA_PROFILE_STRING"):
						prefix = "CURA_PROFILE_STRING:"
					else:
						prefix = "CURA_OCTO_PROFILE_STRING:"

					curaOptions = self._parseCuraProfileString(comment, prefix)
					if "filament_diameter" in curaOptions:
						try:
							self._filamentDiameter = float(curaOptions["filament_diameter"])
						except:
							self._filamentDiameter = 0.0
				line = line[0:line.find(';')]

			G = getCodeInt(line, 'G')
			M = getCodeInt(line, 'M')
			T = getCodeInt(line, 'T')

			if G is not None:
				if G == 0 or G == 1:	#Move
					x = getCodeFloat(line, 'X')
					y = getCodeFloat(line, 'Y')
					z = getCodeFloat(line, 'Z')
					e = getCodeFloat(line, 'E')
					f = getCodeFloat(line, 'F')

					if e is not None:
						e *= memory.flowrate_multiplicator

					if f is not None:
						f *= memory.feedrate_multiplicator

					g0_g1_command(x, y, z, e, f)
				elif G == 2 or G == 3:
					x = getCodeFloat(line, 'X')
					y = getCodeFloat(line, 'Y')
					i = getCodeFloat(line, 'I')
					j = getCodeFloat(line, 'J')

					e = getCodeFloat(line, 'E')
					f = getCodeFloat(line, 'F')

					if e is not None:
						e *= memory.flowrate_multiplicator

					if f is not None:
						f *= memory.feedrate_multiplicator

					g2_g3_command(Vector3D(x, y, memory.pos.z), Vector3D(i, j, 0.0), e, f, G == 2)
				elif G == 4:	#Delay
					S = getCodeFloat(line, 'S')
					if S is not None:
						memory.totalMoveTimeMinute += S / 60.0
					P = getCodeFloat(line, 'P')
					if P is not None:
						memory.totalMoveTimeMinute += P / 60.0 / 1000.0
				elif G == 10:   #Firmware retract
					memory.totalMoveTimeMinute += memory.fwretractTime
				elif G == 11:   #Firmware retract recover
					memory.totalMoveTimeMinute += memory.fwrecoverTime
				elif G == 20:	#Units are inches
					memory.scale = 25.4
				elif G == 21:	#Units are mm
					memory.scale = 1.0
				elif G == 28:	#Home
					x = getCodeFloat(line, 'X')
					y = getCodeFloat(line, 'Y')
					z = getCodeFloat(line, 'Z')
					center = Vector3D(0.0, 0.0, 0.0)
					if x is None and y is None and z is None:
						memory.pos = center
					else:
						memory.pos = Vector3D(center.x if x is not None else memory.pos.x,
											  center.y if y is not None else memory.pos.y,
									          center.z if z is not None else memory.pos.z)
				elif G == 90:	#Absolute position
					memory.posAbs = True
				elif G == 91:	#Relative position
					memory.posAbs = False
				elif G == 92:
					x = getCodeFloat(line, 'X')
					y = getCodeFloat(line, 'Y')
					z = getCodeFloat(line, 'Z')
					e = getCodeFloat(line, 'E')
					if e is not None:
						memory.currentE[memory.currentExtruder] = e

						memory.posOffset = Vector3D((memory.pos.x - x) if x is not None else memory.posOffset.x,
													(memory.pos.y - y) if y is not None else memory.posOffset.y,
													(memory.pos.z - z) if z is not None else memory.posOffset.z)
			elif M is not None:
				if M == 82:   #Absolute E
					memory.absoluteE = True
				elif M == 83:   #Relative E
					memory.absoluteE = False
				elif M == 207 or M == 208: #Firmware retract settings
					s = getCodeFloat(line, 'S')
					f = getCodeFloat(line, 'F')
					if s is not None and f is not None:
						if M == 207:
							memory.fwretractTime = s / f
							memory.fwretractDist = s
						else:
							memory.fwrecoverTime = (memory.fwretractDist + s) / f
				elif M == 220:
					memory.feedrate_multiplicator = getCodeInt(line, 'S') / 100.0
				elif M == 221:
					memory.flowrate_ultiplicator = getCodeInt(line, 'S') / 100.0

			elif T is not None:
				if T > settings().getInt(["gcodeAnalysis", "maxExtruders"]):
					self._logger.warn("GCODE tried to select tool %d, that looks wrong, ignoring for GCODE analysis" % T)
				else:
					memory.posOffset -= Vector3D(memory.offsets[memory.currentExtruder][0] if memory.currentExtruder < len(memory.offsets) else 0.0,
												 memory.offsets[memory.currentExtruder][1] if memory.currentExtruder < len(memory.offsets) else 0.0,
										         0.0)

					memory.currentExtruder = T

					memory.posOffset += Vector3D(memory.offsets[memory.currentExtruder][0] if memory.currentExtruder < len(memory.offsets) else 0.0,
												 memory.offsets[memory.currentExtruder][1] if memory.currentExtruder < len(memory.offsets) else 0.0,
										         0.0)

					if len(memory.currentE) <= memory.currentExtruder:
						for i in range(len(memory.currentE), memory.currentExtruder + 1):
							memory.currentE.append(0.0)
					if len(memory.maxExtrusion) <= memory.currentExtruder:
						for i in range(len(memory.maxExtrusion), memory.currentExtruder + 1):
							memory.maxExtrusion.append(0.0)
					if len(memory.totalExtrusion) <= memory.currentExtruder:
						for i in range(len(memory.totalExtrusion), memory.currentExtruder + 1):
							memory.totalExtrusion.append(0.0)

			if throttle is not None:
				throttle()

		if self.progressCallback is not None:
			self.progressCallback(100.0)

		self.extrusionAmount = memory.maxExtrusion
		self.extrusionVolume = [0] * len(memory.maxExtrusion)
		for i in range(len(memory.maxExtrusion)):
			radius = self._filamentDiameter / 2
			self.extrusionVolume[i] = (self.extrusionAmount[i] * (math.pi * radius * radius)) / 1000
		self.totalMoveTimeMinute = memory.totalMoveTimeMinute

	def _parseCuraProfileString(self, comment, prefix):
		return {key: value for (key, value) in map(lambda x: x.split("=", 1), zlib.decompress(base64.b64decode(comment[len(prefix):])).split("\b"))}

def getCodeInt(line, code):
	n = line.find(code) + 1
	if n < 1:
		return None
	m = line.find(' ', n)
	try:
		if m < 0:
			return int(line[n:])
		return int(line[n:m])
	except:
		return None


def getCodeFloat(line, code):
	import math
	n = line.find(code) + 1
	if n < 1:
		return None
	m = line.find(' ', n)
	try:
		if m < 0:
			val = float(line[n:])
		else:
			val = float(line[n:m])
		return val if not (math.isnan(val) or math.isinf(val)) else None
	except:
		return None
