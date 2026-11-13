"""Append a tag line to a marker file. Usage: marker.py <file> <tag>."""
import sys

with open(sys.argv[1], "a", encoding="utf-8") as fh:
    fh.write(sys.argv[2] + "\n")
