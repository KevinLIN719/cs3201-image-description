"""Self-test for the client skeleton (板块 2 acceptance).

Run:
    .venv\\Scripts\\python.exe tests\\test_client_skeleton.py

Covers: the client prints the exact "client: " / "server: " prefixes, an
unknown command is answered by the real server reply and the connection
stays usable, QUIT ends only that client (the server keeps accepting other
clients and a second connection keeps working), and a refused connection
reports an error instead of crashing.
"""
import shutil
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import client_harness as harness


def t_unknown_command_gets_server_reply():
    def body(port, workdir):
        code, text = harness.run_client(port, "UNKNOWN\nQUIT\n", workdir)
        assert code == 0, "exit code %r, output=%r" % (code, text)
        out = harness.lines_of(text)
        assert out == ["client: UNKNOWN",
                       "server: ERROR - Command not understood",
                       "client: QUIT",
                       "server: OK"], "output was: %r" % (out,)
        harness.assert_prefixed(text)
    harness.with_server(body)


def t_connection_survives_unknown_command():
    def body(port, workdir):
        code, text = harness.run_client(port, "UNKNOWN\nUNKNOWN\nQUIT\n", workdir)
        out = harness.lines_of(text)
        assert out == ["client: UNKNOWN",
                       "server: ERROR - Command not understood",
                       "client: UNKNOWN",
                       "server: ERROR - Command not understood",
                       "client: QUIT",
                       "server: OK"], "output was: %r" % (out,)
    harness.with_server(body)


def t_empty_and_blank_lines_are_ignored():
    def body(port, workdir):
        code, text = harness.run_client(port, "\n\n   \nQUIT\n", workdir)
        out = harness.lines_of(text)
        # The blank lines are echoed, but nothing is sent to the server for them.
        assert out[-2:] == ["client: QUIT", "server: OK"], \
            "output was: %r" % (out,)
        assert all(line.startswith("client:") for line in out[:-2]), \
            "a blank line must not reach the server: %r" % (out,)
    harness.with_server(body)


def t_quit_closes_only_its_own_client():
    def body(port, workdir):
        code, text = harness.run_client(port, "QUIT\n", workdir)
        assert harness.lines_of(text) == ["client: QUIT", "server: OK"], \
            "QUIT output was: %r" % (harness.lines_of(text),)
        assert code == 0

        # The server must still accept a new client and keep its shared state.
        code, text = harness.run_client(port, "UNKNOWN\nQUIT\n", workdir)
        assert harness.lines_of(text) == ["client: UNKNOWN",
                                          "server: ERROR - Command not understood",
                                          "client: QUIT",
                                          "server: OK"], \
            "second client output was: %r" % (harness.lines_of(text),)
        assert code == 0
    harness.with_server(body)


def t_two_open_connections_one_quit():
    """Two connections are open at the same time; closing one keeps the other."""
    def body(port, workdir):
        first = socket.create_connection(("127.0.0.1", port))
        second = socket.create_connection(("127.0.0.1", port))
        try:
            def send(sock, payload):
                sock.sendall(("%010d" % len(payload)).encode("ascii") + payload)

            def receive(sock):
                header = b""
                while len(header) < 10:
                    chunk = sock.recv(10 - len(header))
                    assert chunk, "connection closed while reading header"
                    header += chunk
                length = int(header.decode("ascii"))
                data = b""
                while len(data) < length:
                    chunk = sock.recv(length - len(data))
                    assert chunk, "connection closed while reading payload"
                    data += chunk
                return data.decode("utf-8")

            send(first, b"LIST")
            assert receive(first) == "OK\nNo images"
            send(second, b"LIST")
            assert receive(second) == "OK\nNo images"

            # Close only the first connection.
            send(first, b"QUIT")
            assert receive(first) == "OK"
            first.close()

            # The second connection still works on the same running server.
            send(second, b"UNKNOWN")
            assert receive(second) == "ERROR - Command not understood"
            send(second, b"QUIT")
            assert receive(second) == "OK"
            second.close()
        finally:
            for sock in (first, second):
                try:
                    sock.close()
                except OSError:
                    pass
    harness.with_server(body)


def t_connection_refused_reports_error():
    workdir = harness.make_workdir()
    try:
        port = harness.free_port()
        code, text = harness.run_client(port, "QUIT\n", workdir)
        assert code != 0, "expected a non-zero exit code"
        assert "client: ERROR - Cannot connect to 127.0.0.1:%d" % port in text, \
            "output was: %r" % (text,)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def t_eof_input_exits_cleanly():
    def body(port, workdir):
        # EOF with no command (for example Ctrl+Z) must end the client
        # without an error and without killing the server.
        code, text = harness.run_client(port, "", workdir)
        assert code == 0, "exit code %r, output %r" % (code, text)
        code, text = harness.run_client(port, "QUIT\n", workdir)
        assert harness.lines_of(text) == ["client: QUIT", "server: OK"], \
            "%r" % (harness.lines_of(text),)
    harness.with_server(body)


def main():
    print("Client skeleton self-test")
    return harness.report([
        ("unknown command prints the real server reply", t_unknown_command_gets_server_reply),
        ("connection survives an unknown command", t_connection_survives_unknown_command),
        ("blank input lines are ignored", t_empty_and_blank_lines_are_ignored),
        ("QUIT closes only its own client", t_quit_closes_only_its_own_client),
        ("two open connections, one QUIT", t_two_open_connections_one_quit),
        ("refused connection reports an error", t_connection_refused_reports_error),
        ("EOF input exits cleanly", t_eof_input_exits_cleanly),
    ])


if __name__ == "__main__":
    sys.exit(main())
