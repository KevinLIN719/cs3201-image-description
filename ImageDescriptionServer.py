"""Student server template: Online Image Description System.

Complete the five functions marked # TODO in Part 1.
recv_exact is an optional provided helper; do not modify it.
Read Part 2 to understand the server's communication flow.
Do not modify the provided code in Parts 2, 3, or 4.
You do not need to read the AI code in Part 4.
"""
import socket

HEADER_SIZE = 10
MAX_MESSAGE_BYTES = 5 * 1024 * 1024


# ===== PART 1: FIVE STUDENT SOCKET FUNCTIONS AND ONE PROVIDED HELPER =====
# TODO: Complete create_listener.
def create_listener(host, port):
    """Create and return an IPv4 TCP listening Socket."""
    raise NotImplementedError("TODO: create_listener")


# TODO: Complete accept_client.
def accept_client(listener):
    """Accept a client connection.

    Returns (conn, address): conn is the connected Socket; address is (IP, port).
    """
    raise NotImplementedError("TODO: accept_client")


# OPTIONAL PROVIDED HELPER - USE IF NEEDED, DO NOT MODIFY.
# You may use recv_exact(conn, count) when you need exactly count bytes.
# Return the data when all count bytes have arrived.
# Return None if the peer closes the connection before this call receives any bytes.
# Raise ConnectionError if it closes after some bytes arrive, but before count bytes.
def recv_exact(conn, count):
    """Read exactly count bytes, or report that the connection closed."""
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


# TODO: Complete receive_message.
def receive_message(conn):
    """Receive one complete message.

    Message format: 10 ASCII length digits (with leading zeros) + data.
    The length counts data bytes only and must be 1..MAX_MESSAGE_BYTES.
    Returns the data as bytes, without the length header, or None if the peer
    closes before any bytes of a new message arrive.
    Example: b"0000000005HELLO" returns b"HELLO".
    """
    raise NotImplementedError("TODO: receive_message")


# TODO: Complete send_message.
def send_message(conn, payload):
    """Send the supplied bytes as one complete message.

    Message format: 10 ASCII length digits (with leading zeros) + data.
    The length counts data bytes only (1..MAX_MESSAGE_BYTES), excluding the header.
    Returns None on successful completion.
    """
    raise NotImplementedError("TODO: send_message")


# TODO: Complete close_client.
def close_client(conn):
    """Close the connected Socket. Returns None."""
    raise NotImplementedError("TODO: close_client")


# ===== PART 2: PROVIDED SOCKET FLOW - READ, DO NOT MODIFY =====
import threading


def handle_client(conn, store, store_lock, caption_image):
    """Receive requests and send responses until QUIT or the connection closes."""
    try:
        while True:
            # Read every message of the request before processing its contents.
            try:
                message = receive_message(conn)
                if message is None:
                    break
                if len(message) > 1024:
                    raise ValueError("Command is too long")
                # Accept extra whitespace and mixed-case commands; keep spaces inside filenames.
                parts = message.decode("utf-8").strip().split(maxsplit=1)
                command = parts[0].upper() if parts else ""
                argument = parts[1].strip() if len(parts) > 1 else ""
                data = None
                if command == "UPLOAD":
                    data = receive_message(conn)
                    if data is None:
                        raise ConnectionError("Missing image message")
            except ValueError as error:
                # Invalid message data ends this connection after an error reply.
                send_message(conn, ("ERROR - " + str(error)).encode("utf-8"))
                break

            # Provided synchronization: one complete command runs at a time.
            with store_lock:
                if store["stopping"]:
                    break
                reply, download = process_command(command, argument, data,
                                                  store, caption_image)
            send_message(conn, reply.encode("utf-8"))
            if download is not None:
                send_message(conn, download)
            if command == "QUIT" and reply == "OK":
                break
    except NotImplementedError as error:
        print(error, "- complete this function in Part 1.", flush=True)
    except (OSError, ConnectionError):
        pass
    except Exception as error:
        print("Client handler error:", error, flush=True)
    finally:
        try:
            close_client(conn)
        except Exception as error:
            print("close_client failed:", error, "- closing the connection.", flush=True)
            conn.close()


def run_server(host, port, caption_image, io_timeout=300):
    """Accept clients; the small worker-thread setup is supplied."""
    listener = create_listener(host, port)
    listener.settimeout(0.5)
    store = {"images": {}, "next_id": 0, "stopping": False}
    store_lock = threading.Lock()
    clients = []
    workers = []
    print(f"READY host={host} port={listener.getsockname()[1]}", flush=True)
    try:
        while True:
            try:
                conn, address = accept_client(listener)
            except socket.timeout:
                continue
            conn.settimeout(io_timeout)
            worker = threading.Thread(target=handle_client,
                                      args=(conn, store, store_lock, caption_image))
            clients.append(conn)
            workers.append(worker)
            worker.start()
    finally:
        store["stopping"] = True
        listener.close()
        for conn in clients:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        for worker in workers:
            worker.join()


# ===== PART 3: PROVIDED COMMAND HANDLING AND SERVER STARTUP =====
# This part is complete. Students do not need to modify it.
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

