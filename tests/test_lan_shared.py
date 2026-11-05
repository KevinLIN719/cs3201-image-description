"""Part 5 checks: real AI backend, two clients sharing one store, LAN binding.

Run with:  .venv\\Scripts\\python.exe tests\\test_lan_shared.py
The real-backend case loads the SmolVLM model on the CPU and can take a minute.
"""
import socket
import sys

import client_harness as harness

MOCK_CAPTION = "Mock description: the image was received and decoded successfully."


def local_lan_address():
    """Return this machine's LAN IPv4 address (no packet is actually sent)."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 53))
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


def real_backend_gives_real_caption():
    def body(port, workdir):
        server = harness.start_server(port, workdir, backend="real",
                                      ready_timeout=300)
        try:
            code, text = harness.run_client(
                port,
                "UPLOAD\n./test_images/cat.jpg\nDESCRIBE\n0000\nLIST\n"
                "DESCRIBE\n9999\nQUIT\n",
                workdir, timeout=300)
        finally:
            harness.stop_server(server)
        lines = harness.lines_of(text)
        harness.assert_prefixed(text)
        assert "server: OK 0000" in lines, "upload failed:\n" + text
        assert any("DESCRIPTION: yes" in line for line in lines), \
            "the uploaded image should be marked as described:\n" + text
        assert "server: ERROR - Invalid ID" in lines, "error path broke:\n" + text
        captions = [line for line in lines
                    if line.startswith("server: ") and "OK" not in line
                    and "IMAGE ID" not in line and "ERROR" not in line]
        assert captions, "no caption line was printed:\n" + text
        caption = captions[0][len("server: "):]
        assert caption != MOCK_CAPTION, "the mock caption leaked into real mode"
        assert len(caption) > 10, "caption looks empty: " + repr(caption)
        print("    caption: " + caption)
    return body


def two_clients_share_storage():
    def body(port, workdir):
        server = harness.start_server(port, workdir)
        try:
            _, first = harness.run_client(
                port, "UPLOAD\n./test_images/cat.jpg\nQUIT\n", workdir)
            assert "server: OK 0000" in harness.lines_of(first), first

            _, second = harness.run_client(
                port,
                "LIST\nDESCRIBE\n0000\nREMOVE\n0000\nLIST\nQUIT\n", workdir)

            # A brand-new connection must see the same, now empty, store.
            _, third = harness.run_client(port, "LIST\nQUIT\n", workdir)
        finally:
            harness.stop_server(server)
        lines = harness.lines_of(second)
        harness.assert_prefixed(second)
        assert any("IMAGE ID: 0000 | FILE: cat.jpg" in line for line in lines), \
            "the second client cannot see the first client's image:\n" + second
        assert "server: " + MOCK_CAPTION in lines, \
            "the second client could not describe the image:\n" + second
        assert lines.count("server: OK") >= 3, second
        assert "server: No images" in lines, \
            "the removal should be visible to the second client:\n" + second
        assert "server: No images" in harness.lines_of(third), third
    return body


def server_listens_on_all_interfaces():
    address = local_lan_address()
    if address is None or address.startswith("127."):
        raise AssertionError("no LAN IPv4 address on this machine")

    def body(port, workdir):
        server = harness.start_server(port, workdir, host="0.0.0.0")
        try:
            _, text = harness.run_client(
                port, "UPLOAD\n./test_images/cat.jpg\nLIST\nQUIT\n", workdir,
                host=address)
        finally:
            harness.stop_server(server)
        lines = harness.lines_of(text)
        assert "server: OK 0000" in lines, \
            "client could not reach the server through %s:\n%s" % (address, text)
        assert any("IMAGE ID: 0000" in line for line in lines), text
        print("    connected through LAN address " + address)
    return body


def main():
    print("Part 5 checks")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    tests = [
        ("real AI backend describes an image",
         lambda: harness.with_workdir(real_backend_gives_real_caption())),
        ("two clients share one image store",
         lambda: harness.with_workdir(two_clients_share_storage())),
        ("server answers on the LAN address",
         lambda: harness.with_workdir(server_listens_on_all_interfaces())),
    ]
    return harness.report(tests)


if __name__ == "__main__":
    sys.exit(main())
