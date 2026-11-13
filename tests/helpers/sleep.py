"""Sleep, then optionally append a tag to a marker file.

Usage: sleep.py <seconds> [marker-file tag]
The marker is written only if the sleep completes, so a killed
(timed-out) invocation leaves no marker behind.
"""
import sys
import time

time.sleep(float(sys.argv[1]))
if len(sys.argv) > 3:
    with open(sys.argv[2], "a", encoding="utf-8") as fh:
        fh.write(sys.argv[3] + "\n")
