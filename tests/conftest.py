"""Shared pytest fixtures.

The real game talks to a TCP champion-pool server.  For tests we inject an
in-process ``FakePool`` that speaks the exact same socket protocol
(``pool`` / ``buy: X`` / ``sell: X: L``), so no server (or network) is needed.
"""

import json
import os
import struct
import sys
from pathlib import Path

import pytest

# Run Qt fully headless.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Make the project importable regardless of pytest's rootdir.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.rolldown_enums import CHAMPION_AMOUNTS, THREE_STARRED, UNIT_AMOUNT_LEVEL  # noqa: E402

SET_DIR = ROOT / "TFT_Set_17"


class FakePool:
    """In-process stand-in for the pool server, speaking the framed protocol.

    Implements ``sendall``/``recv`` with length-prefixed framing and supports
    ``pool`` / ``buy:`` / ``sell:`` / ``bulk:`` / ``reset`` / ``quit`` just
    like the real :mod:`shared.networking_server`.
    """

    def __init__(self, input_dir):
        with open(Path(input_dir) / "champions.json", encoding="utf-8") as handle:
            champions = json.loads(handle.read())

        self.pool = {}
        for champ in champions:
            if len(champ["traits"]) < 1:
                continue
            self.pool[champ["name"]] = CHAMPION_AMOUNTS[champ["cost"]]

        self._inbuf = b""
        self._outbuf = b""

    # region framed-socket emulation
    @staticmethod
    def _frame(text):
        payload = text.encode()
        return struct.pack(">I", len(payload)) + payload

    def sendall(self, data):
        self._inbuf += data
        while len(self._inbuf) >= 4:
            (length,) = struct.unpack(">I", self._inbuf[:4])
            if len(self._inbuf) < 4 + length:
                break
            message = self._inbuf[4:4 + length].decode()
            self._inbuf = self._inbuf[4 + length:]
            self._outbuf += self._frame(self._handle(message))

    # Some callers may still use .send(); treat it like sendall.
    send = sendall

    def recv(self, bufsize):
        out, self._outbuf = self._outbuf[:bufsize], self._outbuf[bufsize:]
        return out
    # endregion

    def _do_buy(self, name):
        if self.pool.get(name, 0) > 0:
            self.pool[name] -= 1

    def _do_sell(self, name, level):
        amount = UNIT_AMOUNT_LEVEL[int(level)]
        self.pool[name] = self.pool.get(name, 0) + amount

    def _handle(self, message):
        if message in ("pool", "full_pool"):
            return json.dumps(self.pool)
        if message.startswith("bulk:"):
            ops = json.loads(message[len("bulk:"):])
            for op in ops:
                if op["op"] == "buy":
                    self._do_buy(op["name"])
                else:
                    self._do_sell(op["name"], op.get("level", 1))
            return f"bulk ok ({len(ops)} ops)"
        if message.startswith("buy"):
            self._do_buy(message.split(":")[1].strip())
            return "bought"
        if message.startswith("sell"):
            _, name, level = message.split(":")
            self._do_sell(name.strip(), level.strip())
            return "sold"
        if message in ("quit", "shutdown"):
            return "Quitting..."
        return f"Unknown message: {message}"

    # Number of copies of ``name`` still available in the pool.
    def count(self, name):
        return self.pool.get(name, 0)


@pytest.fixture(autouse=True)
def _reset_three_starred():
    """The 3-star tracker is a module global; isolate it per test."""
    THREE_STARRED.clear()
    yield
    THREE_STARRED.clear()


@pytest.fixture
def set_dir():
    return str(SET_DIR)


@pytest.fixture
def fake_pool():
    return FakePool(SET_DIR)


@pytest.fixture
def game(fake_pool):
    """A ready-to-use Game backed by the FakePool (no server)."""
    from shared.game import Game

    return Game(str(SET_DIR), gold=100, level=9, client_socket=fake_pool)


@pytest.fixture(scope="session")
def qapp():
    """A single QApplication for the whole GUI test session."""
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
