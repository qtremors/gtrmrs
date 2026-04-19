# gtrmrs - Unified CLI Tools
import sys

if sys.version_info < (3, 11):
    raise RuntimeError("gtrmrs requires Python 3.11 or newer; no third-party runtime packages are needed")

__version__ = "0.0.7"
