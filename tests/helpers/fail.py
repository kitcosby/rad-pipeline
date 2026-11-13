"""Exit with the given code (default 1). Usage: fail.py [code]"""
import sys

sys.exit(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
