"""Pytest configuration for communicator app workflow tests."""

import sys
from pathlib import Path


COMMUNICATOR_APP_SRC = Path(__file__).resolve().parents[1] / "src" / "communicator_app" / "src"
EXPERIMENTATION_SRC = Path(__file__).resolve().parents[1] / "src" / "experimentation" / "src"

if str(COMMUNICATOR_APP_SRC) not in sys.path:
    sys.path.insert(0, str(COMMUNICATOR_APP_SRC))

if str(EXPERIMENTATION_SRC) not in sys.path:
    sys.path.insert(0, str(EXPERIMENTATION_SRC))
