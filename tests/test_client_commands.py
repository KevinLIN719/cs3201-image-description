"""Self-test for the five data commands (板块 3 acceptance).

Run:
    .venv\\Scripts\\python.exe tests\\test_client_commands.py

Every test starts the real server in "--backend mock" mode, so the replies are
the ones the real server produces (including the mock description text) and
the transcript is checked line by line against the format in the assignment.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import client_harness as harness

MOCK_DESCRIPTION = ("server: Mock description: the image was received "
                    "and decoded successfully.")
IMAGE_LINE = re.compile(r"server: IMAGE ID: (\d{4}) \| FILE: (\S+) \| "
                        r"TIME: \d\d:\d\d:\d\d \| DESCRIPTION: (no|yes)")


def rel(path):
    """Path of a temp file relative to the repository (the client runs there)."""
    return Path(path).resolve().relative_to(harness.REPO).as_posix()


def t_upload_then_list():
    def body(port, workdir):
        code, text = harness.run_client(
            port, "UPLOAD\n./test_images/cat.jpg\nLIST\nQUIT\n", workdir)
        assert code == 0, "exit code %r, output=%r" % (code, text)
        out = harness.lines_of(text)
        assert out[:5] == ["client: UPLOAD",
                           "client: ./test_images/cat.jpg",
                           "server: OK 0000",
                           "client: LIST",
                           "server: OK"], "output was: %r" % (out,)
        match = IMAGE_LINE.fullmatch(out[5])
        assert match, "bad LIST line: %r" % (out[5],)
        assert match.groups() == ("0000", "cat.jpg", "no"), match.groups()
        assert out[6:] == ["client: QUIT", "server: OK"], "output was: %r" % (out,)
        harness.assert_prefixed(text)
    harness.with_server(body)


def t_two_uploads_get_increasing_ids():
    def body(port, workdir):
        code, text = harness.run_client(
            port, "UPLOAD\n./test_images/cat.jpg\nUPLOAD\n./test_images/flower.png\n"
                  "LIST\nQUIT\n", workdir)
        out = harness.lines_of(text)
        assert out[2] == "server: OK 0000", out
        assert out[5] == "server: OK 0001", out
        ids = [match.groups()[0] for match in map(IMAGE_LINE.fullmatch, out) if match]
        assert ids == ["0000", "0001"], "LIST lines were: %r" % (out,)
    harness.with_server(body)


def t_upload_local_errors_keep_the_session():
    def body(port, workdir):
        big = Path(workdir) / "big.jpg"
        big.write_bytes(b"\x00" * (5 * 1024 * 1024 + 1))
        code, text = harness.run_client(
            port,
            "UPLOAD\ntest_images/missing.jpg\n"
            "UPLOAD\n%s\n"
            "UPLOAD\ntest_images\n"
            "LIST\nQUIT\n" % rel(big), workdir)
        out = harness.lines_of(text)
        assert out == ["client: UPLOAD",
                       "client: test_images/missing.jpg",
                       "client: ERROR - File not found",
                       "client: UPLOAD",
                       "client: " + rel(big),
                       "client: ERROR - File exceeds 5 MiB",
                       "client: UPLOAD",
                       "client: test_images",
                       "client: ERROR - File not found",
                       "client: LIST",
                       "server: OK",
                       "server: No images",
                       "client: QUIT",
                       "server: OK"], "output was: %r" % (out,)
        harness.assert_prefixed(text)
    harness.with_server(body)


def t_upload_invalid_image_gets_server_error():
    def body(port, workdir):
        bad = Path(workdir) / "notimage.jpg"
        bad.write_bytes(b"this is not an image")
        code, text = harness.run_client(
            port, "UPLOAD\n%s\nLIST\nQUIT\n" % rel(bad), workdir)
        out = harness.lines_of(text)
        assert out[2] == "server: ERROR - Invalid image", \
            "output was: %r" % (out,)
        assert out[3:] == ["client: LIST", "server: OK", "server: No images",
                           "client: QUIT", "server: OK"], out
    harness.with_server(body)


def t_describe_and_remove():
    def body(port, workdir):
        code, text = harness.run_client(
            port,
            "UPLOAD\n./test_images/cat.jpg\n"
            "DESCRIBE\n9999\n"
            "DESCRIBE\n0000\n"
            "REMOVE\n9999\n"
            "REMOVE\n0000\n"
            "LIST\nQUIT\n", workdir)
        out = harness.lines_of(text)
        assert out == ["client: UPLOAD",
                       "client: ./test_images/cat.jpg",
                       "server: OK 0000",
                       "client: DESCRIBE",
                       "client: 9999",
                       "server: ERROR - Invalid ID",
                       "client: DESCRIBE",
                       "client: 0000",
                       "server: OK",
                       MOCK_DESCRIPTION,
                       "client: REMOVE",
                       "client: 9999",
                       "server: ERROR - Invalid ID",
                       "client: REMOVE",
                       "client: 0000",
                       "server: OK",
                       "client: LIST",
                       "server: OK",
                       "server: No images",
                       "client: QUIT",
                       "server: OK"], "output was: %r" % (out,)
        harness.assert_prefixed(text)
    harness.with_server(body)


def t_blank_arguments_are_rejected_locally():
    def body(port, workdir):
        code, text = harness.run_client(
            port, "DESCRIBE\n\nDOWNLOAD\n\nREMOVE\n\nLIST\nQUIT\n", workdir)
        out = harness.lines_of(text)
        assert out.count("client: ERROR - Missing image ID") == 3, \
            "output was: %r" % (out,)
        assert out[-5:] == ["client: LIST", "server: OK", "server: No images",
                            "client: QUIT", "server: OK"], out
    harness.with_server(body)


def t_download_round_trip_and_no_overwrite():
    def body(port, workdir):
        missing = Path(workdir) / "missing.jpg"
        saved = Path(workdir) / "cat_download.jpg"
        code, text = harness.run_client(
            port,
            "UPLOAD\n./test_images/cat.jpg\n"
            "DOWNLOAD\n9999\n%s\n"
            "DESCRIBE\n0000\n"
            "DOWNLOAD\n0000\n%s\n"
            "DOWNLOAD\n0000\n%s\n"
            "LIST\nQUIT\n" % (rel(missing), rel(saved), rel(saved)), workdir)
        out = harness.lines_of(text)
        assert out[3:6] == ["client: DOWNLOAD", "client: 9999", "client: " + rel(missing)], \
            "output was: %r" % (out,)
        assert out[6] == "server: ERROR - Invalid ID", \
            "a failed DOWNLOAD must not print extra lines: %r" % (out,)
        assert not missing.exists(), "no file must be created for an invalid ID"

        # The connection stayed in sync: DESCRIBE still gets its own reply.
        assert out[7:10] == ["client: DESCRIBE", "client: 0000", "server: OK"], out
        assert out[10] == MOCK_DESCRIPTION, out

        assert out[14] == "server: OK cat.jpg", out
        assert out[15] == "client: Saved to " + rel(saved), out
        assert saved.read_bytes() == (harness.REPO / "test_images" / "cat.jpg").read_bytes(), \
            "downloaded bytes differ from the uploaded file"

        # The second DOWNLOAD to the same path is refused before sending.
        assert out[19] == "client: ERROR - File already exists: " + rel(saved), \
            "output was: %r" % (out,)
        assert out[20:22] == ["client: LIST", "server: OK"], out
        match = IMAGE_LINE.fullmatch(out[22])
        assert match and match.groups() == ("0000", "cat.jpg", "yes"), \
            "DESCRIPTION must be yes after DESCRIBE: %r" % (out[22],)
        assert out[23:] == ["client: QUIT", "server: OK"], out
    harness.with_server(body)


def t_download_existing_file_is_not_replaced():
    def body(port, workdir):
        target = Path(workdir) / "keep.png"
        target.write_bytes(b"keep me")
        code, text = harness.run_client(
            port, "DOWNLOAD\n0000\n%s\nLIST\nQUIT\n" % rel(target), workdir)
        out = harness.lines_of(text)
        # No "server:" line for the refused DOWNLOAD: nothing was sent.
        assert out[:3] == ["client: DOWNLOAD", "client: 0000",
                           "client: " + rel(target)], out
        assert out[3] == "client: ERROR - File already exists: " + rel(target), out
        assert target.read_bytes() == b"keep me", "the local file was overwritten"
        assert out[4:] == ["client: LIST", "server: OK", "server: No images",
                           "client: QUIT", "server: OK"], out
    harness.with_server(body)


def t_upload_check_units():
    client = harness.load_program("ImageDescriptionClient", "ImageDescriptionClient")

    cat = harness.REPO / "test_images" / "cat.jpg"
    data, filename = client.check_upload_file(cat)
    assert filename == "cat.jpg", filename
    assert data == cat.read_bytes(), "the whole file must be returned"

    try:
        client.check_upload_file(harness.REPO / "test_images" / "nope.jpg")
    except client.LocalError as error:
        assert str(error) == "File not found", str(error)
    else:
        raise AssertionError("a missing file must raise LocalError")

    old_limit = client.MAX_FILENAME_CHARS
    client.MAX_FILENAME_CHARS = 3
    try:
        try:
            client.check_upload_file(cat)
        except client.LocalError as error:
            assert str(error) == "Invalid filename", str(error)
        else:
            raise AssertionError("an over-long filename must raise LocalError")
    finally:
        client.MAX_FILENAME_CHARS = old_limit


def t_inline_arguments_are_accepted():
    def body(port, workdir):
        target = Path(workdir) / "flower_copy.png"
        code, text = harness.run_client(
            port,
            "UPLOAD ./test_images/flower.png\n"
            "DESCRIBE 0000\n"
            "DOWNLOAD 0000\n%s\n"
            "REMOVE 0000\n"
            "LIST\nQUIT\n" % rel(target), workdir)
        out = harness.lines_of(text)
        assert out == ["client: UPLOAD ./test_images/flower.png",
                       "server: OK 0000",
                       "client: DESCRIBE 0000",
                       "server: OK",
                       MOCK_DESCRIPTION,
                       "client: DOWNLOAD 0000",
                       "client: " + rel(target),
                       "server: OK flower.png",
                       "client: Saved to " + rel(target),
                       "client: REMOVE 0000",
                       "server: OK",
                       "client: LIST",
                       "server: OK",
                       "server: No images",
                       "client: QUIT",
                       "server: OK"], "output was: %r" % (out,)
        assert target.read_bytes() == \
            (harness.REPO / "test_images" / "flower.png").read_bytes(), \
            "downloaded bytes differ from the uploaded file"
    harness.with_server(body)


def main():
    print("Client command self-test")
    return harness.report([
        ("UPLOAD then LIST", t_upload_then_list),
        ("two uploads get IDs 0000 and 0001", t_two_uploads_get_increasing_ids),
        ("local UPLOAD errors keep the session alive", t_upload_local_errors_keep_the_session),
        ("invalid image gets the server error", t_upload_invalid_image_gets_server_error),
        ("DESCRIBE and REMOVE", t_describe_and_remove),
        ("blank arguments are rejected locally", t_blank_arguments_are_rejected_locally),
        ("DOWNLOAD round trip and no overwrite", t_download_round_trip_and_no_overwrite),
        ("existing local file is not replaced", t_download_existing_file_is_not_replaced),
        ("arguments on the command line are accepted", t_inline_arguments_are_accepted),
        ("check_upload_file units", t_upload_check_units),
    ])


if __name__ == "__main__":
    sys.exit(main())
