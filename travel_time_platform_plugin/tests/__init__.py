import platform
import sys
import unittest
from datetime import datetime

from qgis.core import Qgis
from qgis.PyQt.QtCore import qVersion
from qgis.testing import unittest
from qgis.utils import pluginMetadata


def run_suite(stream) -> unittest.TestResult:

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromNames(
        [
            "traveltime_plugin.tests.tests_express_tools",
            "traveltime_plugin.tests.tests_algorithms",
            "traveltime_plugin.tests.tests_misc",
        ]
    )
    runner = unittest.TextTestRunner(stream=stream, verbosity=2)
    return runner.run(suite)


def system_info():
    return "\n".join(
        [
            "TravelTime Plugin tests report",
            "----------------------------------------------------------------------",
            f"Date: {datetime.now().isoformat()}",
            f"QGIS version: {Qgis.version()} [{Qgis.devVersion()}]",
            f"Qt version: {qVersion()}",
            f"Python version: {sys.version}",
            f"Platform: {platform.system()} {platform.release()} {platform.version()}",
            f"Plugin version: {pluginMetadata('traveltime_plugin', 'version')}",
            "----------------------------------------------------------------------",
        ]
    )
