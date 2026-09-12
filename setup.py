"""
gtrmrs - Unified CLI Tools

A collection of Git-aware utilities:
- rtree: Directory tree visualization
- locr: Lines of code counter
- gitmig: Repository copy without dependencies
- deps: Multi-repository dependency auditor and updater
- storage: Repository storage audit and cleanup preview
"""

import re
from setuptools import setup, find_packages

# Read version from __init__.py
with open("gtrmrs/__init__.py", "r", encoding="utf-8") as f:
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]", f.read(), re.M)
    version = version_match.group(1) if version_match else "0.0.0"

setup(
    name="gtrmrs",
    version=version,
    description="Unified CLI tools for Git repository management",
    author="Tremors",
    packages=find_packages(exclude=("tests", "tests.*")),
    python_requires=">=3.11",
    entry_points={
        "console_scripts": [
            # Umbrella command
            "gtrmrs=gtrmrs.cli:main",
            # Direct access (preferred)
            "rtree=gtrmrs.rtree.cli:main",
            "locr=gtrmrs.locr.cli:main",
            "gitmig=gtrmrs.gitmig.cli:main",
            "deps=gtrmrs.deps.cli:main",
            "storage=gtrmrs.storage.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Build Tools",
        "Topic :: Utilities",
    ],
)
