"""
This script should be used to wrap calls to QGIS. It will check the output and set exit code
accordingly to test results, working around the issue about QGIS crashing on exitting from python.
"""

import sys
from subprocess import PIPE, STDOUT, Popen

print("Starting qgis...")

# Run QGIS in a subprocess
process = Popen("qgis", stdout=PIPE, stderr=STDOUT, encoding="utf-8")

# Print output in realtime, keep full output in string
full_output = ""
while True:
    output = process.stdout.readline()
    print(output.strip(), flush=True)
    full_output += output
    if output == "" and process.poll() is not None:
        break

# Set exit code
if "__SUCCESS__" in full_output and "__FAILURE__" not in full_output:
    sys.exit(0)
else:
    sys.exit(1)
