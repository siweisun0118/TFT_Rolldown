"""Receive messages and manage the rolldown."""

# Standard libraries
import json
import socket
import sys
import time
import threading


# Local files
from resources import SERVER_PORT, CHAMPION_POOL, read_database, serialize


# Lock that protects CHAMPION_POOL
pool_lock = threading.Lock()


def get_champion_pool():
    """Return the current state of the champion pool."""
    # LOCK SHOULD ALWAYS BE HELD HERE
    assert pool_lock.locked()

    # Build a copy of the champion pool and return it
    pool = {}
    for _, champions in CHAMPION_POOL.items():
        for unit in champions:
            if unit.name not in pool:
                pool[unit.name] = 1
            else:
                pool[unit.name] += 1
    return json.dumps(pool, default=serialize)


def client_thread(connection, addr, champions):
    """Start thread that handles a single client."""
    # Establish communication with client(s)
    while True:
        # Wait to receive messages
        message = connection.recv(1024).decode()
        print('Message received:', message, 'from connection', addr)

        # Respond to messages
        # Quit message
        if message == 'quit':
            connection.send('Quitting...'.encode())
            connection.close()
            return

        # Check pool message (message form: 'get_champion_pool')
        if message == 'pool':
            # Grab lock since we are reading from CHAMPION POOL
            with pool_lock:
                connection.send(f'{get_champion_pool()}\0'.encode())

        # Buy unit message (message form: 'buy_unit: {unit})
        elif 'buy' in message:
            # Get unit data
            unit = message.split(':')[1].strip()
            if unit in champions:
                unit_data = champions[unit]

                # Remove unit from pool if possible
                try:
                    # Grab lock since we are writing to CHAMPION_POOL
                    with pool_lock:
                        CHAMPION_POOL[unit_data.rarity].remove(unit_data)
                except ValueError:
                    connection.send(f'{unit} does not exist in pool!\0'.encode())
                    continue

                # Send response message
                connection.send(f'{unit} bought successfully\0'.encode())

            # Unknown unit
            else:
                connection.send(f'{unit} not found\0'.encode())

        # Unknown message
        else:
            connection.send(f'Unknown message: {message}\0'.encode())

        # Allow thread to sleep to save processor time
        time.sleep(0.5)


def init_rolldown_server(argv):
    """Initialize the server on port 8000 and receive messages.
       Also reads in database from input_dir."""
    # Read in database
    champions, _ = read_database(argv[1])

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
            args = (connection, addr, champions)
            new_thread = threading.Thread(target=client_thread, args=args)
            new_thread.start()
            client_threads.append(new_thread)

    # In case of error or keyboard interrupt, close all connections and join threads
    except (KeyboardInterrupt, BrokenPipeError):
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
