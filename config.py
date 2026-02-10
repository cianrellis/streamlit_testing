"""
Configuration constants and runtime flags for the First Embrace Streamlit app.
"""
import os
import sys
from pathlib import Path

SERVICE_ACCOUNT_FILE = Path(__file__).parent / "service-account.json"
TESTING_DIR = Path(__file__).parent / "testing"
FAKE_DATA_DIR = TESTING_DIR / "synthetic_data"

# ---------------------------------------------------------------------------
# Runtime flag: use local synthetic data instead of Firestore
# Usage:
#   streamlit run streamlit_app.py -- --fake-data
# or set environment variable:
#   USE_FAKE_DATA=1
# ---------------------------------------------------------------------------
USE_FAKE_DATA = ("--fake-data" in sys.argv) or (os.getenv("USE_FAKE_DATA", "0") == "1")

# ---------------------------------------------------------------------------
# Project Identity
# Controls dashboard title and timezone settings
# ---------------------------------------------------------------------------
PROJECT_ID = os.getenv("PROJECT_ID", "DEFAULT").upper()

