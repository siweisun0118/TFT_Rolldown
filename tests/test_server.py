"""Integration test for the framed, gracefully-shutdownable pool server.

The test is self-healing: it shuts down any pre-existing server before it
starts and guarantees it never leaves a server behind, so it neither skips
nor leaks a process onto port 8000.
"""

import json
import socket
import subprocess
import sys
import time

import pytest

from conftest import ROOT, SET_DIR
from shared.networking_client import send_bulk, send_message, wait_for_server
from shared.rolldown_enums import SERVER_HOST, SERVER_PORT


def _connect(timeout=0.3):
    """Return a connected socket, or None if nothing is listening."""
    try:
        return socket.create_connection((SERVER_HOST, SERVER_PORT), timeout)
    except OSError:
        return None


def _port_free():
    sock = _connect()
    if sock is None:
        return True
    sock.close()
    return False


def _wait_port_free(timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_free():
            return True
        time.sleep(0.1)
    return _port_free()


def _shutdown_any_running_server():
    """Cleanly stop a server that may have leaked from an earlier run."""
    sock = _connect()
    if sock is None:
        return
    try:
        send_message(sock, "shutdown")
    except OSError:
        pass
    finally:
        sock.close()
    _wait_port_free(timeout=8.0)


@pytest.fixture
def server():
    _shutdown_any_running_server()
    assert _wait_port_free(timeout=8.0), "port 8000 still busy after cleanup"

    proc = subprocess.Popen(
        [sys.executable, "-m", "shared.networking_server", str(SET_DIR)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        sock = wait_for_server(timeout=15)
        yield sock, proc
    finally:
        # Guarantee the server never survives this test.
        try:
            send_message(sock, "shutdown")
        except (OSError, NameError, UnboundLocalError):
            pass
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        _wait_port_free(timeout=8.0)


def test_framed_pool_buy_sell_roundtrip(server):
    sock, _ = server
    pool = json.loads(send_message(sock, "pool"))
    start = pool["Aatrox"]

    assert send_message(sock, "buy: Aatrox") == "bought"
    assert json.loads(send_message(sock, "pool"))["Aatrox"] == start - 1
    assert send_message(sock, "sell: Aatrox: 1") == "sold"
    assert json.loads(send_message(sock, "pool"))["Aatrox"] == start


def test_bulk_is_atomic_single_roundtrip(server):
    sock, _ = server
    pool = json.loads(send_message(sock, "pool"))
    aatrox, akali = pool["Aatrox"], pool["Akali"]

    resp = send_bulk(sock, [
        {"op": "buy", "name": "Aatrox"},
        {"op": "buy", "name": "Aatrox"},
        {"op": "sell", "name": "Akali", "level": 1},
    ])
    assert "bulk ok" in resp

    pool = json.loads(send_message(sock, "pool"))
    assert pool["Aatrox"] == aatrox - 2
    assert pool["Akali"] == akali + 1


def test_reset_restores_pool(server):
    sock, _ = server
    send_message(sock, "buy: Aatrox")
    assert send_message(sock, "reset") == "CHAMPION_POOL reset"
    assert json.loads(send_message(sock, "pool"))["Aatrox"] == 29


def test_graceful_shutdown_exits_cleanly(server):
    sock, proc = server
    assert send_message(sock, "shutdown") == "Quitting..."
    proc.wait(timeout=10)
    assert proc.returncode == 0
    assert _wait_port_free(timeout=5.0)
