"""Pytest bootstrap for communicator_app source imports."""

import sys
from pathlib import Path


COMMUNICATOR_APP_SRC = Path(__file__).resolve().parents[3] / "src" / "communicator_app" / "src"

if str(COMMUNICATOR_APP_SRC) not in sys.path:
    sys.path.insert(0, str(COMMUNICATOR_APP_SRC))
