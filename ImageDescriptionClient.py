"""Client for the Online Image Description System (CS3201 programming assignment).

The client keeps one persistent TCP connection to the server and implements the
six commands UPLOAD, LIST, DESCRIBE, DOWNLOAD, REMOVE and QUIT.

Wire format (identical to the server):
    one message = 10 ASCII decimal digits (zero padded length) + payload bytes
    the length counts payload bytes only and must be 1..5 MiB

Run:
    python ImageDescriptionClient.py 127.0.0.1 18333
    python ImageDescriptionClient.py --host 127.0.0.1 --port 18333
"""
import argparse
import socket
import sys
from pathlib import Path

HEADER_SIZE = 10
MAX_MESSAGE_BYTES = 5 * 1024 * 1024
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_COMMAND_BYTES = 1024
MAX_FILENAME_CHARS = 255
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18333


# ===== PROTOCOL LAYER =====
# The client is a separate program, so it carries its own copy of the wire
# format helpers instead of importing the server file (importing the server
# would also load the local AI model and its dependencies).

def recv_exact(conn, count):
    """Read exactly count bytes, or report that the connection closed.

    Returns the data when all count bytes have arrived.
    Returns None if the peer closes before this call receives any bytes.
    Raises ConnectionError if it closes after some bytes arrive.
    """
    data = b""
    while len(data) < count:
        # One recv call may return fewer bytes than requested.
        chunk = conn.recv(count - len(data))
        if chunk == b"":
            if data == b"":
                return None
            raise ConnectionError("Connection closed during a message")
        data += chunk
    return data


def receive_message(conn):
    """Receive one complete message.

    Returns the payload bytes (without the 10-byte header), or None if the
    server closes the connection before any byte of a new message arrives.
    """
    header = recv_exact(conn, HEADER_SIZE)
    if header is None:
        return None
    try:
        digits = header.decode("ascii")
    except UnicodeDecodeError:
        raise ValueError("Invalid length header")
    if not digits.isdigit():
        raise ValueError("Invalid length header")
    length = int(digits)
    if not 1 <= length <= MAX_MESSAGE_BYTES:
        raise ValueError("Invalid message length")
    data = recv_exact(conn, length)
    if data is None:
        raise ConnectionError("Connection closed during a message")
    return data


def send_message(conn, payload):
    """Send the supplied bytes as one complete length-prefixed message."""
    payload = bytes(payload)
    length = len(payload)
    if not 1 <= length <= MAX_MESSAGE_BYTES:
        raise ValueError("Invalid message length")
    header = ("%010d" % length).encode("ascii")
    conn.sendall(header + payload)


# ===== SCREEN OUTPUT =====

def read_input_line():
    """Read one line of terminal input and show it with the client: prefix.

    When stdin is a real terminal the prompt itself produces the
    "client: <typed line>" line.  When stdin is redirected (for example in an
    automated test) the line is echoed after it has been read, so the visible
    output is the same in both cases.
    """
    try:
        if sys.stdin is not None and sys.stdin.isatty():
            return input("client: ")
        line = input()
        print("client: " + line, flush=True)
        return line
    except EOFError:
        return None


def print_server_reply(text):
    """Print a server reply, one line per line, each with the server: prefix."""
    for line in text.split("\n"):
        print("server: " + line, flush=True)


def print_client_error(text):
    """Print a client-side error (nothing was sent to the server)."""
    print("client: ERROR - " + text, flush=True)


def exchange(conn, command_text):
    """Send one text command and return the single text reply.

    Raises ConnectionClosed when the server closes before replying.
    """
    send_message(conn, command_text.encode("utf-8"))
    reply = receive_message(conn)
    if reply is None:
        raise ConnectionClosed("The server closed the connection")
    return reply.decode("utf-8", errors="replace")


class ConnectionClosed(Exception):
    """Raised when the server closes the connection while a reply is due."""


# ===== COMMAND HANDLERS =====
# Each handler receives the connected socket and reads the extra input lines
# that its command needs (the assignment puts every value on its own line).

def command_upload(conn):
    """UPLOAD: upload one local JPEG/PNG file (implemented in the next step)."""
    print("client: TODO - UPLOAD is not implemented yet", flush=True)


def command_list(conn):
    """LIST: show the shared image list (implemented in the next step)."""
    print("client: TODO - LIST is not implemented yet", flush=True)


def command_describe(conn):
    """DESCRIBE: show one image description (implemented in the next step)."""
    print("client: TODO - DESCRIBE is not implemented yet", flush=True)


def command_download(conn):
    """DOWNLOAD: save one image locally (implemented in the next step)."""
    print("client: TODO - DOWNLOAD is not implemented yet", flush=True)


def command_remove(conn):
    """REMOVE: delete one image on the server (implemented in the next step)."""
    print("client: TODO - REMOVE is not implemented yet", flush=True)


COMMANDS = {
    "UPLOAD": command_upload,
    "LIST": command_list,
    "DESCRIBE": command_describe,
    "DOWNLOAD": command_download,
    "REMOVE": command_remove,
}


# ===== MAIN LOOP =====

def run_session(conn):
    """Read commands until QUIT, EOF or a lost connection."""
    while True:
        line = read_input_line()
        if line is None:
            # End of input: leave without sending anything else.
            print("", flush=True)
            return
        line = line.strip()
        if not line:
            continue
        command = line.split(None, 1)[0].upper()

        if command == "QUIT":
            reply = exchange(conn, line)
            print_server_reply(reply)
            if reply.split("\n")[0].strip() == "OK":
                return
            continue

        handler = COMMANDS.get(command)
        if handler is None:
            # Unknown command: the server decides and describes the error,
            # the client just prints the real reply and keeps the connection.
            print_server_reply(exchange(conn, line))
            continue

        handler(conn)


def parse_args(argv):
    """Accept both the reference form 'host port' and --host/--port flags."""
    parser = argparse.ArgumentParser(
        description="Client for the Online Image Description System.")
    parser.add_argument("host", nargs="?", default=None,
                        help="server IPv4 address (default: 127.0.0.1)")
    parser.add_argument("port", nargs="?", type=int, default=None,
                        help="server TCP port (default: 18333)")
    parser.add_argument("--host", dest="host_flag", default=None,
                        help="server IPv4 address (default: 127.0.0.1)")
    parser.add_argument("--port", dest="port_flag", type=int, default=None,
                        help="server TCP port (default: 18333)")
    args = parser.parse_args(argv)
    host = args.host_flag if args.host_flag is not None else args.host
    port = args.port_flag if args.port_flag is not None else args.port
    return DEFAULT_HOST if host is None else host, DEFAULT_PORT if port is None else port


def main(argv=None):
    host, port = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        conn = socket.create_connection((host, port))
    except OSError as error:
        print_client_error("Cannot connect to %s:%d (%s)" % (host, port, error))
        return 1

    try:
        run_session(conn)
    except EOFError:
        print("", flush=True)
    except KeyboardInterrupt:
        print("", flush=True)
    except ConnectionClosed as error:
        print_client_error(str(error))
    except (OSError, ConnectionError) as error:
        print_client_error("Connection failed (%s)" % error)
    finally:
        try:
            conn.close()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
