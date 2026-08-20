"""Filesystem locations for server-side artifacts.

Kept out of :mod:`shared.rolldown_enums` so the data directory can be
redirected per user (or per test run) without touching game constants.
Override with ``ROLLDOWN_DATA_DIR``.
"""

import os
from pathlib import Path


def _data_dir():
    """Return the per-user directory that holds server logs and state."""
    override = os.environ.get('ROLLDOWN_DATA_DIR')
    base = Path(override) if override else Path.home() / '.local' / 'share' / 'rolldown'
    base.mkdir(parents=True, exist_ok=True)
    return base


SERVER_LOG_FILE = _data_dir() / 'server.log'
SERVER_TRANSITIONS_LOG = _data_dir() / 'transitions.jsonl'
