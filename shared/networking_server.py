"""Receive messages and manage the rolldown champion pool.

Robust, framed, gracefully-shutdownable threaded server
(PERFORMANCE_AND_SERVER.md 1.2, 1.3, 1.5, 2.1, 2.2, 2.3, 2.4):

* ``socketserver.ThreadingTCPServer`` with daemon threads (2.4) instead of a
  hand-rolled accept loop that leaks threads.
* Binds loopback only (2.2).
* Length-prefixed framing (1.3) shared with the client.
* The database is parsed **once** and reused (even by ``reset``) (1.5).
* Prints a readiness sentinel so clients need no ``sleep`` (2.1).
* ``shutdown`` message + SIGTERM/SIGINT stop the server cleanly (2.3).
* ``bulk:`` applies many ops under a single lock acquisition (1.2).
"""

# Standard libraries
import json
import signal
import socketserver
import sys
import threading
from pathlib import Path


# Local imports
from shared.networking_client import recv_framed, send_framed
from shared.rolldown_enums import (
    CHAMPION_AMOUNTS, CHAMPION_POOL, POOL_LOCK, SERVER_HOST,
    SERVER_PORT, SERVER_READY_MESSAGE, UNIT_AMOUNT_LEVEL,
)
from shared.resources import Unit, Trait, serialize


class UnknownChampionError(Exception):
    """Unknown Champion Error."""


class UnknownMessageError(Exception):
    """Unknown Message Error."""


# Parsed database, shared by every connection and reused on reset (1.5).
_CHAMPIONS = {}


def populate_champ_pool(input_dir, reparse=True):
    """(Re)build the champion pool, reusing the parsed DB when possible."""
    assert POOL_LOCK.locked(), 'POOL_LOCK must be held to access CHAMPION POOL'
    global _CHAMPIONS

    for cost in CHAMPION_POOL:
        CHAMPION_POOL[cost] = []

    if reparse or not _CHAMPIONS:
        with open(Path(input_dir) / 'champions.json', encoding='utf-8') as champs:
            champions_list = json.loads(champs.read())
        with open(Path(input_dir) / 'traits.json', encoding='utf-8') as traits:
            json.loads(traits.read())  # validate presence / format

        champions = {}
        for champ in champions_list:
            if len(champ['traits']) < 1:
                continue
            champions[champ['name']] = Unit(
                champ['cost'], champ['name'], champ['traits'], champ['championId'])
        _CHAMPIONS = champions

    # Reuse the (immutable for pool purposes) Unit instances (1.5).
    for name, unit in _CHAMPIONS.items():
        CHAMPION_POOL[unit.rarity] += [unit] * CHAMPION_AMOUNTS[unit.rarity]

    return _CHAMPIONS


def get_champion_pool():
    """Return the current per-name counts as a JSON string."""
    assert POOL_LOCK.locked(), 'POOL_LOCK must be held to access CHAMPION POOL'
    pool = {}
    for champions in CHAMPION_POOL.values():
        for unit in champions:
            pool[unit.name] = pool.get(unit.name, 0) + 1
    return json.dumps(pool, default=serialize)


def _buy(name, champions):
    """Remove one copy of ``name`` from the pool."""
    if name not in champions:
        raise UnknownChampionError(name)
    unit = champions[name]
    if unit in CHAMPION_POOL[unit.rarity]:
        CHAMPION_POOL[unit.rarity].remove(unit)


def _sell(name, level, champions):
    """Return copies of ``name`` (count depends on star level) to the pool."""
    if name not in champions:
        raise UnknownChampionError(name)
    unit = champions[name]
    for _ in range(UNIT_AMOUNT_LEVEL[int(level)]):
        CHAMPION_POOL[unit.rarity].append(unit)


def process_message(message, champions, input_dir, stop_event):
    """Handle one request and return the (text) response."""
    if message == 'pool' or message == 'full_pool':
        with POOL_LOCK:
            return get_champion_pool()

    if message.startswith('bulk:'):
        ops = json.loads(message[len('bulk:'):])
        with POOL_LOCK:
            for op in ops:
                if op['op'] == 'buy':
                    _buy(op['name'], champions)
                elif op['op'] == 'sell':
                    _sell(op['name'], op.get('level', 1), champions)
        return f'bulk ok ({len(ops)} ops)'

    if message.startswith('buy'):
        with POOL_LOCK:
            _buy(message.split(':')[1].strip(), champions)
        return 'bought'

    if message.startswith('sell'):
        _, name, level = message.split(':')
        with POOL_LOCK:
            _sell(name.strip(), level.strip(), champions)
        return 'sold'

    if message == 'reset':
        with POOL_LOCK:
            populate_champ_pool(input_dir, reparse=False)
        return 'CHAMPION_POOL reset'

    if message in ('quit', 'shutdown'):
        if message == 'shutdown':
            stop_event.set()
        return 'Quitting...'

    raise UnknownMessageError(message)


class _Handler(socketserver.BaseRequestHandler):
    """Per-connection handler reading framed requests in a loop."""

    def handle(self):
        champions = self.server.champions
        input_dir = self.server.input_dir
        stop_event = self.server.stop_event
        try:
            while True:
                try:
                    message = recv_framed(self.request)
                except (ConnectionError, OSError):
                    return
                try:
                    response = process_message(
                        message, champions, input_dir, stop_event)
                except UnknownChampionError as err:
                    response = f'{err} not found'
                except UnknownMessageError as err:
                    response = f'Unknown message: {err}'
                send_framed(self.request, response)
                if stop_event.is_set():
                    # 'shutdown' was requested - stop the whole server.
                    threading.Thread(
                        target=self.server.shutdown, daemon=True).start()
                    return
                if response == 'Quitting...':
                    # Plain 'quit' - just close this connection.
                    return
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return


class RolldownServer(socketserver.ThreadingTCPServer):
    """Threaded, loopback, reuse-address rolldown server (2.2, 2.4)."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, input_dir):
        self.input_dir = input_dir
        self.stop_event = threading.Event()
        with POOL_LOCK:
            self.champions = populate_champ_pool(input_dir, reparse=True)
        super().__init__((SERVER_HOST, SERVER_PORT), _Handler)


def init_rolldown_server(argv):
    """Initialise and serve the rolldown server until shutdown (2.1, 2.3)."""
    input_dir = argv[1]
    server = RolldownServer(input_dir)

    def _graceful(*_):
        server.stop_event.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _graceful)
    signal.signal(signal.SIGINT, _graceful)

    # Readiness sentinel - clients poll-connect, no sleep needed (2.1).
    print(SERVER_READY_MESSAGE, flush=True)
    print(f'Server listening on {SERVER_HOST}:{SERVER_PORT}', flush=True)

    try:
        server.serve_forever()
    finally:
        server.server_close()
        print('Server shut down cleanly.', flush=True)


def main(argv):
    """Start the server."""
    init_rolldown_server(argv)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: python -m shared.networking_server {input_dir}')
        sys.exit()
    main(sys.argv)
