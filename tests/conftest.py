"""Shared pytest fixtures for TFT-Rolldown tests.

The fixtures here keep the test files terse: most tests just need a Game in
offline mode with predictable starting state.  We also offer helpers for
running PyQt tests without a real display by setting the ``QT_QPA_PLATFORM``
environment variable to ``offscreen`` before any Qt module is imported.
"""

# Standard libraries
import os
import sys
from pathlib import Path

import pytest


# Make the repository root importable as a package so tests can import the
# project modules without modifying PYTHONPATH externally.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(scope='session')
def set_dir():
    """Path to the Set 17 data used by most tests."""
    return str(REPO_ROOT / 'TFT_Set_17')


@pytest.fixture(autouse=True)
def _reset_three_starred():
    """The THREE_STARRED global is mutated by upgrades; reset between tests."""
    # Import lazily so the autouse fixture doesn't fail when the module is
    # imported for the first time by another test.
    from shared.rolldown_enums import THREE_STARRED  # noqa: WPS433
    THREE_STARRED.clear()
    yield
    THREE_STARRED.clear()


@pytest.fixture
def game(set_dir):  # pylint: disable=redefined-outer-name
    """Offline ``Game`` instance with 100 gold and player level 3."""
    from shared.game import Game  # noqa: WPS433
    return Game(set_dir, gold=100, level=3, offline=True)


@pytest.fixture
def qapp():
    """Singleton ``QApplication`` for GUI tests, set up offscreen."""
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PyQt5.QtWidgets import QApplication  # noqa: WPS433
    app = QApplication.instance() or QApplication(['tft-test'])
    return app
