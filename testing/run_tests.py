"""
This script starts the test suite from within QGIS.

It should be run with the --code command line argument
"""

import os
import sys

from qgis.PyQt.QtCore import qDebug

# TODO: proper tests discovery
from travel_time_platform_plugin.tests import run_suite, system_info

# Forward pyqgis output to console
sys.stdout.write = lambda text: qDebug(text.encode("ascii", "replace").strip())
sys.stderr.write = lambda text: qDebug(text.encode("ascii", "replace").strip())


print("Starting tests...")

# Show output
print(system_info())

# Run the tests
tests = run_suite(stream=sys.stdout)

# Exit with code
os._exit(0 if tests.wasSuccessful() else 1)
