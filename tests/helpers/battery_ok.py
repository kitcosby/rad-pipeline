"""Fake QA battery that passes. Usage: battery_ok.py [label]

Stands in for an existing project QA battery invoked through its
existing interface: prints a result line and exits 0.
"""
import sys

label = sys.argv[1] if len(sys.argv) > 1 else "battery"
print(f"{label}: 12 passed, 0 failed")
sys.exit(0)
