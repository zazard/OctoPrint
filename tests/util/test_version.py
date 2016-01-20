# coding=utf-8
from __future__ import absolute_import

__author__ = "Gina Häußge <osd@foosel.net>"
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'
__copyright__ = "Copyright (C) 2015 The OctoPrint Project - Released under terms of the AGPLv3 License"


import unittest
import ddt
import mock

from octoprint.util.version import version_matches_spec, version_matches_any_spec, octoprint_version_matches, parse_version


@ddt.ddt
class VersionUtilTest(unittest.TestCase):

	@ddt.data(("1.2.0",         "foo>=1.2.0,<1.3.0", None,  False, True),
	          ("1.2.0",         "foo>=1.3.0",        None,  False, False),
	          ("1.2.0-dev-405", "foo>=1.2.0",        None,  True,  True),
	          ("1.2.0.dev.405", "foo>=1.2.0",        None,  False, False),
	          ("1.2.0.dev.405", "foo>=1.2.0",        None,  True,  True),
	          ("1.2.0",         ">=1.2.0,<1.3.0",    "foo", False, True),
	          ("1.2.0",         "FoO>=1.2.0,<1.3.0", "foo", False, True),
	          ("1.2.0",         ">=1.2.0,<1.3.0",    None,  False, ValueError),
	          ("1.2.fnord",     ">=1.2.0",           None,  False, ValueError)
	)
	@ddt.unpack
	def test_version_matches_spec(self, version, spec, package, base, expected):
		self.assertExpected(version_matches_spec, (version, spec), dict(package=package, base=base), expected)

	def test_version_matches_any_spec(self):
		self.assertTrue(version_matches_any_spec("1.2.0", [">=1.1.0,<1.2.0", ">=1.2.0,<1.3.0", "==1.3.0"], package="foo"))

	def test_version_matches_any_spec_nomatch(self):
		self.assertFalse(version_matches_any_spec("1.2.0", [">=1.1.0,<1.2.0", "==1.3.0"], package="foo"))

	@ddt.data((">=1.2.0,<1.3.0", False, "1.2.0",         True),
	          (">=1.2.0,<1.3.0", False, "1.3.0.dev.123", False),
	          (">=1.2.0,<1.3.0", False, "1.2.0.dev.123", False),
	          (">=1.2.0,<1.3.0", True,  "1.2.0.dev.123", True))
	@ddt.unpack
	def test_octoprint_version_matches(self, spec, base, mocked_version, expected):
		import octoprint
		old_version = octoprint.__version__
		try:
			octoprint.__version__ = mocked_version
			self.assertExpected(octoprint_version_matches, (spec,), dict(base=base), expected)
		finally:
			octoprint.__version__ = old_version

	@ddt.data(("1.2.0",         False, "1.2.0",         ("00000001", "00000002", "00000000", "*final"),                   ("00000001", "00000002", "00000000", "*final"),                   "1.2.0"),
	          ("1.2.0-dev-123", False, "1.2.0",         ("00000001", "00000002", "00000000", "*final"),                   ("00000001", "00000002", "00000000", "*final"),                   "1.2.0"),
	          ("1.2.0-dev-123", True,  "1.2.0",         ("00000001", "00000002", "00000000", "*final"),                   ("00000001", "00000002", "00000000", "*final"),                   "1.2.0"),
	          ("1.2.0.dev.123", False, "1.2.0.dev.123", ("00000001", "00000002", "00000000", "*@", "00000123", "*final"), ("00000001", "00000002", "00000000", "*@", "00000123", "*final"), "1.2.0"),
	          ("1.2.0.dev.123", True,  "1.2.0.dev.123", ("00000001", "00000002", "00000000", "*@", "00000123", "*final"), ("00000001", "00000002", "00000000", "*final"),                   "1.2.0"))
	@ddt.unpack
	def test_parse_version(self, version, base, stripped_version, mocked_tuple, expected_tuple, mocked_base_version):
		mocked_obj = mock.MagicMock()
		mocked_obj.base_version = mocked_base_version

		# old setuptools return a tuple for parse_version, we simulate that here
		with mock.patch("pkg_resources.parse_version") as mocked_parse_version:
			mocked_parse_version.return_value = mocked_tuple

			result = parse_version(version, base=base)
			self.assertEqual(expected_tuple, result)

			mocked_parse_version.assert_called_with(stripped_version)

		# newer setuptools return a version object, we simulate that here
		with mock.patch("pkg_resources.parse_version") as mocked_parse_version:
			mocked_parse_version.return_value = mocked_obj

			result = parse_version(version, base=base)
			self.assertEqual(mocked_obj, result)

			expected_calls = [mock.call(stripped_version)]
			if base:
				expected_calls.append(mock.call(mocked_base_version))

			self.assertListEqual(expected_calls, mocked_parse_version.call_args_list)

	def assertExpected(self, callable, args, kwargs, expected):
		"""
		Helper for checking the return value against an expected one.

		Maybe an exception class in which case a try-catch-block is created and a test for the correct
		exception is set up.
		"""

		if isinstance(expected, type) and issubclass(expected, Exception):
			try:
				callable(*args, **kwargs)
				self.fail("Expected {}".format(expected))
			except Exception as e:
				if not isinstance(e, expected):
					self.fail("Expected exception of type {}, got {} instead".format(expected, e.__class__.__name__))
		else:
			self.assertEqual(expected, callable(*args, **kwargs))