MAX_IMAGES = 20
MAX_STORED_BYTES = 50 * 1024 * 1024


def process_command(command, argument, data, store, caption_image):
    """Return (text reply, optional download bytes) for a complete request."""
    images = store["images"]
    if command == "UPLOAD":
        if (not argument or len(argument) > 255 or argument in {".", ".."}
                or any(char in argument for char in "/\\\r\n\x00")):
            return "ERROR - Invalid filename", None
        try:
            prepare_image(data).close()
        except ValueError as error:
            return "ERROR - " + str(error), None
        total = sum(len(record["data"]) for record in images.values())
        if len(images) >= MAX_IMAGES or total + len(data) > MAX_STORED_BYTES:
            return "ERROR - Image storage is full", None
        image_id = f"{store['next_id']:04d}"
        store["next_id"] += 1
        images[image_id] = {"filename": argument, "data": data, "caption": None,
                            "uploaded": datetime.now(timezone(timedelta(hours=8))).strftime("%H:%M:%S")}
        return "OK " + image_id, None
    if command == "LIST" and not argument:
        lines = ["OK"]
        for image_id, record in images.items():
            state = "yes" if record["caption"] is not None else "no"
            lines.append(f"IMAGE ID: {image_id} | FILE: {record['filename']} | "
                         f"TIME: {record['uploaded']} | DESCRIPTION: {state}")
        if not images:
            lines.append("No images")
        return "\n".join(lines), None
    if command in ("DESCRIBE", "DOWNLOAD", "REMOVE"):
        if argument not in images:
            return "ERROR - Invalid ID", None
        record = images[argument]
        if command == "DOWNLOAD":
            return "OK " + record["filename"], record["data"]
        if command == "REMOVE":
            del images[argument]
            return "OK", None
        if record["caption"] is None:
            try:
                record["caption"] = caption_image(record["data"])
            except Exception:
                return "ERROR - AI inference failed", None
        return "OK\n" + record["caption"], None
    if command == "QUIT" and not argument:
        return "OK", None
    return "ERROR - Command not understood", None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0",
                        help="IPv4 listening address (default: all interfaces)")
    parser.add_argument("--port", type=int, default=18333)
    parser.add_argument("--backend", choices=("real", "mock"), default="real")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--io-timeout", type=float, default=300)
    parser.add_argument("--model-dir", type=Path, default=Path(__file__).resolve().parent / "models" / "smolvlm-256m")
    parser.add_argument("--download-model", action="store_true",
                        help="Force-download the pinned course model and repair its local files")
    parser.add_argument("--check-ai", type=Path, metavar="IMAGE")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535 or not 1 <= args.threads <= 16 or args.io_timeout <= 0:
        parser.error("Invalid port, thread count or timeout")
    try:
        if args.download_model:
            download_model(args.model_dir)
        else:
            caption_image = load_captioner(args.model_dir, backend=args.backend, threads=args.threads)
            if args.check_ai:
                print(caption_image(args.check_ai.read_bytes()))
            else:
                run_server(args.host, args.port, caption_image, args.io_timeout)
    except KeyboardInterrupt:
        print("Server stopped")
    except NotImplementedError as error:
        parser.exit(2, f"{error}\nComplete the five Socket TODOs in ImageDescriptionServer.py.\n")
    except (OSError, RuntimeError, ValueError, ImportError) as error:
        parser.exit(2, f"Server error: {error}\n")


# ===== PART 4: PROVIDED LOCAL AI - NO STUDENT READING OR EDITING REQUIRED =====
# Students: you do not need to read or modify anything in this section.
# Image preparation, model loading, inference, and downloading are supplied.
import io
import hashlib
import os
import shutil
import tempfile
import warnings

