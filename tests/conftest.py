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


@pytest.fixture
def live_server(set_dir):
    """A real framed server on an ephemeral port, for end-to-end protocol tests.

    Binds port 0 so runs never contend for the fixed application port, and
    reuses the shipped dispatch helpers so the wire behavior under test is the
    same code the real server runs.
    """
    import socket  # noqa: WPS433
    import threading  # noqa: WPS433

    from shared.networking_server import (  # noqa: WPS433
        buy_champion, get_champion_pool, populate_champ_pool, recv_framed,
        sell_champion, send_framed,
    )
    from shared.rolldown_enums import POOL_LOCK  # noqa: WPS433

    with POOL_LOCK:
        champions, _ = populate_champ_pool(set_dir)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(('127.0.0.1', 0))
    listener.listen()
    listener.settimeout(0.2)
    port = listener.getsockname()[1]
    stop = threading.Event()

    def dispatch(message):
        if message == 'pool':
            with POOL_LOCK:
                return get_champion_pool()
        if message.startswith('buy'):
            with POOL_LOCK:
                return buy_champion(message, champions)
        if message.startswith('sell'):
            with POOL_LOCK:
                return sell_champion(message, champions)
        return f'ERROR: unknown message: {message}'

    def serve():
        while not stop.is_set():
            try:
                connection, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with connection:
                while not stop.is_set():
                    try:
                        message = recv_framed(connection)
                    except (ConnectionError, OSError):
                        break
                    try:
                        reply = dispatch(message)
                    except Exception as err:  # noqa: BLE001 -- mirror the real worker
                        reply = f'ERROR: {type(err).__name__}: {err}'
                    try:
                        send_framed(connection, reply)
                    except OSError:
                        break

    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    yield port
    stop.set()
    listener.close()
    worker.join(timeout=2)
