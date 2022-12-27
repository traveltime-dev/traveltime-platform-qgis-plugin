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
            "travel_time_platform_plugin.tests.tests_express_tools",
            "travel_time_platform_plugin.tests.tests_algorithms",
        ]
    )
    runner = unittest.TextTestRunner(stream=stream, verbosity=2)
    return runner.run(suite)


def system_info():
    return "\n".join(
        [
            "Travel Time Platform Plugin tests report",
            "----------------------------------------------------------------------",
            f"Date: {datetime.now().isoformat()}",
            f"QGIS version: {Qgis.version()} [{Qgis.devVersion()}]",
            f"Qt version: {qVersion()}",
            f"Python version: {sys.version}",
            f"Platform: {platform.system()} {platform.release()} {platform.version()}",
            f"Plugin version: {pluginMetadata('travel_time_platform_plugin', 'version')}",
            "----------------------------------------------------------------------",
        ]
    )
