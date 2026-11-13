"""Fake QA battery that fails with exit code 3.

Usage: battery_fail.py [label] [code]
Prints a failing result line and exits with the given code (default 3)
so tests can assert the exact exit code is recorded as evidence.
"""
import sys

label = sys.argv[1] if len(sys.argv) > 1 else "battery"
code = int(sys.argv[2]) if len(sys.argv) > 2 else 3
print(f"{label}: 9 passed, 3 failed")
sys.exit(code)
