# coding=utf-8
"""
Unit tests for ``octoprint.util.comm``.
"""

from __future__ import absolute_import

__author__ = "Gina Häußge <osd@foosel.net>"
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'
__copyright__ = "Copyright (C) 2016 The OctoPrint Project - Released under terms of the AGPLv3 License"


from collections import deque
import Queue as queue
import re
import time
import threading

import unittest
import mock


import octoprint.util.comm


class FakeBareboneFirmware(object):

	def __init__(self, serial_mock):
		self.serial_mock = serial_mock

		self.serial_mock.readline.side_effect = self.readline
		self.serial_mock.write.side_effect = self.write

		self.on_receive = None

		self.outgoing = queue.Queue()
		self.incoming = queue.Queue()

		self._written = deque([])
		self._read = deque([])

		self._conditioned_answers = []

		self._produce_read_timeout = 0
		self._produce_write_timeout = 0
		self._finishing = False

		self._receive_lock = threading.Lock()

	def produce_read_timeout(self):
		self._produce_read_timeout = True

	def readline(self):
		line = self._get_next_line()
		self._read.append(line)
		return line

	def write(self, data):
		with self._receive_lock:
			if self._finishing:
				return

			if self._produce_write_timeout:
				self._produce_write_timeout -= 1
				if self._produce_write_timeout <= 0:
					self._produce_write_timeout = 0
				import serial
				raise serial.SerialTimeoutException()

			self._written.append(data)
			self._on_received_data(data)

			for condition, lines in self._conditioned_answers:
				if callable(condition) and condition(data):
					self.return_lines(*lines)

	def assert_written(self, *data):
		if not data:
			return True

		all_written = list(self._written)
		while all_written:
			written = all_written[0]
			if written == data[0]:
				break
			all_written.pop(0)
		else:
			raise AssertionError("{!r} is not contained in written data".format(data))

		return self._check_written(all_written, data)

	def assert_written_exactly(self, *data):
		if not data:
			return True

		all_written = list(self._written)
		return self._check_written(all_written, data)

	def return_lines(self, *lines):
		for line in lines:
			if not line.endswith("\n"):
				line += "\n"
			self.outgoing.put(line)

	def return_lines_if(self, condition, *lines):
		self._conditioned_answers.append((condition, lines))

	def finish(self):
		self._finishing = True
		self.outgoing.join()

	def _check_written(self, expected, actual):
		zipped = zip(expected, actual)
		for a, b in zipped:
			assert a == b
		return True

	def _get_next_line(self):
		if self._produce_read_timeout:
			self._produce_read_timeout -= 1
			if self._produce_read_timeout <= 0:
				self._produce_read_timeout = 0
			return ""

		try:
			line = self.outgoing.get(timeout=self.serial_mock.timeout)
			self.outgoing.task_done()
			return line
		except queue.Empty:
			return ""

	def _on_received_data(self, data):
		if callable(self.on_receive):
			return self.on_receive(self, data)
		return False


class FakeGcodeFirmware(FakeBareboneFirmware):

	command_regex = re.compile("^([GMTF])(\d+)")

	def __init__(self, serial_mock, simulate_reset=True, require_checksum=False):
		FakeBareboneFirmware.__init__(self, serial_mock)

		self._require_checksum = require_checksum
		self._line_number = 0

		if simulate_reset:
			self.return_lines("start")
		else:
			import random
			self._line_number = random.randrange(1, stop=2342)

	def _on_received_data(self, data):
		print("firmware - received data: {!r}".format(data))

		if FakeBareboneFirmware._on_received_data(self, data):
			return True

		data = data.strip()

		# strip checksum
		if "*" in data:
			pos = data.rfind("*")
			checksum = int(data[pos+1:])
			data = data[:pos]

			if checksum != self._get_checksum(data):
				self._trigger_resend(checksum_wrong=True)
				return True

		elif self._require_checksum:
			self.return_lines("Error: Missing checksum")
			return True

		# track line numbers
		if "N" in data and "M110" in data:
			linenumber = int(re.search("N([0-9]+)", data).group(1))
			self._line_number = linenumber
			self._trigger_ok()
			return True

		elif data.startswith("N"):
			match = re.search("N([0-9]+)", data)

			prefix = match.group(0)
			linenumber = int(match.group(1))
			expected = self._line_number + 1
			if linenumber != expected:
				self._trigger_resend(expected=expected, actual=linenumber)
				return True

			self._line_number = linenumber
			data = data[len(prefix):].strip()

		if self._process_line(data):
			self._trigger_ok()

		return True

	def _trigger_ok(self):
		print("firmware - sending ok")
		self.return_lines("ok")

	def _trigger_resend(self, checksum_wrong=False, actual=None, expected=None):
		if expected is None:
			expected = self._line_number + 1

		if actual is not None:
			print("firmware - Triggering resend for expected line incl. ok")
			self.return_lines("Error: expected line {} got {}".format(expected, actual),
			                  "Resend: {}".format(expected),
			                  "ok")

		elif checksum_wrong:
			print("firmware - Triggering resend for wrong checksum incl. ok")
			self.return_lines("Error: Wrong checksum",
			                  "Resend: {}".format(expected),
			                  "ok")

	def _process_line(self, line):
		command_match = self.command_regex.match(line)

		if command_match is None:
			return False

		command = command_match.group(0)
		letter = command_match.group(1)

		# if we have a method _gcode_G, _gcode_M or _gcode_T, execute that first
		letter_handler = "_gcode_{}".format(letter)
		if hasattr(self, letter_handler):
			code = command_match.group(2)
			handled = getattr(self, letter_handler)(code, line)
			if handled:
				return False

		# then look for a method _gcode_<command> and execute that if it exists
		command_handler = "_gcode_{}".format(command)
		if hasattr(self, command_handler):
			handled = getattr(self, command_handler)(line)
			if handled:
				return False

		return True

	@staticmethod
	def _get_checksum(line):
		checksum = 0
		for c in line:
			checksum ^= ord(c)
		return checksum


