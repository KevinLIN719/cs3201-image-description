"""Error handling matrix (板块 4 acceptance).

Eight error cases, each driven through the real client against a real server in
"--backend mock" mode.  Every case checks the exact reply AND that the SAME
connection is still usable afterwards (that is the point being graded: an error
must not desynchronise or close the connection).

Run every case and write the screenshots:
    .venv\\Scripts\\python.exe tests\\error_matrix.py
Run one case only (for a hand-made screenshot):
    .venv\\Scripts\\python.exe tests\\error_matrix.py --case 3

For each case the script writes
    shots/err-0N.txt   the captured client transcript
    shots/err-0N.png   the same transcript rendered like a terminal window
so the report can embed the picture and the text is still searchable.
"""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import client_harness as harness
from PIL import Image, ImageDraw, ImageFont

SHOTS = harness.REPO / "shots"
FONT_DIR = Path("C:/Windows/Fonts")

BACKGROUND = (30, 30, 30)
BAR = (46, 46, 46)
BODY = (212, 212, 212)
CLIENT = (86, 182, 255)
SERVER = (126, 198, 138)
ERROR = (240, 150, 90)
TITLE = (255, 255, 255)


def load_font(size, bold=False):
    names = ["consolab.ttf", "consola.ttf"] if bold else ["consola.ttf"]
    for name in names:
        path = FONT_DIR / name
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def line_color(line):
    if "ERROR -" in line:
        return ERROR
    if line.startswith("server:"):
        return SERVER
    if line.startswith("---"):
        return BODY
    return CLIENT


def render_png(title, lines, out_path):
    """Draw the transcript like a terminal window screenshot."""
    body_font = load_font(15)
    title_font = load_font(15, bold=True)
    line_height = 22
    padding = 16
    header = 34

    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    widest = max([measure.textlength(title, font=title_font)]
                 + [measure.textlength(line, font=body_font) for line in lines])
    width = max(760, int(widest) + 2 * padding)
    height = header + padding * 2 + line_height * max(1, len(lines))

    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width, header], fill=BAR)
    for index, dot in enumerate((ERROR, SERVER, CLIENT)):
        draw.ellipse([12 + index * 18, 12, 20 + index * 18, 20], fill=dot)
    draw.text((padding + 60, 9), title, font=title_font, fill=TITLE)

    y = header + padding
    for line in lines:
        draw.text((padding, y), line, font=body_font, fill=line_color(line))
        y += line_height
    image.save(out_path)


def expect(lines, expected):
    """Assert the exact line list, showing the whole transcript when it fails."""
    assert lines == expected, "expected %r but got %r" % (expected, lines)


def case01_unknown_command():
    def body(port, workdir):
        code, text = harness.run_client(port, "UNKNOWN\nLIST\nQUIT\n", workdir)
        assert code == 0, "exit code %r" % (code,)
        out = harness.lines_of(text)
        expect(out, ["client: UNKNOWN",
                     "server: ERROR - Command not understood",
                     "client: LIST",
                     "server: OK",
                     "server: No images",
                     "client: QUIT",
                     "server: OK"])
        return [text]
    return body


def case02_missing_file():
    def body(port, workdir):
        code, text = harness.run_client(
            port, "UPLOAD\ntest_images/no_such_file.jpg\nLIST\nQUIT\n", workdir)
        out = harness.lines_of(text)
        expect(out, ["client: UPLOAD",
                     "client: test_images/no_such_file.jpg",
                     "client: ERROR - File not found",
                     "client: LIST",
                     "server: OK",
                     "server: No images",
                     "client: QUIT",
                     "server: OK"])
        return [text]
    return body


def case03_fake_image():
    def body(port, workdir):
        # Use a short path in the repository root so the screenshot stays readable.
        fake = harness.REPO / "fake_image.png"
        if fake.exists():
            fake = Path(workdir) / "fake_image.png"
            rel = fake.resolve().relative_to(harness.REPO).as_posix()
        else:
            rel = "./fake_image.png"
        fake.write_bytes(b"this is a text file renamed to .png\n")
        try:
            code, text = harness.run_client(
                port, "UPLOAD\n%s\nLIST\nQUIT\n" % rel, workdir)
        finally:
            fake.unlink()
        out = harness.lines_of(text)
        expect(out, ["client: UPLOAD",
                     "client: " + rel,
                     "server: ERROR - Invalid image",
                     "client: LIST",
                     "server: OK",
                     "server: No images",
                     "client: QUIT",
                     "server: OK"])
        return [text]
    return body


def case04_invalid_id_describe():
    def body(port, workdir):
        code, text = harness.run_client(
            port, "DESCRIBE\n9999\nLIST\nQUIT\n", workdir)
        out = harness.lines_of(text)
        expect(out, ["client: DESCRIBE",
                     "client: 9999",
                     "server: ERROR - Invalid ID",
                     "client: LIST",
                     "server: OK",
                     "server: No images",
                     "client: QUIT",
                     "server: OK"])
        return [text]
    return body


