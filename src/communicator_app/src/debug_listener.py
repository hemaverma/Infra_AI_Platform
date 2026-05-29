"""Debug listener bootstrap for local Azure Functions debugging."""

import logging
import os


def start_debug_listener() -> None:
    """Start a debugpy listener when explicitly enabled by environment."""
    if os.getenv("ENABLE_DEBUGPY") != "1":
        return

    try:
        import debugpy

        port = int(os.getenv("DEBUGPY_PORT", "9091"))
        host = os.getenv("DEBUGPY_HOST", "127.0.0.1")
        logging.getLogger(__name__).info(
            f"[debug] Starting debugpy listener on {host}:{port}"
        )
        debugpy.listen((host, port))
        # Do NOT wait-for-client to avoid worker timeout; attach is optional.
    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to start debugpy: {e}")
