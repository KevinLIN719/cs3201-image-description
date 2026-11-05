"""Self-test for Part 1 of ImageDescriptionServer.py (板块 1 验收).

Run:
    D:\\CityU\\CS3201_OIDS\\.venv\\Scripts\\python.exe test_server_protocol.py

Covers: header format, round trip on several sizes, EOF before a message
(None), EOF in the middle of a message (ConnectionError), invalid headers,
send_message rejection of empty/oversized payloads, and a real
create_listener / accept_client loop over loopback.
"""
import socket
import sys
import threading

REPO = r"D:\CityU\CS3201_OIDS"
sys.path.insert(0, REPO)

import ImageDescriptionServer as srv

HEADER = srv.HEADER_SIZE
MAXB = srv.MAX_MESSAGE_BYTES

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


def pair():
    """Return two connected sockets over loopback."""
    a, b = socket.socketpair() if hasattr(socket, "socketpair") else (None, None)
    if a is not None:
        return a, b
    listener = srv.create_listener("127.0.0.1", 0)
    port = listener.getsockname()[1]
    client = socket.create_connection(("127.0.0.1", port))
    server, _ = srv.accept_client(listener)
    listener.close()
    return server, client


# ---------- 1. header format ----------
def t_header_format():
    server, client = pair()
    srv.send_message(client, b"HELLO")
    raw = b""
    while len(raw) < HEADER + 5:
        raw += server.recv(HEADER + 5 - len(raw))
    assert raw == b"0000000005HELLO", raw
    server.close()
    client.close()


def t_header_padding_wide():
    """A long payload still gets exactly 10 header bytes."""
    server, client = pair()
    payload = b"A" * 123457
    srv.send_message(client, payload)
    raw = b""
    while len(raw) < HEADER:
        raw += server.recv(HEADER - len(raw))
    assert raw == b"0000123457", raw
    body = b""
    while len(body) < len(payload):
        body += server.recv(len(payload) - len(body))
    assert body == payload
    server.close()
    client.close()


# ---------- 2. round trip ----------
def t_roundtrip_sizes():
    server, client = pair()
    for size in (1, 5, 10, 1024, 65536, 1024 * 1024):
        payload = bytes((i % 251 for i in range(size)))
        srv.send_message(client, payload)
        got = srv.receive_message(server)
        assert got == payload, "size %d mismatch" % size
    server.close()
    client.close()


def t_bytearray_payload():
    server, client = pair()
    srv.send_message(client, bytearray(b"abc"))
    assert srv.receive_message(server) == b"abc"
    server.close()
    client.close()


# ---------- 3. EOF semantics ----------
def t_eof_before_message_is_none():
    server, client = pair()
    client.close()
    result = srv.receive_message(server)
    assert result is None, result
    server.close()


def t_eof_partial_header_raises():
    server, client = pair()
    client.sendall(b"0000")
    client.close()
    try:
        srv.receive_message(server)
    except ConnectionError:
        server.close()
        return
    raise AssertionError("expected ConnectionError")


def t_eof_partial_body_raises():
    server, client = pair()
    client.sendall(b"0000000010ABC")
    client.close()
    try:
        srv.receive_message(server)
    except ConnectionError:
        server.close()
        return
    raise AssertionError("expected ConnectionError")


# ---------- 4. invalid headers ----------
def expect_value_error(raw_bytes, label):
    server, client = pair()
    client.sendall(raw_bytes)
    try:
        srv.receive_message(server)
    except ValueError:
        server.close()
        client.close()
        return
    except Exception as error:
        raise AssertionError(label + " raised " + type(error).__name__)
    raise AssertionError(label + " did not raise ValueError")


def t_bad_header_nondigit():
    expect_value_error(b"00000ABCDE", "non-digit")


def t_bad_header_zero_length():
    expect_value_error(b"0000000000", "zero length")


def t_bad_header_too_long():
    expect_value_error(b"9999999999", "oversized")


# ---------- 5. send_message validation ----------
def t_send_rejects_empty():
    server, client = pair()
    try:
        srv.send_message(client, b"")
    except ValueError:
        server.close()
        client.close()
        return
    raise AssertionError("empty payload accepted")


def t_send_rejects_oversized():
    server, client = pair()
    try:
        srv.send_message(client, b"x" * (MAXB + 1))
    except ValueError:
        server.close()
        client.close()
        return
    raise AssertionError("oversized payload accepted")


def t_send_accepts_max_size():
    """MAX_MESSAGE_BYTES exactly is still legal (memory-heavy, so only header-checked)."""
    server, client = pair()
    header_holder = {}

    def reader():
        raw = b""
        while len(raw) < HEADER:
            raw += server.recv(HEADER - len(raw))
        header_holder["h"] = raw
        server.close()

    thread = threading.Thread(target=reader)
    thread.start()
    payload = b"z" * MAXB
    srv.send_message(client, payload)
    thread.join()
    client.close()
    assert header_holder["h"] == b"0005242880", header_holder["h"]


# ---------- 6. listener / accept / close over real loopback ----------
def t_listener_accept_loopback():
    listener = srv.create_listener("127.0.0.1", 0)
    port = listener.getsockname()[1]
    assert port > 0, port

    box = {}

    def server_side():
        conn, address = srv.accept_client(listener)
        box["address"] = address
        box["msg"] = srv.receive_message(conn)
        srv.send_message(conn, b"OK")
        srv.close_client(conn)

    thread = threading.Thread(target=server_side)
    thread.start()
    client = socket.create_connection(("127.0.0.1", port), timeout=5)
    srv.send_message(client, b"UPLOAD")
    reply = srv.receive_message(client)
    thread.join()
    client.close()
    listener.close()
    assert reply == b"OK", reply
    assert box["msg"] == b"UPLOAD", box["msg"]
    assert isinstance(box["address"], tuple) and len(box["address"]) == 2, box["address"]


def t_close_client_is_idempotent_safe():
    server, client = pair()
    srv.close_client(server)
    srv.close_client(server)  # closing twice must not raise


def t_close_client_none():
    srv.close_client(None)


print("Part 1 self-test")
check("header format 0000000005HELLO", t_header_format)
check("10-byte header for 123457-byte payload", t_header_padding_wide)
check("round trip 1/5/10/1024/65536/1MiB", t_roundtrip_sizes)
check("bytearray payload", t_bytearray_payload)
check("EOF before new message -> None", t_eof_before_message_is_none)
check("EOF in header -> ConnectionError", t_eof_partial_header_raises)
check("EOF in body -> ConnectionError", t_eof_partial_body_raises)
check("non-digit header -> ValueError", t_bad_header_nondigit)
check("zero length header -> ValueError", t_bad_header_zero_length)
check("oversized header -> ValueError", t_bad_header_too_long)
check("send_message rejects empty", t_send_rejects_empty)
check("send_message rejects > 5MiB", t_send_rejects_oversized)
check("send_message accepts exactly 5MiB", t_send_accepts_max_size)
check("listener/accept/close loopback", t_listener_accept_loopback)
check("close_client twice is safe", t_close_client_is_idempotent_safe)
check("close_client(None) is safe", t_close_client_none)

print("")
print("%d passed, %d failed" % (passed, len(failed)))
if failed:
    for name, error in failed:
        print("  - " + name + ": " + str(error))
    sys.exit(1)
