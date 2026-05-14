"""Send messages to the main rolldown server."""


# Standard libraries
import socket
import sys

# Local imports
from shared.rolldown_enums import SERVER_PORT


### NETWORKING CLIENT FUNCTIONS ###
# Send a message over the socket
def send_message(client_socket, message):
    """Send a message to the server and get response."""
    client_socket.send(message.encode())

    # Get response
    response = ''
    while True:
        # Get message in chunks
        chunk = client_socket.recv(1024).decode()
        response += chunk
        if not chunk or chunk[-1] == '\0':
            break

    return response[:-1]


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
### END NETWORKING CLIENT FUNCTIONS ###

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
