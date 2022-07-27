"""Receive messages and manage the rolldown."""

# Standard libraries
import json
from pathlib import Path
import socket
import sys
import threading


# Local files
from resources import SERVER_PORT, CHAMPION_POOL, serialize
from resources import POOL_LOCK, UNIT_AMOUNT_LEVEL, CHAMPION_AMOUNTS
from resources import Unit, Trait


class UnknownChampionError(Exception):
    """Unknown Champion Error."""
    pass


class UnknownMessageError(Exception):
    """Unknown Message Error."""
    pass


# Helper function to read input directory
def populate_champ_pool(input_dir):
    """Read in units and traits."""
    assert POOL_LOCK.locked(), 'POOL_LOCK must be held to access CHAMPION POOL'

    for cost in CHAMPION_POOL:
        CHAMPION_POOL[cost] = []

    # Read in units
    with open(Path(input_dir) / 'champions.json', encoding='utf-8') as champions_file:
        champions_list = json.loads(champions_file.read())

    # Read in traits
    with open(Path(input_dir) / 'traits.json', encoding='utf-8') as traits_file:
        traits_list = json.loads(traits_file.read())

    # Parse unit data
    champions = {}
    for champ in champions_list:
        # If champion has fewer than 2 traits, ignore it
        # Since it is a target dummy, voidspawn, tome, Veigar, etc.
        if len(champ['traits']) < 2:
            continue

        # Add to champions list
        champions[champ['name']] = Unit(champ['cost'], champ['name'], \
            champ['traits'], champ['championId'])

        # Add to champion pool
        CHAMPION_POOL[champ['cost']] += [champions[champ['name']]] * \
            CHAMPION_AMOUNTS[champ['cost']]

    # Parse trait data
    traits = {}
    for trait in traits_list:
        # Extract trait breakpoints and styles from trait data
        breakpoints = []
        styles = []
        for b_p in trait['sets']:
            breakpoints.append(b_p['min'])
            styles.append(b_p['style'])

        # Add to traits list
        traits[trait['name']] = Trait(trait['name'], breakpoints, styles)

    return champions, traits


def get_champion_pool():
    """Return the current state of the champion pool."""
    assert POOL_LOCK.locked(), 'POOL_LOCK must be held to access CHAMPION POOL'

    # Build a copy of the champion pool and return it
    pool = {}
    for _, champions in CHAMPION_POOL.items():
        for unit in champions:
            if unit.name not in pool:
                pool[unit.name] = 1
            else:
                pool[unit.name] += 1
    return f'{json.dumps(pool, default=serialize)}\0'.encode()


def get_full_pool():
    """Return the current state of the champion pool.
       Includes champion information."""
    assert POOL_LOCK.locked(), 'POOL_LOCK must be held to access CHAMPION POOL'

    return f'{json.dumps(CHAMPION_POOL, default=serialize)}\0'.encode()


def buy_champion(message, connection, champions):
    """Remove a champion from the pool by buying it."""
    assert POOL_LOCK.locked(), 'POOL_LOCK must be held to access CHAMPION POOL'

    # Get unit data
    unit = message.split(':')[1].strip()
    if unit in champions:
        unit_obj = champions[unit]

        # Remove unit from pool
        # Grab lock since we are writing to CHAMPION_POOL
        assert unit_obj in CHAMPION_POOL[unit_obj.rarity], \
            'Error: unit not found in champion pool'
        CHAMPION_POOL[unit_obj.rarity].remove(unit_obj)

        # Send response message
        connection.send(f'{unit} bought successfully\0'.encode())

    # Unknown unit
    else:
        connection.send(f'{unit} not found\0'.encode())
        raise UnknownChampionError(unit)


def sell_champion(message, connection, champions):
    """Add a champion to the pool by selling it."""
    assert POOL_LOCK.locked(), 'POOL_LOCK must be held to access CHAMPION POOL'

    # Get information about the unit
    unit, level = message.split(':')[1:]
    unit = unit.strip()
    amount = UNIT_AMOUNT_LEVEL[int(level)]

    # Add unit to pool
    if unit in champions:
        unit_obj = champions[unit]

        # Can sell multiple champions at once (i.e. selling upgraded unit)
        for _ in range(amount):
            CHAMPION_POOL[unit_obj.rarity].append(unit_obj)

        # Send response confirming sell
        connection.send(f'Successfully sold {amount} {unit} units\0'.encode())

    # Unknown unit
    else:
        connection.send(f'{unit} not found\0'.encode())
        raise UnknownChampionError(unit)


def shutdown(main_socket, client_threads):
    """Shutdown server and close all connections."""
    main_socket.close()
    for thread in client_threads:
        thread.join()
    print('Server shutting down...')


def client_thread(connection, addr, champions):
    """Start thread that handles a single client."""
    # Establish communication with client(s)
    try:
        while True:
            # Wait to receive messages
            message = connection.recv(1024).decode()
            print('Message received:', message, 'from connection', addr)

            # Respond to messages
            # Quit message
            if message == 'quit':
                connection.send('Quitting...\0'.encode())
                connection.close()
                return

            # Check pool message (message form: 'pool')
            if message == 'pool':
                with POOL_LOCK:
                    connection.send(get_champion_pool())

            elif message == 'full_pool':
                # Function will grab POOL_LOCK
                with POOL_LOCK:
                    connection.send(get_full_pool())

            # Buy unit message (message form: 'buy: {unit}')
            elif 'buy' in message:
                with POOL_LOCK:
                    buy_champion(message, connection, champions)

            # Sell unit message (message form: 'sell: {unit}: {amount})
            elif 'sell' in message:
                with POOL_LOCK:
                    sell_champion(message, connection, champions)

            # Reset champion pool
            elif message == 'reset':
                with POOL_LOCK:
                    populate_champ_pool(sys.argv[1])
                    connection.send('CHAMPION_POOL reset\n'.encode())

            # TODO: Shutdown server and close all connections
            elif message == 'shutdown':
                connection.send('Quitting...\0'.encode())
                connection.close()
                return

            # Unknown message
            else:
                connection.send(f'Unknown message: {message}\0'.encode())
                raise UnknownMessageError(message)

    except (KeyboardInterrupt, BrokenPipeError, ConnectionAbortedError):
        print(addr, 'has closed the connection.')
        return


def init_rolldown_server(argv):
    """Initialize the server on port 8000 and receive messages.
       Also reads in database from input_dir."""
    # Read in database
    with POOL_LOCK:
        champions, _ = populate_champ_pool(argv[1])

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
    except (KeyboardInterrupt, BrokenPipeError, ConnectionAbortedError):
        shutdown(main_socket, client_threads)


def main(argv):
    """Start the server."""
    init_rolldown_server(argv)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: python networking_server.py {input_dir}')
        sys.exit()
    main(sys.argv)
