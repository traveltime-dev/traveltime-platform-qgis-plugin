"""
This script should be used to wrap calls to QGIS. It will check the output and set exit code
accordingly to test results, working around the issue about QGIS crashing on exitting from python.
"""

import sys
from subprocess import PIPE, STDOUT, run

print("Starting qgis...")

process = run(["qgis"], stdout=PIPE, stderr=STDOUT, encoding="utf-8")

print(process.stdout)


if "__SUCCESS__" in process.stdout and "__FAILURE__" not in process.stdout:
    sys.exit(0)
else:
    sys.exit(1)
