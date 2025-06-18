"""
FENDER - Forensic Extraction of Navigational Data & Event Records
Source code package
"""

# Import version from main.py
import sys
from pathlib import Path

# Add parent directory to path to import from main.py
sys.path.insert(0, str(Path(__file__).parent.parent))
from main import FENDER_VERSION

__version__ = FENDER_VERSION
