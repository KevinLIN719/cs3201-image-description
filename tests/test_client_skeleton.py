"""Self-test for the client skeleton (板块 2 acceptance).

Run:
    D:\\CityU\\CS3201_OIDS\\.venv\\Scripts\\python.exe tests\\test_client_skeleton.py

Covers: the client prints the exact "client: " / "server: " prefixes, an
unknown command is answered by the real server reply and the connection
stays usable, the not-yet-implemented commands do not close the connection,
QUIT ends only that client (the server keeps accepting other clients and a
second connection keeps working), and a refused connection reports an error
instead of crashing.

Note: stdout/stderr are redirected through temporary files instead of pipes
because the DSH sandbox on this machine forbids creating pipes
(PermissionError [WinError 5]); this also works outside the sandbox.
"""
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
TEST_TMP = REPO / ".test-tmp"


def make_workdir():
    """Temp folder inside the repository (the sandbox blocks the system temp dir)."""
    TEST_TMP.mkdir(exist_ok=True)
    workdir = TEST_TMP / ("run-%d-%d" % (os.getpid(), time.time_ns()))
    workdir.mkdir()
    return workdir

passed = 0
failed = []


def check(name, fn):
    global passed
    try:
        fn()
        passed += 1
        print("  PASS  " + name)
    except AssertionError as error:
        failed.append((name, error))
        print("  FAIL  " + name + "  -> " + str(error))
    except Exception as error:
        failed.append((name, error))
        print("  FAIL  " + name + "  -> " + type(error).__name__ + ": " + str(error))


def free_port():
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def start_server(port, workdir):
    """Start the mock server; its output goes to a file we poll for READY."""
    log_path = Path(workdir) / "server.log"
    log = open(log_path, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        [PYTHON, "ImageDescriptionServer.py", "--backend", "mock",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(REPO), stdin=subprocess.DEVNULL, stdout=log,
        stderr=subprocess.STDOUT)
    proc._log_path = log_path
    proc._log_handle = log
    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        text = log_path.read_text(encoding="utf-8", errors="replace")
        if "READY" in text:
            return proc
        time.sleep(0.1)
    proc.kill()
    raise AssertionError("server did not print READY: "
                         + log_path.read_text(encoding="utf-8", errors="replace"))


def stop_server(proc):
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)
    proc._log_handle.close()


def run_client(port, stdin_text, workdir, timeout=60):
    """Run the client with the given stdin text and return (returncode, output)."""
    name = "client-%d" % time.time_ns()
    in_path = Path(workdir) / (name + ".in")
    out_path = Path(workdir) / (name + ".out")
    in_path.write_text(stdin_text, encoding="utf-8")
    with open(in_path, "r", encoding="utf-8") as stdin, \
            open(out_path, "w", encoding="utf-8", errors="replace") as stdout:
        result = subprocess.run(
            [PYTHON, "ImageDescriptionClient.py", "127.0.0.1", str(port)],
            cwd=str(REPO), stdin=stdin, stdout=stdout,
            stderr=subprocess.STDOUT, timeout=timeout)
    return result.returncode, out_path.read_text(encoding="utf-8", errors="replace")


def lines_of(text):
    return [line for line in text.splitlines() if line.strip()]


def assert_prefixed(text):
    for line in lines_of(text):
        assert line.startswith("client: ") or line.startswith("server: "), \
            "unexpected output line: " + repr(line)


def with_server(test_body):
    workdir = make_workdir()
    port = free_port()
    server = start_server(port, workdir)
    try:
        test_body(port, workdir)
    finally:
        stop_server(server)
        shutil.rmtree(workdir, ignore_errors=True)


def t_unknown_command_gets_server_reply():
    def body(port, workdir):
        code, text = run_client(port, "UNKNOWN\nQUIT\n", workdir)
        assert code == 0, "exit code %r, output=%r" % (code, text)
        out = lines_of(text)
        assert out == ["client: UNKNOWN",
                       "server: ERROR - Command not understood",
                       "client: QUIT",
                       "server: OK"], "output was: %r" % (out,)
        assert_prefixed(text)
    with_server(body)


def t_connection_survives_unknown_command():
    def body(port, workdir):
        code, text = run_client(port, "UNKNOWN\nUNKNOWN\nQUIT\n", workdir)
        out = lines_of(text)
        assert out == ["client: UNKNOWN",
                       "server: ERROR - Command not understood",
                       "client: UNKNOWN",
                       "server: ERROR - Command not understood",
                       "client: QUIT",
                       "server: OK"], "output was: %r" % (out,)
    with_server(body)


def t_stub_commands_do_not_close_connection():
    def body(port, workdir):
        code, text = run_client(
            port, "UPLOAD\nLIST\nDESCRIBE\nDOWNLOAD\nREMOVE\nUNKNOWN\nQUIT\n", workdir)
        out = lines_of(text)
        for name in ("UPLOAD", "LIST", "DESCRIBE", "DOWNLOAD", "REMOVE"):
            assert "client: TODO - %s is not implemented yet" % name in out, \
                "missing TODO line for " + name + ", output: %r" % (out,)
        # After five stubs the connection is still alive: the real server
        # answers the unknown command and then QUIT.
        assert out[-3:] == ["server: ERROR - Command not understood",
                            "client: QUIT",
                            "server: OK"], "output was: %r" % (out,)
        assert_prefixed(text)
    with_server(body)


def t_quit_closes_only_its_own_client():
    def body(port, workdir):
        code, text = run_client(port, "QUIT\n", workdir)
        assert lines_of(text) == ["client: QUIT", "server: OK"], \
            "QUIT output was: %r" % (lines_of(text),)
        assert code == 0

        # The server must still accept a new client and keep its shared state.
        code, text = run_client(port, "UNKNOWN\nQUIT\n", workdir)
        assert lines_of(text) == ["client: UNKNOWN",
                                  "server: ERROR - Command not understood",
                                  "client: QUIT",
                                  "server: OK"], "second client output was: %r" % (lines_of(text),)
        assert code == 0
    with_server(body)


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
    with_server(body)


def t_connection_refused_reports_error():
    workdir = make_workdir()
    try:
        port = free_port()
        code, text = run_client(port, "QUIT\n", workdir)
        assert code != 0, "expected a non-zero exit code"
        assert "client: ERROR - Cannot connect to 127.0.0.1:%d" % port in text, \
            "output was: %r" % (text,)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def t_eof_input_exits_cleanly():
    def body(port, workdir):
        # EOF with no command (for example Ctrl+Z) must end the client
        # without an error and without killing the server.
        code, text = run_client(port, "", workdir)
        assert code == 0, "exit code %r, output %r" % (code, text)
        code, text = run_client(port, "QUIT\n", workdir)
        assert lines_of(text) == ["client: QUIT", "server: OK"], "%r" % (lines_of(text),)
    with_server(body)


def main():
    print("Client skeleton self-test")
    check("unknown command prints the real server reply", t_unknown_command_gets_server_reply)
    check("connection survives an unknown command", t_connection_survives_unknown_command)
    check("stub commands keep the connection open", t_stub_commands_do_not_close_connection)
    check("QUIT closes only its own client", t_quit_closes_only_its_own_client)
    check("two open connections, one QUIT", t_two_open_connections_one_quit)
    check("refused connection reports an error", t_connection_refused_reports_error)
    check("EOF input exits cleanly", t_eof_input_exits_cleanly)

    print("")
    print("%d passed, %d failed" % (passed, len(failed)))
    if failed:
        for name, error in failed:
            print("  - " + name + ": " + str(error))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
