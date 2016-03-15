# coding=utf-8
"""
Unit tests for ``octoprint.util.comm``.
"""

from __future__ import absolute_import

__author__ = "Gina Häußge <osd@foosel.net>"
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'
__copyright__ = "Copyright (C) 2016 The OctoPrint Project - Released under terms of the AGPLv3 License"


from . import CommsTestCase, FakeGcodeFirmware

import octoprint.util.comm

import mock
from ddt import ddt, data, unpack


class BasicCommsTest(CommsTestCase):

	def _perform_simple_open_test(self, setting_overrides, expected_written_lines, not_written):
		# prepare
		self._mock_settings(overrides=setting_overrides)

		# run
		self._start_comm("/dev/ttyUSB0", 115200)
		self._wait_for_operational(additional=1.0)
		self._stop_comm()

		# verify
		self.serial_module.Serial.assert_called_once_with("/dev/ttyUSB0",
		                                                  115200,
		                                                  timeout=self.default_settings["serial"]["timeout"]["connection"],
		                                                  writeTimeout=10000,
		                                                  parity=octoprint.util.comm.serial.PARITY_ODD)
		self.assertEquals(self.serial.close.call_count, 2)
		self.assertEquals(self.serial.open.call_count, 1)
		self.assertEqual(self.serial.parity, octoprint.util.comm.serial.PARITY_NONE)

		expected_writes = []
		for line in expected_written_lines:
			expected_writes.append(mock.call(line + "\n"))
		self.serial.write.assert_has_calls(expected_writes, any_order=True)

		for line in not_written:
			self.assertNotIn(mock.call(line + "\n"), self.serial.write.mock_calls)


@ddt
class BasicCommsResetTest(BasicCommsTest):

	@data((dict(feature=dict(sdSupport=True,
	                         sdAlwaysAvailable=False,
	                         waitForStartOnConnect=False)),
	       ["N0 M110 N0*125",  # hello from tickling
	        "N0 M110 N0*125",  # hello from start
	        "N0 M110 N0*125",  # line number reset from connected handler
	        "M21"],
	       ["M20"]),           # sd card init from connected handler

	      # wait for start
	      (dict(feature=dict(sdSupport=True,
	                         sdAlwaysAvailable=False,
	                         waitForStartOnConnect=True)),
	       ["N0 M110 N0*125",  # hello from start
	        "N0 M110 N0*125",  # line number reset from connected handler
	        "M21"],            # sd card init from connected handler
	       ["M20"]),           # no M20 (no sd init success message)

	      # no sd
	      (dict(feature=dict(sdSupport=False,
	                         sdAlwaysAvailable=False,
	                         waitForStartOnConnect=False)),
	       ["N0 M110 N0*125",  # hello from tickling
	        "N0 M110 N0*125",  # hello from start
	        "N0 M110 N0*125"], # line number reset from connected handler
	       ["M20", "M21"]),    # no M20 or M21 (no sd card support)

	      # no sd, wait for start
	      (dict(feature=dict(sdSupport=False,
	                         sdAlwaysAvailable=False,
	                         waitForStartOnConnect=True)),
	       ["N0 M110 N0*125",  # hello from start
	        "N0 M110 N0*125"], # line number reset from connected handler
	       ["M20", "M21"]),    # no M20 or M21 (no sd card support)

	      # sd assumed available, wait for start
	      (dict(feature=dict(sdSupport=True,
	                         sdAlwaysAvailable=True,
	                         waitForStartOnConnect=True)),
	       ["N0 M110 N0*125",  # hello from start
	        "N0 M110 N0*125",  # line number reset from connected handler
	        "M21",             # sd init, no response necessary
	        "M20"],            # sd list (init assumed to be done)
	       []),
	)
	@unpack
	def test_simple_open(self, setting_overrides, expected_written_lines, not_written):
		self._perform_simple_open_test(setting_overrides, expected_written_lines, not_written)

	def _create_firmware(self):
		return FakeGcodeFirmware(self.serial, simulate_reset=True)

@ddt
class BasicCommsNoResetTest(BasicCommsTest):

	@data((dict(feature=dict(sdSupport=True,
	                         sdAlwaysAvailable=False,
	                         waitForStartOnConnect=False)),
	       ["N0 M110 N0*125",  # hello from tickling
	        "N0 M110 N0*125",  # line number reset from connected handler
	        "M21"],
	       ["M20"]),           # sd card init from connected handler

	      # no sd
	      (dict(feature=dict(sdSupport=False,
	                         sdAlwaysAvailable=False,
	                         waitForStartOnConnect=False)),
	       ["N0 M110 N0*125",  # hello from tickling
	        "N0 M110 N0*125"], # line number reset from connected handler
	       ["M20", "M21"]),    # no M20 or M21 (no sd card support)

	      # no sd
	      (dict(feature=dict(sdSupport=False,
	                         sdAlwaysAvailable=False,
	                         waitForStartOnConnect=False)),
	       ["N0 M110 N0*125",  # hello from tickling
	        "N0 M110 N0*125"], # line number reset from connected handler
	       ["M20", "M21"]),    # no M20 or M21 (no sd card support)

	      # sd assumed available
	      (dict(feature=dict(sdSupport=True,
	                         sdAlwaysAvailable=True,
	                         waitForStartOnConnect=False)),
	       ["N0 M110 N0*125",  # hello from tickling
	        "N0 M110 N0*125",  # line number reset from connected handler
	        "M21",             # sd init, no response necessary
	        "M20"],            # sd list (init assumed to be done)
	       []),
	)
	@unpack
	def test_simple_open(self, setting_overrides, expected_written_lines, not_written):
		self._perform_simple_open_test(setting_overrides, expected_written_lines, not_written)

	def _create_firmware(self):
		return FakeGcodeFirmware(self.serial, simulate_reset=False)
