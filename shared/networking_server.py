"""Rolldown game server. Handles shared champion pool and buy/sell messages from clients."""

# Standard libraries
import datetime as _dt
import json
import socket
import struct
import sys
import threading
from pathlib import Path

# Local imports
from shared.rolldown_enums import (
    CHAMPION_AMOUNTS,
    CHAMPION_POOL,
    POOL_LOCK,
    SERVER_PORT,
    SERVER_TRANSITIONS_LOG,
    UNIT_AMOUNT_LEVEL,
)
from shared.resources import Trait, Unit, serialize


# ----------------------------------------------------------------------------
# Framing helpers (mirror image of networking_client._{send,recv}_framed).

_HEADER = '!I'
_HEADER_SIZE = struct.calcsize(_HEADER)


class UnknownChampionError(Exception):
    """Unknown Champion Error."""


class UnknownMessageError(Exception):
    """Unknown Message Error."""


def _recv_exact(conn, num_bytes):
    chunks = []
    remaining = num_bytes
    while remaining > 0:
        chunk = conn.recv(remaining)
        if not chunk:
            raise ConnectionError('client closed the connection mid-message')
        chunks.append(chunk)
        remaining -= len(chunk)
    return b''.join(chunks)


def send_framed(conn, payload):
    """Send a length-prefixed message to *conn*."""
    if isinstance(payload, str):
        payload = payload.encode('utf-8')
    conn.sendall(struct.pack(_HEADER, len(payload)) + payload)


def recv_framed(conn):
    """Receive one full length-prefixed message and return its decoded string."""
    header = _recv_exact(conn, _HEADER_SIZE)
    (length,) = struct.unpack(_HEADER, header)
    body = _recv_exact(conn, length)
    return body.decode('utf-8')


# ----------------------------------------------------------------------------
# Pool helpers
def populate_champ_pool(input_dir):
    """Read in units and traits."""
    assert POOL_LOCK.locked(), 'POOL_LOCK must be held to access CHAMPION POOL'

    for cost in CHAMPION_POOL:
        CHAMPION_POOL[cost] = []

    with open(Path(input_dir) / 'champions.json', encoding='utf-8') as champions_file:
        champions_list = json.loads(champions_file.read())

    with open(Path(input_dir) / 'traits.json', encoding='utf-8') as traits_file:
        traits_list = json.loads(traits_file.read())

    champions = {}
    for champ in champions_list:
        if len(champ['traits']) < 1:
            continue
        champions[champ['name']] = Unit(champ['cost'], champ['name'],
            champ['traits'], champ['championId'])
        CHAMPION_POOL[champ['cost']] += [champions[champ['name']]] * \
            CHAMPION_AMOUNTS[champ['cost']]

    traits = {}
    for trait in traits_list:
        breakpoints = []
        styles = []
        for b_p in trait['sets']:
            breakpoints.append(b_p['min'])
            styles.append(b_p['style'])
        traits[trait['name']] = Trait(trait['name'], breakpoints, styles)

    return champions, traits


def get_champion_pool():
    """Return the current state of the champion pool as a framed payload."""
    assert POOL_LOCK.locked(), 'POOL_LOCK must be held to access CHAMPION POOL'

    pool = {}
    for _, champions in CHAMPION_POOL.items():
        for unit in champions:
            pool[unit.name] = pool.get(unit.name, 0) + 1
    return json.dumps(pool, default=serialize)


def get_full_pool():
    """Return the rich CHAMPION_POOL representation."""
    assert POOL_LOCK.locked(), 'POOL_LOCK must be held to access CHAMPION POOL'
    return json.dumps(CHAMPION_POOL, default=serialize)


# ----------------------------------------------------------------------------
# Transition log helpers (server improvement §2.12)
_LOG_LOCK = threading.Lock()


def _append_transition(record):
    """Append a JSON-line transition record to ``SERVER_TRANSITIONS_LOG``.

    Thread-safe and crash-resilient: writes are atomic per ``write()`` call
    because the OS buffers them on a single descriptor.  On startup the log
    is replayed by :func:`_replay_transitions`.
    """
    record = {'ts': _dt.datetime.utcnow().isoformat() + 'Z', **record}
    payload = json.dumps(record, default=serialize)
    with _LOG_LOCK:
        with open(SERVER_TRANSITIONS_LOG, mode='a', encoding='utf-8') as log_file:
            log_file.write(payload + '\n')
            log_file.flush()


def _replay_transitions(champions):
    """Re-apply every record from the transition log to ``CHAMPION_POOL``.

    The state recovered from the log is approximate: we only persist
    buy/sell records, which the server can reapply at startup so a hard
    crash doesn't lose game progress.
    """
    if not SERVER_TRANSITIONS_LOG.is_file():
        return
    with open(SERVER_TRANSITIONS_LOG, mode='r', encoding='utf-8') as log_file:
        for line in log_file:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            op = record.get('op')
            unit = record.get('unit')
            if op == 'buy' and unit in champions:
                unit_obj = champions[unit]
                if unit_obj in CHAMPION_POOL.get(unit_obj.rarity, []):
                    CHAMPION_POOL[unit_obj.rarity].remove(unit_obj)
            elif op == 'sell' and unit in champions:
                level = int(record.get('level', 1))
                unit_obj = champions[unit]
                for _ in range(UNIT_AMOUNT_LEVEL.get(level, 1)):
                    CHAMPION_POOL[unit_obj.rarity].append(unit_obj)


