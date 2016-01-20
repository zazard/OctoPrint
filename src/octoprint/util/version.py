# coding=utf-8
from __future__ import absolute_import, unicode_literals

__author__ = "Gina Häußge <osd@foosel.net>"
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'
__copyright__ = "Copyright (C) 2016 The OctoPrint Project - Released under terms of the AGPLv3 License"


import pkg_resources


def parse_version(version_string, base=False):
	"""
	Parses the given ``version_string`` using ``pkg_resources.parse_version``

	If ``base`` is ``True``, the version will be reduced to the base version (e.g. ``1.2.0.dev.123`` will be reduced
	to ``1.2.0``) before returning.

	If a ``-`` is contains in the version string, it and any following parts of the version stirng will be stripped
	(e.g. ``1.2.0-dev-123`` is turned into ``1.2.0``) to ensure the string is parsable using ``pkg_resources``.

	Parameters:
	    version_string (str, unicode): the version string to parse
	    base (boolean): whether to reduce the version to the base version before returning

	Returns:
	    (tuple or object): the parsed version, as either a tuple or a ``setuptools`` version object, depending on the
	        installed ``setuptools`` version
	"""

	assert isinstance(version_string, basestring)

	if "-" in version_string:
		version_string = version_string[:version_string.find("-")]

	try:
		version = pkg_resources.parse_version(version_string)
	except:
		raise ValueError("Invalid version: {!r}".format(version_string))

	if base:
		if isinstance(version, tuple):
			# old setuptools
			base_version = []
			for part in version:
				if part.startswith("*"):
					break
				base_version.append(part)
			base_version.append("*final")
			version = tuple(base_version)
		else:
			# new setuptools
			version = pkg_resources.parse_version(version.base_version)
	return version


def version_matches_any_spec(version, specs, package=None, base=False):
	"""
	Checks if the supplied version matches any of the supplied specs.

	See `Requirements Parsing <https://pythonhosted.org/setuptools/pkg_resources.html#requirements-parsing>`_ for
	details on the format. The version spec does not need to start with ``package``, it will be added automatically
	if it's missing.

	Example::
	    >>> version_matches_any_spec("1.2.0", ["Foo>=1.1.0,<1.2.0", "Foo>=1.2.0,<1.3.0", "Foo>=1.3.0"])
	    True
	    >>> version_matches_any_spec("1.2.0", ["Foo>=1.1.0,<1.2.0", "Foo>=1.3.0"])
	    False

	Arguments:
	    version (str, unicode, parsed version): version to check
	    specs (list of str or unicode): version specs to check against
	    package (str or unicode): name of the package to use in the spec
	    base (boolean): If True, only check the base version of the version against the spec. Defaults
	        to False.

	Returns:
	    (boolean) True if the version matches any of the version specs, False otherwise.
	"""

	if isinstance(version, basestring):
		version = parse_version(version, base=base)

	for spec in specs:
		if package is not None and not spec.lower().startswith(package.lower()):
			spec = package.lower() + spec

		try:
			parsed_spec = next(pkg_resources.parse_requirements(spec))
		except:
			raise ValueError("Invalid spec: {!r}".format(spec))

		if version in parsed_spec:
			return True
	else:
		return False


def version_matches_spec(version, spec, package=None, base=False):
	"""
	Checks if the supplied version matches the supplied spec.

	See `Requirements Parsing <https://pythonhosted.org/setuptools/pkg_resources.html#requirements-parsing>`_ for
	details on the format. The version spec does not need to start with ``package``, it will be added automatically
	if it's missing.

	Example::
	    >>> version_matches_spec("1.2.0", "Foo>=1.2.0,<1.3.0")
	    True
	    >>> version_matches_spec("1.2.0", "Foo>=1.3.0")
	    False
	    >>> version_matches_spec("1.2.0", ">=1.2.0,<1.3.0", package="Foo")
	    True
	    >>> version_matches_spec("1.2.0.dev.123", ">=1.2.0", package="Foo")
	    False
	    >>> version_matches_spec("1.2.0.dev.123", ">=1.2.0", package="Foo", base=True)
	    True

	Arguments:
	    version (str, unicode, parsed version): version to check
	    spec (str or unicode): version spec to check against
	    package (str or unicode): name of the package to use in the spec
	    base (boolean): If True, only check the base version of the version against the spec. Defaults
	        to False.

	Returns:
	    (boolean) True if the version matches the version spec, False otherwise.
	"""
	return version_matches_any_spec(version, [spec], package=package, base=base)


def octoprint_version_matches(spec, base=False):
	"""
	Checks if the current OctoPrint version matches the provided spec.

	See `Requirements Parsing <https://pythonhosted.org/setuptools/pkg_resources.html#requirements-parsing>`_ for
	details on the format. The version spec does not need to start with "OctoPrint", it will be added automatically
	if it's missing.

	Example::

	    octoprint_version_matches(">=1.2.0")

	    octoprint_version_matches("OctoPrint>=1.3.0", )

	Arguments:
	    spec (str or unicode): version spec to check against
	    base (boolean): If True, only check the base version of the OctoPrint version against the spec. Defaults
	        to False.

	Returns:
	    (boolean) True if the version matches the version spec, False otherwise.
	"""

	from octoprint import __version__
	return version_matches_any_spec(__version__, [spec], package="OctoPrint", base=base)
