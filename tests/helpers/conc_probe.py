"""Concurrency probe: record how many probes run simultaneously.

Usage: conc_probe.py <state-file> <seconds>
State file is JSON {"current": n, "max": m}, updated under an flock.
Each probe increments current (and max) on entry, sleeps, decrements
on exit. The final "max" is the true peak concurrency observed.
"""
import fcntl
import json
import os
import sys
import time

path, seconds = sys.argv[1], float(sys.argv[2])


def update(delta):
    with open(path, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        raw = fh.read().strip()
        state = json.loads(raw) if raw else {"current": 0, "max": 0}
        state["current"] += delta
        state["max"] = max(state["max"], state["current"])
        fh.seek(0)
        fh.truncate()
        fh.write(json.dumps(state))
        fh.flush()
        os.fsync(fh.fileno())
        fcntl.flock(fh, fcntl.LOCK_UN)
        return state


update(+1)
try:
    time.sleep(seconds)
finally:
    update(-1)