MAX_PIXELS = 20_000_000
IMAGE_EDGE = 512
MODEL_REPO = "HuggingFaceTB/SmolVLM-256M-Instruct"
MODEL_REVISION = "7e3e67edbbed1bf9888184d9df282b700a323964"
MODEL_FILES = {
    "README.md": "0b687c656b2587d84cb85003825746f8b3a08497dff4ed51b54b1090719fa512",
    "added_tokens.json": "74135b8664b56088c0006f1c8e848d79a8eba003411f72ebf1dc2ee96227be3a",
    "chat_template.json": "a68ad1a42681ae44eacd109ff8dd56a840f761c03d72f4ff4c515d092f882168",
    "config.json": "b70fb4bfde88df9eeebc9d8ff523733b8bf70d6c9b06c610325960e06ae9db52",
    "generation_config.json": "067a2a54e5f87162ecac6e0e911cc4665fc8f7f3324794ecbac0f76badb56636",
    "merges.txt": "0b54e8aa4e53d5383e2e4bc635a56b43f9647f7b13832d5d9ecd8f82dac4f510",
    "model.safetensors": "74dea5904032e5ae99a2e0eef5179e6ac0f1dedc3ab0c7c2a5d4d387c843203e",
    "preprocessor_config.json": "6cb6e36d6fcb88ca1502c4a26750715dc3e7dedddc9a8f17b27d8d167d1457e7",
    "processor_config.json": "e7bff42da73ae9eec9042ef20e066e11f1ee20f025358ff79131e3c0fb549b46",
    "special_tokens_map.json": "aa0ff906077086dfa9734a7f97f68c825877a48f9468807be65504495cdeef09",
    "tokenizer.json": "5ece781dc8d2b2f3e2f289ca0ae50b17cfc27dd27bfe7971bb8241e0b964331a",
    "tokenizer_config.json": "36c6fd44d07d10fd8180ee6b46dcccf69fb7c06753968ff0d7e17b8bfe17b777",
    "vocab.json": "82b84012e3add4d01d12ba14442026e49b8cbbaead1f79ecf3d919784f82dc79"
}
PROMPT = "Describe the main objects and the setting in this image in two short sentences."
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def prepare_image(data):
    from PIL import Image, ImageOps
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as original:
                if original.format not in {"JPEG", "PNG"}:
                    raise ValueError("Only JPEG and PNG are supported")
                if original.width * original.height > MAX_PIXELS:
                    raise ValueError("Image exceeds 20 million pixels")
                image = ImageOps.exif_transpose(original).convert("RGBA")
                background = Image.new("RGBA", image.size, "white")
                background.alpha_composite(image)
                image = background.convert("RGB")
                image.thumbnail((IMAGE_EDGE, IMAGE_EDGE), Image.Resampling.LANCZOS)
                canvas = Image.new("RGB", (IMAGE_EDGE, IMAGE_EDGE), "white")
                canvas.paste(image, ((IMAGE_EDGE - image.width) // 2,
                                    (IMAGE_EDGE - image.height) // 2))
                return canvas
    except ValueError:
        raise
    except (OSError, SyntaxError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise ValueError("Invalid image")


def load_captioner(model_dir, backend="real", threads=2):
    """Return a supplied function that describes one image using CPU FP32."""
    if backend == "real":
        import torch
        from transformers import AutoProcessor, AutoModelForVision2Seq
        directory = Path(model_dir).resolve()
        if not (directory / "model.safetensors").is_file():
            raise FileNotFoundError("Bundled model not found. Extract the complete assignment ZIP "
                                    "or run ImageDescriptionServer.py --download-model to repair it")
        torch.set_num_threads(threads)
        torch.manual_seed(0)
        processor = AutoProcessor.from_pretrained(directory, local_files_only=True,
                    trust_remote_code=False, size={"longest_edge": IMAGE_EDGE})
        model = AutoModelForVision2Seq.from_pretrained(directory, local_files_only=True,
                trust_remote_code=False, use_safetensors=True, torch_dtype=torch.float32,
                attn_implementation="eager").to("cpu").eval()

    def caption_image(data):
        image = prepare_image(data)
        try:
            if backend == "mock":
                return "Mock description: the image was received and decoded successfully."
            messages = [{"role": "user", "content": [
                {"type": "image"}, {"type": "text", "text": PROMPT}]}]
            prompt = processor.apply_chat_template(messages, add_generation_prompt=True)
            inputs = processor(text=prompt, images=[image], return_tensors="pt")
            with torch.inference_mode():
                output = model.generate(**inputs, do_sample=False, num_beams=1, max_new_tokens=80)
            caption = processor.decode(output[0, inputs["input_ids"].shape[1]:],
                                       skip_special_tokens=True).strip()
            if not caption:
                raise RuntimeError("AI returned an empty description")
            return caption
        finally:
            image.close()
    return caption_image


def download_model(directory):
    """Force-download, verify, and replace the pinned local model files."""
    from huggingface_hub import snapshot_download
    directory = Path(directory).resolve()
    if directory.exists() and not directory.is_dir():
        raise ValueError("The model path must be a directory")
    directory.parent.mkdir(parents=True, exist_ok=True)
    print("Repairing model: downloading the pinned course version", flush=True)
    with tempfile.TemporaryDirectory(prefix=".model-repair-", dir=directory.parent) as temporary:
        prepared = Path(temporary) / "download"
        snapshot_download(MODEL_REPO, revision=MODEL_REVISION, local_dir=prepared,
                          allow_patterns=list(MODEL_FILES), force_download=True)
        for name, expected in MODEL_FILES.items():
            digest = hashlib.sha256()
            with (prepared / name).open("rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != expected:
                raise ValueError("Model verification failed: " + name)
        (prepared / "README.md").rename(prepared / "MODEL_CARD.md")
        shutil.rmtree(prepared / ".cache", ignore_errors=True)
        for name in ("LICENSE.txt", "ATTRIBUTION.txt", "course_manifest.json"):
            if (directory / name).is_file():
                shutil.copy2(directory / name, prepared / name)
        backup = directory.parent / ("." + directory.name + "-backup-" + Path(temporary).name)
        had_model = directory.exists()
        if had_model:
            directory.rename(backup)
        try:
            prepared.rename(directory)
        except OSError:
            if had_model:
                backup.rename(directory)
            raise
        if had_model:
            shutil.rmtree(backup, ignore_errors=True)
    print("Model repaired:", directory)


if __name__ == "__main__":
    main()