def case05_invalid_id_download():
    def body(port, workdir):
        # A short repository-relative path keeps the screenshot readable.
        target = harness.REPO / "downloaded_9999.jpg"
        if target.exists():
            target = Path(workdir) / "downloaded_9999.jpg"
            rel = target.resolve().relative_to(harness.REPO).as_posix()
        else:
            rel = "./downloaded_9999.jpg"
        code, text = harness.run_client(
            port, "DOWNLOAD\n9999\n%s\nLIST\nQUIT\n" % rel, workdir)
        out = harness.lines_of(text)
        expect(out, ["client: DOWNLOAD",
                     "client: 9999",
                     "client: " + rel,
                     "server: ERROR - Invalid ID",
                     "client: LIST",
                     "server: OK",
                     "server: No images",
                     "client: QUIT",
                     "server: OK"])
        assert not target.exists(), "a failed DOWNLOAD must not create a file"
        return [text]
    return body


def case06_invalid_id_remove():
    def body(port, workdir):
        code, text = harness.run_client(
            port, "REMOVE\n9999\nLIST\nQUIT\n", workdir)
        out = harness.lines_of(text)
        expect(out, ["client: REMOVE",
                     "client: 9999",
                     "server: ERROR - Invalid ID",
                     "client: LIST",
                     "server: OK",
                     "server: No images",
                     "client: QUIT",
                     "server: OK"])
        return [text]
    return body


def case07_quit_does_not_disturb_other_clients():
    def body(port, workdir):
        code, first = harness.run_client(
            port, "UPLOAD\n./test_images/cat.jpg\nQUIT\n", workdir)
        first_out = harness.lines_of(first)
        expect(first_out, ["client: UPLOAD",
                           "client: ./test_images/cat.jpg",
                           "server: OK 0000",
                           "client: QUIT",
                           "server: OK"])
        assert code == 0

        # A brand new client sees the image the first client uploaded, so the
        # QUIT of one client neither killed the server nor lost its state.
        code, second = harness.run_client(
            port, "LIST\nDESCRIBE\n0000\nQUIT\n", workdir)
        second_out = harness.lines_of(second)
        assert second_out[0:2] == ["client: LIST", "server: OK"], second_out
        assert second_out[2].startswith("server: IMAGE ID: 0000 | FILE: cat.jpg"), second_out
        assert second_out[2].endswith("| DESCRIPTION: no"), second_out
        assert second_out[3:9] == ["client: DESCRIBE", "client: 0000", "server: OK",
                                   "server: Mock description: the image was received "
                                   "and decoded successfully.",
                                   "client: QUIT", "server: OK"], second_out
        return [first, second]
    return body


def case08_storage_full():
    def body(port, workdir):
        commands = "UPLOAD\n./test_images/cat.jpg\n" * 21 + "LIST\nQUIT\n"
        code, text = harness.run_client(port, commands, workdir, timeout=180)
        out = harness.lines_of(text)
        replies = [out[index * 3 + 2] for index in range(21)]
        assert replies[:20] == ["server: OK %04d" % index for index in range(20)], \
            "the first 20 uploads must succeed: %r" % (replies,)
        assert replies[20] == "server: ERROR - Image storage is full", \
            "the 21st upload must be refused: %r" % (replies[20],)
        # The connection survives the refusal: LIST still answers with 20 images.
        assert out[63] == "client: LIST" and out[64] == "server: OK", out[60:]
        assert len([line for line in out if line.startswith("server: IMAGE ID:")]) == 20
        assert out[-2:] == ["client: QUIT", "server: OK"], out[-2:]
        return [text]
    return body


CASES = [
    (1, "CASE 1  unknown command", case01_unknown_command()),
    (2, "CASE 2  UPLOAD with a missing file", case02_missing_file()),
    (3, "CASE 3  UPLOAD with a fake image", case03_fake_image()),
    (4, "CASE 4  DESCRIBE with an invalid ID", case04_invalid_id_describe()),
    (5, "CASE 5  DOWNLOAD with an invalid ID", case05_invalid_id_download()),
    (6, "CASE 6  REMOVE with an invalid ID", case06_invalid_id_remove()),
    (7, "CASE 7  QUIT does not disturb other clients",
     case07_quit_does_not_disturb_other_clients()),
    (8, "CASE 8  storage full after 20 images", case08_storage_full()),
]


def run_case(number, title, body):
    """Run one case against a fresh mock server and save its screenshot."""
    workdir = harness.make_workdir()
    port = harness.free_port()
    server = harness.start_server(port, workdir)
    try:
        transcripts = body(port, workdir)
    finally:
        harness.stop_server(server)
        shutil.rmtree(workdir, ignore_errors=True)

    lines = []
    for index, transcript in enumerate(transcripts):
        if index:
            lines.append("--- a new client connects to the same server ---")
        lines.extend(harness.lines_of(transcript))
    text = "\n".join(lines) + "\n"
    (SHOTS / ("err-%02d.txt" % number)).write_text(text, encoding="utf-8")
    render_png(title, lines, SHOTS / ("err-%02d.png" % number))
    print("  PASS  " + title)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=int, default=0,
                        help="run only this case number (default: all)")
    args = parser.parse_args()

    SHOTS.mkdir(exist_ok=True)
    selected = [case for case in CASES if args.case in (0, case[0])]
    if not selected:
        print("no such case: %d" % args.case)
        return 1

    print("Error handling matrix")
    failures = 0
    for number, title, body in selected:
        try:
            run_case(number, title, body)
        except AssertionError as error:
            failures += 1
            print("  FAIL  " + title + "  -> " + str(error))

    print("")
    print("%d case(s) passed, %d failed" % (len(selected) - failures, failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
