"""
Root test runner entrypoint.
Preserves backwards-compatible CLI command: python -m unittest test_engine.py -v
The test suite implementation lives in tests/test_engine.py.
"""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tests.test_engine import *

if __name__ == "__main__":
    import unittest
    unittest.main()