class CommCallbackHelper(octoprint.util.comm.MachineComPrintCallback):

	def __init__(self):
		self._states = deque([])

		import threading
		self._state_change_event = threading.Event()

	def wait_for_state(self, *states, **kwargs):
		import octoprint.util.comm

		timeout = kwargs.get("timeout", 10)

		if not states:
			return True

		offset = len(self._states)

		while True:
			if not self._state_change_event.wait(timeout=timeout):
				raise AssertionError("Timeout while waiting for any of states {}".format(states))
			current_states = list(self._states)[offset:]
			if current_states:
				current_state = current_states[-1]
				if current_state in states:
					return True
				elif current_state in (octoprint.util.comm.MachineCom.STATE_ERROR,
				                       octoprint.util.comm.MachineCom.STATE_CLOSED_WITH_ERROR,
				                       octoprint.util.comm.MachineCom.STATE_CLOSED):
					raise AssertionError("Didn't get any of states {} but an error/a close instead: {}".format(states, current_state))


	def on_comm_state_change(self, state):
		self._states.append(state)
		self._state_change_event.set()

	def on_comm_log(self, message):
		print("on_comm_log - {:.3f}: {}".format(time.time(), message))

	def assert_states(self, *states):
		all_states = list(self._states)

		while all_states:
			state = all_states[0]
			if state == states[0]:
				break
			all_states.pop(0)
		else:
			raise AssertionError("{!r} is not contained in states".format(states))

		return self._check_states(states, all_states)

	def assert_states_exactly(self, *states):
		all_states = list(self._states)
		return self._check_states(states, all_states)

	def _check_states(self, expected, actual):
		zipped = zip(expected, actual)
		for a, b in zipped:
			assert a == b
		return True


class CommsTestCase(unittest.TestCase):

	def setUp(self):
		import serial
		from octoprint.settings import default_settings
		from octoprint.printer.profile import PrinterProfileManager

		self.default_settings = default_settings

		# mock serial
		self.serial_patcher = mock.patch("octoprint.util.comm.serial")
		self.serial_module = self.serial_patcher.start()
		self.serial_module.Serial = mock.MagicMock()

		self.serial = mock.MagicMock(spec=serial.Serial)
		def constructor(*args, **kwargs):
			self.serial.timeout = kwargs.get("timeout", None)
			return self.serial
		self.serial_module.Serial.side_effect = constructor

		# mock settings
		self.settings_patcher = mock.patch("octoprint.util.comm.settings")
		settings = self.settings_patcher.start()
		self.settings = settings.return_value
		self._mock_settings()

		# mock plugin manager
		self.plugin_manager_patcher = mock.patch("octoprint.plugin.plugin_manager")
		self.plugin_manager = self.plugin_manager_patcher.start()
		self._mock_hooks()

		# mock printer profile manager
		self.printer_profile_manager = mock.MagicMock(spec=PrinterProfileManager)
		self.printer_profile_manager.get_current_or_default.return_value = dict(heatedBed=False,
		                                                                        extruder=dict(count=1))

		# fake firmware
		self.firmware = self._create_firmware()

		# comm callback helper
		self.callback = CommCallbackHelper()

	def tearDown(self):
		self.plugin_manager_patcher.stop()
		self.settings_patcher.stop()
		self.serial_patcher.stop()

	def _start_comm(self, port, baudrate):
		self.comm = octoprint.util.comm.MachineCom(port=port,
		                                           baudrate=baudrate,
		                                           callbackObject=self.callback,
		                                           printerProfileManager=self.printer_profile_manager)
		return self.comm

	def _stop_comm(self, timeout=10.0):
		self.firmware.finish()
		self.comm.close(timeout=timeout)

	def _wait_for_operational(self, additional=0.0):
		self.callback.wait_for_state(octoprint.util.comm.MachineCom.STATE_OPERATIONAL)
		time.sleep(additional)

	def _create_firmware(self):
		return FakeGcodeFirmware(self.serial)

	def _mock_hooks(self, hooks=None):
		if hooks == None:
			hooks = dict()

		def get_hooks(hook):
			return hooks.get(hook, dict())
		self.plugin_manager.return_value.get_hooks.side_effect = get_hooks

	def _mock_settings(self, overrides=None):
		from octoprint.util import dict_merge
		merged = dict_merge(self.default_settings, overrides)

		def get(path, *args, **kwargs):
			if len(path) == 3 and path[0:2] == ["serial", "timeout"]:
				first, second, third = path
				if first not in ("serial", "feature"):
					return None
				return merged[first][second][third]
			elif len(path) == 2:
				first, second = path
				if first not in ("serial", "feature"):
					return None
				return merged[first][second]
			else:
				return None

		def getBoolean(path, *args, **kwargs):
			return get(path, *args, **kwargs)

		def getFloat(path, *args, **kwargs):
			return get(path, *args, **kwargs)

		self.settings.get.side_effect = get
		self.settings.getFloat.side_effect = getFloat
		self.settings.getBoolean.side_effect = getBoolean
