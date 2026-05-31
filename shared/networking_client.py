"""Send messages to the main rolldown server.

Server improvement §2.2: every message is now sent with a 4-byte
network-order length prefix.  The wire format is::

    [4 bytes: payload length, network order] [payload (utf-8)]

This makes ``recv`` re-entrant – no more relying on a trailing null byte to
delimit messages – and lets us send arbitrarily large pool dumps without
worrying about TCP segmentation.
"""

# Standard libraries
import socket
import struct
import sys

# Local imports
from shared.rolldown_enums import SERVER_PORT


# Header size (always 4 bytes, network-order length).
_HEADER = '!I'
_HEADER_SIZE = struct.calcsize(_HEADER)


def _recv_exact(client_socket, num_bytes):
    """Read exactly *num_bytes* bytes from *client_socket* or raise."""
    chunks = []
    remaining = num_bytes
    while remaining > 0:
        chunk = client_socket.recv(remaining)
        if not chunk:
            raise ConnectionError(
                f'Server closed connection while reading; '
                f'expected {num_bytes} bytes, got {num_bytes - remaining}.'
            )
        chunks.append(chunk)
        remaining -= len(chunk)
    return b''.join(chunks)


def send_framed(client_socket, payload):
    """Send a length-prefixed message to the server."""
    if isinstance(payload, str):
        payload = payload.encode('utf-8')
    client_socket.sendall(struct.pack(_HEADER, len(payload)) + payload)


def recv_framed(client_socket):
    """Receive one full length-prefixed message and return its decoded string."""
    header = _recv_exact(client_socket, _HEADER_SIZE)
    (length,) = struct.unpack(_HEADER, header)
    body = _recv_exact(client_socket, length)
    return body.decode('utf-8')


# Send a message over the socket
def send_message(client_socket, message):
    """Send a message to the server and return the decoded response."""
    send_framed(client_socket, message)
    return recv_framed(client_socket)

# Initialize the client socket
def init_rolldown_client(port):
    """Initialize the rolldown client on the given port number."""
    # Make sure that the client is not trying to use the same port as the server
    assert port != SERVER_PORT, 'Port 8000 is used by the server!'

    # Initialize the client socket and bind it to the given port
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    host = socket.gethostname()
    client_socket.bind((host, port))

    # Connect to server
    client_socket.connect((host, SERVER_PORT))

    # Return client socket
    return client_socket

def main(argv):
    """Start the client that sends messages to the server."""
    client_socket = init_rolldown_client(int(argv[1]))

    # Send messages
    while True:
        # Send messages
        message = input('Enter a message: ')
        response = send_message(client_socket, message)
        print('Server response:', response)

        # End process after quitting
        if response == 'Quitting...':
            print('Client closed successfully')
            break


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: python networking_client.py {port_number}')
        sys.exit()
    main(sys.argv)