def buy_champion(message, champions):
    """Handle receiving a message to buy a champion."""
    assert POOL_LOCK.locked(), 'POOL_LOCK must be held to access CHAMPION POOL'

    parts = message.split(':', 1)
    if len(parts) != 2:
        raise UnknownMessageError(message)
    unit = parts[1].strip()
    if unit not in champions:
        raise UnknownChampionError(unit)

    unit_obj = champions[unit]
    if unit_obj not in CHAMPION_POOL[unit_obj.rarity]:
        raise UnknownChampionError(f'{unit} (no copies left in pool)')

    CHAMPION_POOL[unit_obj.rarity].remove(unit_obj)
    _append_transition({'op': 'buy', 'unit': unit})
    return f'OK: bought {unit}'


def sell_champion(message, champions):
    """Handle receiving a message to sell a champion."""
    assert POOL_LOCK.locked(), 'POOL_LOCK must be held to access CHAMPION POOL'

    parts = message.split(':')
    if len(parts) < 3:
        raise UnknownMessageError(message)
    unit = parts[1].strip()
    try:
        level = int(parts[2].strip())
    except ValueError as err:
        raise UnknownMessageError(message) from err
    if unit not in champions:
        raise UnknownChampionError(unit)

    amount = UNIT_AMOUNT_LEVEL[level]
    unit_obj = champions[unit]
    for _ in range(amount):
        CHAMPION_POOL[unit_obj.rarity].append(unit_obj)
    _append_transition({'op': 'sell', 'unit': unit, 'level': level})
    return f'OK: sold {amount} {unit}'


def shutdown(main_socket, client_threads):
    """Shutdown server and close all connections."""
    try:
        main_socket.close()
    except OSError:
        pass
    for thread in client_threads:
        thread.join(timeout=1.0)
    print('Server shutting down...')


def client_thread(connection, addr, champions):
    """Handle a single client connection."""
    try:
        while True:
            try:
                message = recv_framed(connection)
            except ConnectionError:
                break
            print('Message received:', message, 'from', addr)

            response = None
            try:
                if message == 'quit':
                    send_framed(connection, 'Quitting...')
                    break
                if message == 'pool':
                    with POOL_LOCK:
                        response = get_champion_pool()
                elif message == 'full_pool':
                    with POOL_LOCK:
                        response = get_full_pool()
                elif message.startswith('buy'):
                    with POOL_LOCK:
                        response = buy_champion(message, champions)
                elif message.startswith('sell'):
                    with POOL_LOCK:
                        response = sell_champion(message, champions)
                elif message == 'reset':
                    with POOL_LOCK:
                        populate_champ_pool(sys.argv[1])
                        response = 'OK: CHAMPION_POOL reset'
                elif message == 'shutdown':
                    send_framed(connection, 'Quitting...')
                    break
                else:
                    raise UnknownMessageError(message)
            except UnknownChampionError as err:
                response = f'ERROR: unknown champion: {err}'
                print(response)
            except UnknownMessageError as err:
                response = f'ERROR: unknown message: {err}'
                print(response)
            except Exception as err:  # pylint: disable=broad-except
                response = f'ERROR: {type(err).__name__}: {err}'
                print(response)

            if response is not None:
                try:
                    send_framed(connection, response)
                except (BrokenPipeError, ConnectionError):
                    break
    finally:
        try:
            connection.close()
        except OSError:
            pass
        print(addr, 'has closed the connection.')


def init_rolldown_server(argv):
    """Initialize the server and dispatch client threads."""
    with POOL_LOCK:
        champions, _ = populate_champ_pool(argv[1])
        # Replay the persisted transitions so a restart restores game state.
        _replay_transitions(champions)

    client_threads = []
    main_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    main_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    host = socket.gethostname()
    main_socket.bind((host, SERVER_PORT))
    main_socket.listen()
    print('Server on port', SERVER_PORT, 'listening for connections.')

    try:
        while True:
            connection, addr = main_socket.accept()
            print('Got connection from', addr)
            new_thread = threading.Thread(
                target=client_thread, args=(connection, addr, champions),
                daemon=True,
            )
            new_thread.start()
            client_threads.append(new_thread)
    except (KeyboardInterrupt, BrokenPipeError, ConnectionAbortedError,
            ConnectionResetError):
        shutdown(main_socket, client_threads)


def main(argv):
    """Start the server."""
    init_rolldown_server(argv)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: python networking_server.py {input_dir}')
        sys.exit()
    main(sys.argv)
