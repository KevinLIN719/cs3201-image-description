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
import os
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


class ConnectionClosed(Exception):
    """Raised when the server closes the connection while a reply is due."""


class LocalError(Exception):
    """A problem detected on the client before anything was sent."""


def receive_text_reply(conn):
    """Receive one text message and decode it.

    Raises ConnectionClosed when the server closes instead of replying.
    """
    reply = receive_message(conn)
    if reply is None:
        raise ConnectionClosed("The server closed the connection")
    return reply.decode("utf-8", errors="replace")


def exchange(conn, command_text):
    """Send one text command and return the single text reply.

    Raises LocalError when the command is longer than the server accepts and
    ConnectionClosed when the server closes before replying.
    """
    encoded = command_text.encode("utf-8")
    if len(encoded) > MAX_COMMAND_BYTES:
        raise LocalError("Command is too long (limit: %d bytes)" % MAX_COMMAND_BYTES)
    send_message(conn, encoded)
    return receive_text_reply(conn)


# ===== COMMAND HANDLERS =====
# Each handler receives the connected socket and reads the extra input lines
# that its command needs (the assignment puts every value on its own line).

class InputClosed(Exception):
    """Raised when the user input ends in the middle of a command."""


def read_value_line():
    """Read one value line (a path or an image ID) belonging to a command."""
    line = read_input_line()
    if line is None:
        raise InputClosed()
    return line.strip()


def read_argument(rest):
    """Return the argument typed on the command line, else read the next line.

    The assignment puts every value on its own line; accepting "UPLOAD x.jpg"
    as well only makes the client more forgiving for a human user.
    """
    return rest if rest else read_value_line()


def check_upload_file(path):
    """Validate a local file before uploading.

    Returns (image_bytes, filename). Raises LocalError with the message that
    has to be printed instead of contacting the server.
    """
    if not path.is_file():
        raise LocalError("File not found")
    if not os.access(path, os.R_OK):
        raise LocalError("File is not readable")
    try:
        if path.stat().st_size > MAX_UPLOAD_BYTES:
            raise LocalError("File exceeds 5 MiB")
        data = path.read_bytes()
    except OSError:
        raise LocalError("Cannot read the file")

    filename = path.name
    if (not filename or len(filename) > MAX_FILENAME_CHARS
            or filename in {".", ".."}
            or any(char in filename for char in "/\\\r\n\x00")):
        raise LocalError("Invalid filename")
    return data, filename


def command_upload(conn, rest):
    """UPLOAD: send the file name, then the raw image bytes, then the reply."""
    path_text = read_argument(rest)
    if not path_text:
        print_client_error("Missing local path")
        return
    try:
        data, filename = check_upload_file(Path(path_text))
    except LocalError as error:
        print_client_error(str(error))
        return
    # The protocol uploads the bare file name, never the local path.
    send_message(conn, ("UPLOAD " + filename).encode("utf-8"))
    send_message(conn, data)
    print_server_reply(receive_text_reply(conn))


def command_list(conn, rest):
    """LIST: print the shared image list exactly as the server formats it."""
    print_server_reply(exchange(conn, "LIST"))


def command_describe(conn, rest):
    """DESCRIBE: ask for the description of one image ID."""
    image_id = read_argument(rest)
    if not image_id:
        print_client_error("Missing image ID")
        return
    print_server_reply(exchange(conn, "DESCRIBE " + image_id))


def command_download(conn, rest):
    """DOWNLOAD: receive the text reply and, when it is OK, the image bytes."""
    image_id = read_argument(rest)
    if not image_id:
        print_client_error("Missing image ID")
        return
    path_text = read_value_line()
    if not path_text:
        print_client_error("Missing destination path")
        return

    target = Path(path_text)
    if target.exists():
        # Never overwrite an existing local file, and do not send the command.
        print_client_error("File already exists: " + path_text)
        return

    reply = exchange(conn, "DOWNLOAD " + image_id)
    print_server_reply(reply)
    if not reply.startswith("OK"):
        # The server sends no image message after an error reply, so the
        # session stays in sync and the connection can be used again.
        return

    data = receive_message(conn)
    if data is None:
        raise ConnectionClosed("The server closed the connection")
    try:
        target.write_bytes(data)
    except OSError:
        print_client_error("Cannot save the image to " + path_text)
        return
    print("client: Saved to " + path_text, flush=True)


def command_remove(conn, rest):
    """REMOVE: delete one image on the server."""
    image_id = read_argument(rest)
    if not image_id:
        print_client_error("Missing image ID")
        return
    print_server_reply(exchange(conn, "REMOVE " + image_id))


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
        parts = line.split(None, 1)
        command = parts[0].upper()
        rest = parts[1].strip() if len(parts) > 1 else ""

        try:
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

            handler(conn, rest)
        except InputClosed:
            # The input ended while a command still waited for a value line.
            print("", flush=True)
            return
        except LocalError as error:
            # Nothing was sent, so the connection is still usable.
            print_client_error(str(error))


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
