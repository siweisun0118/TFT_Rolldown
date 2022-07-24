"""Send messages to the main rolldown server."""


# Standard libraries
import socket
import sys


# Local files
from resources import SERVER_PORT


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

    # Get client up and running
    while True:
        # Send messages
        message = input('Enter a message: ')
        client_socket.send(message.encode())

        # Get response
        while True:
            # Get message in chunks
            response = client_socket.recv(65536).decode()
            if not response:
                break
        print('Server response:', response)


def main(argv):
    """Start the client that sends messages to the server."""
    init_rolldown_client(int(argv[1]))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: python networking_client.py {port_number}')
        sys.exit()
    main(sys.argv)
