"""Receive messages and manage the rolldown."""

# Standard libraries
import json
import socket
import sys


# Local files
from resources import SERVER_PORT, CHAMPION_POOL, read_database, serialize


def close_connection(client_port):
    """Close the connection on the given client port."""
    client_port.close()
    return f'Port {client_port} has been closed'


def get_champion_pool():
    """Return the current state of the champion pool."""
    return json.dumps(CHAMPION_POOL, default=serialize)


# Dictionary of valid messages
# Map message -> function
valid_messages = {
    'quit': close_connection,
    'get_champion_pool': get_champion_pool
}


def init_rolldown_server(argv):
    """Initialize the server on port 8000 and receive messages.
       Also reads in database from input_dir."""
    # Read in database
    read_database(argv[1])

    # Initialize socket and bind to port SERVER_PORT
    main_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    host = socket.gethostname()
    main_socket.bind((host, SERVER_PORT))

    # Listen for connection
    main_socket.listen()

    # Establish connection with client(s)
    while True:
        # Accept connection from client
        connection, addr = main_socket.accept()
        print('Got connection from', addr)

        # Wait to receive messages
        message = connection.recv(1024).decode()
        print('Message received:', message, 'from connection', addr)

        # Respond to message
        if message not in valid_messages:
            connection.send(f'Unknown message: {message}'.encode())
        else:
            connection.send(valid_messages[message]().encode())


def main(argv):
    """Start the server."""
    init_rolldown_server(argv)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: python networking_server.py {input_dir}')
        sys.exit()
    main(sys.argv)
