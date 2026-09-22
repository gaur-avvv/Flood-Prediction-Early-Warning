"""Test configuration (T-33): offline, auth disabled, project root on sys.path."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["FLOOD_API_KEYS"] = ""
os.environ["FLOOD_AUTH_REQUIRED"] = "false"
os.environ.setdefault("FLOOD_ENV", "test")
