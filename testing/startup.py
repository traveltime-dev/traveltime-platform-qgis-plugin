"""
This script starts the test suite from within QGIS.

It should be mounted to ~/.local/share/QGIS/QGIS3/startup.py to run the tests on QGIS startup.
"""

import sys

from qgis.PyQt.QtCore import qDebug
from qgis.utils import iface

# TODO: proper tests discovery
from travel_time_platform_plugin.tests import run_suite, system_info

# Forward pyqgis output to console
sys.stdout.write = lambda text: qDebug(text.encode("ascii", "replace").strip())
sys.stderr.write = lambda text: qDebug(text.encode("ascii", "replace").strip())

print("Waiting for initialisation...")


def run_tests():

    print("Starting tests...")

    # Show output
    print(system_info())

    # Maximize the window
    iface.mainWindow().showMaximized()
    iface.mainWindow().activateWindow()

    # Run the tests
    tests = run_suite(stream=sys.stdout)

    # To workaround missing exit code (see below), so we print the result value and check for it in the runner
    if tests.wasSuccessful():
        print("__SUCCESS__")
    else:
        print("__FAILURE__")

    # Exit code here is lost, since this crashes QGIS with segfault
    print("notice: following `QGIS died on signal 11` can be ignored.")
    sys.exit(0 if tests.wasSuccessful() else 1)


# Start tests only once init is complete
iface.initializationCompleted.connect(run_tests)
