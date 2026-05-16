"""Send messages to the main rolldown server.

Messages use **length-prefixed framing** (a 4-byte big-endian length followed
by the UTF-8 payload) instead of the old ``\\0`` sentinel scan.  This removes
the blocking one-chunk-at-a-time receive loop and partial-read ambiguity
(PERFORMANCE_AND_SERVER.md 1.3).
"""


# Standard libraries
import json
import socket
import struct
import sys
import time

# Local imports
from shared.rolldown_enums import SERVER_HOST, SERVER_PORT


def _recv_exactly(sock, num_bytes):
    """Read exactly ``num_bytes`` from ``sock`` (or raise on close)."""
    chunks = []
    remaining = num_bytes
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError('Socket closed before full message received')
        chunks.append(chunk)
        remaining -= len(chunk)
    return b''.join(chunks)


def send_framed(sock, text):
    """Send ``text`` as a single length-prefixed frame."""
    payload = text.encode()
    sock.sendall(struct.pack('>I', len(payload)) + payload)


def recv_framed(sock):
    """Receive one length-prefixed frame and return it as text."""
    (length,) = struct.unpack('>I', _recv_exactly(sock, 4))
    return _recv_exactly(sock, length).decode()


def send_message(client_socket, message):
    """Send a message to the server and return its (framed) response."""
    send_framed(client_socket, message)
    return recv_framed(client_socket)


def send_bulk(client_socket, ops):
    """Send a batch of pool operations in a single round-trip.

    ``ops`` is a list like ``[{"op": "buy", "name": "Ahri"},
    {"op": "sell", "name": "Zed", "level": 1}]`` (1.2).
    """
    return send_message(client_socket, 'bulk:' + json.dumps(ops))


# pylint: disable=unused-argument
def init_rolldown_client(port=0):
    """Connect to the rolldown server on loopback.

    Clients no longer bind a local port (2.2); ``port`` is accepted only for
    backward compatibility and ignored.
    """
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((SERVER_HOST, SERVER_PORT))
    return client_socket


def wait_for_server(timeout=10.0, interval=0.05):
    """Poll-connect until the server is ready or ``timeout`` elapses (2.1).

    Replaces the old fixed ``time.sleep(0.5)`` race.
    """
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            return init_rolldown_client()
        except (ConnectionRefusedError, OSError) as err:
            last_error = err
            time.sleep(interval)
    raise ConnectionRefusedError(
        f'Server not reachable on {SERVER_HOST}:{SERVER_PORT}: {last_error}')


def main(argv):
    """Start the client that sends messages to the server."""
    client_socket = init_rolldown_client()

    # Send messages
    while True:
        message = input('Enter a message: ')
        response = send_message(client_socket, message)
        print('Server response:', response)

        if response == 'Quitting...':
            print('Client closed successfully')
            break


if __name__ == '__main__':
    main(sys.argv)
