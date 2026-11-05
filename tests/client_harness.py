"""Shared helpers for the client self-tests.

Every test starts the real server in "--backend mock" mode and drives the real
client program, so the wire format and the printed transcript are both tested.

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

passed = 0
failed = []


def make_workdir():
    """Temp folder inside the repository (the sandbox blocks the system temp dir)."""
    TEST_TMP.mkdir(exist_ok=True)
    workdir = TEST_TMP / ("run-%d-%d" % (os.getpid(), time.time_ns()))
    workdir.mkdir()
    return workdir


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


def report(tests):
    """Run (name, function) pairs and print the summary; return an exit code."""
    for name, fn in tests:
        check(name, fn)
    print("")
    print("%d passed, %d failed" % (passed, len(failed)))
    if failed:
        for name, error in failed:
            print("  - " + name + ": " + str(error))
        return 1
    return 0
