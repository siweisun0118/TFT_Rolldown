"""Receive messages and manage the rolldown."""

# Standard libraries
import json
import socket
from sqlite3 import connect
import sys
import time
import threading


# Local files
from resources import SERVER_PORT, CHAMPION_POOL, read_database, serialize


END = False


def test_response():
    """Test the server."""
    return f'Hi this is {SERVER_PORT}'


def get_champion_pool():
    """Return the current state of the champion pool."""
    # GRAB LOCK
    pool = {}
    for cost in CHAMPION_POOL:
        for unit in CHAMPION_POOL[cost]:
            if unit.name not in pool:
                pool[unit.name] = 1
            else:
                pool[unit.name] += 1
    # RELEASE LOCK
    return json.dumps(pool, default=serialize)


# Dictionary of valid messages
# Map message -> function
valid_messages = {
    'test': test_response,
    'get_champion_pool': get_champion_pool
}


def client_thread(connection, addr):
    """Start thread that manages a single client."""
    # Establish communication with client(s)
    while True:
        # Wait to receive messages
        message = connection.recv(1024).decode()
        print('Message received:', message, 'from connection', addr)

        # Respond to message
        if message == 'quit':
            connection.send('Quitting...'.encode())
            connection.close()
            break
        elif message not in valid_messages:
            connection.send(f'Unknown message: {message} \0'.encode())
        else:
            connection.send(f'{valid_messages[message]()} \0'.encode())

        # Allow thread to sleep to save processor time
        time.sleep(0.5)


def init_rolldown_server(argv):
    """Initialize the server on port 8000 and receive messages.
       Also reads in database from input_dir."""
    # Read in database
    read_database(argv[1])

    # Initialize list to store client threads
    client_threads = []

    # Initialize socket and bind to port SERVER_PORT
    main_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    host = socket.gethostname()
    main_socket.bind((host, SERVER_PORT))

    # Start listening for connections
    main_socket.listen()
    print('Server on port', SERVER_PORT, 'listening for connections.')

    # Make connections and spin up client threads
    try:
        while True:
            # Accept connection from client
            connection, addr = main_socket.accept()
            print('Got connection from', addr)

            # Spin up thread for client
            new_thread = threading.Thread(target=client_thread, args=(connection, addr))
            new_thread.start()
            client_threads.append(new_thread)
    except:
        # In case of error or keyboard interrupt, close all connections and join threads
        END = True
        for thread in client_threads:
            assert isinstance(thread, threading.Thread)
            thread.join()
        print('All threads joined, shutting down...')


def main(argv):
    """Start the server."""
    init_rolldown_server(argv)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: python networking_server.py {input_dir}')
        sys.exit()
    main(sys.argv)
