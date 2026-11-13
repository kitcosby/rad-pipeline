"""FAKE CEG generation stand-in. Usage: fake_ceg.py <output-file>

This is NOT the qa-ceg engine and generates no CEG graphs or suites.
It only writes a one-line text marker so adapter tests can prove
whether the gated generation stage was permitted to execute.
"""
import sys

path = sys.argv[1]
with open(path, "w", encoding="utf-8") as fh:
    fh.write("fake generation ran (test stand-in; no CEG artifacts produced)\n")
print(f"fake-ceg: wrote {path}")
