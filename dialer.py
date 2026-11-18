#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# File: dialer.py (repository root)
# Purpose: Convenience CLI entry point so operators can run `python dialer.py`.
# Exports: None (script only).
# Invoked by: Developers from shell; equivalent to `python server.py`.
# Depends on: server.serve() which starts both HTTP servers in server.py.
# -----------------------------------------------------------------------------
"""Start the local Power Dialer CRM web application."""

# Import the serve() bootstrap from server.py (not features/dialer.py Dialer class).
from server import serve


# Standard Python idiom: run serve() only when executed as a script, not on import.
if __name__ == "__main__":
    serve()