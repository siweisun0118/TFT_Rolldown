"""Send messages to the main rolldown server."""


# Standard libraries
import sys


# Local files
from resources import send_message, init_rolldown_client


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
        if 'Quitting' in response:
            print('Client closed successfully')
            break


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: python networking_client.py {port_number}')
        sys.exit()
    main(sys.argv)
