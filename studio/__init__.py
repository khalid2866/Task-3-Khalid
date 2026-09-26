"""Image Generation Studio — package init. Loads .env if present."""
from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # dotenv is optional
    pass

__version__ = "1.0.0"
