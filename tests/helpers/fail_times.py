"""Fail until a counter file reaches a threshold, then succeed.

Usage: fail_times.py <counter-file> <failures-before-success>
Each invocation increments the counter; exit 1 while the count is
<= failures-before-success, else exit 0. The final counter value is
the exact number of times this script was executed.
"""
import os
import sys

path, threshold = sys.argv[1], int(sys.argv[2])
count = 0
if os.path.exists(path):
    count = int(open(path, encoding="utf-8").read().strip() or "0")
count += 1
with open(path, "w", encoding="utf-8") as fh:
    fh.write(str(count))
sys.exit(1 if count <= threshold else 0)
