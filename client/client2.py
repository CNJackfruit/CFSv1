import argparse
import hashlib
import json
import os
import socket
import ssl
import sys
import time
from utils import ProtocolReader

BUFFER_SIZE = 65536  # 64 KB chunk size for transfer


# =====================================================================
# CORE FUNCTIONS (No prints, no sys.exit; return values or raise exceptions)
# =====================================================================

def connect(host, port):
    """Establishes a secure connection with a 5-second timeout."""
    try:
        raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_socket.settimeout(5.0)  # 5s timeout to catch dropped packets
        raw_socket.connect((host, port))

        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        return context.wrap_socket(raw_socket)
    except socket.timeout:
        raise RuntimeError("connection timed out (blocked by network policy?)")
    except Exception as e:
        raise RuntimeError(f"connection failed: {e}")


def login(sock, user, password, reader=None):
    """Authenticates against the server."""
    if reader is None:
        reader = ProtocolReader(sock)

    request = {"cmd": "LOGIN", "username": user, "password": password}
    sock.sendall((json.dumps(request) + "\n").encode("utf-8"))

    response_bytes = reader.recv_line()
    if not response_bytes:
        raise ConnectionError("Server disconnected during login.")

    response = json.loads(response_bytes.decode("utf-8").strip())
    if response.get("status") != "OK":
        raise PermissionError(response.get("msg", "Invalid credentials"))
    return True


def list_files(sock, reader=None):
    """Requests and returns the files metadata dictionary from the server."""
    if reader is None:
        reader = ProtocolReader(sock)

    command = {"cmd": "LIST"}
    sock.sendall((json.dumps(command) + "\n").encode("utf-8"))

    response_bytes = reader.recv_line()
    if not response_bytes:
        raise ConnectionError("Server disconnected during file listing.")

    response = json.loads(response_bytes.decode("utf-8").strip())
    if response.get("status") == "ERROR":
        raise RuntimeError(response.get("msg", "Failed to retrieve list"))

    return response.get("files", {})


def upload(sock, path, reader=None):
    """Uploads a file in 64 KB chunks and measures pure transfer time."""
    if reader is None:
        reader = ProtocolReader(sock)

    if not os.path.exists(path):
        raise FileNotFoundError(f"File '{path}' does not exist.")

    file_size = os.path.getsize(path)
    filename = os.path.basename(path)

    # 1. Compute SHA-256 BEFORE starting the transfer timer
    sha256_hash = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(BUFFER_SIZE):
            sha256_hash.update(chunk)
    expected_sha256 = sha256_hash.hexdigest()

    header_dict = {
        "cmd": "UPLOAD",
        "name": filename,
        "size": file_size,
        "sha256": expected_sha256
    }
    header_bytes = (json.dumps(header_dict) + "\n").encode("utf-8")

    # 2. START TIMING WINDOW
    start_time = time.perf_counter()

    sock.sendall(header_bytes)

    # Stream file in 64 KB chunks
    with open(path, "rb") as f:
        while chunk := f.read(BUFFER_SIZE):
            sock.sendall(chunk)

    # Read final server acknowledgment
    response_bytes = reader.recv_line()
    
    # 3. END TIMING WINDOW
    elapsed_time = time.perf_counter() - start_time

    if not response_bytes:
        raise ConnectionError("Server disconnected during upload.")

    try:
        resp_text = response_bytes.decode("utf-8").strip()
        if resp_text.startswith("{"):
            resp = json.loads(resp_text)
            if resp.get("status") == "ERROR":
                raise RuntimeError(resp.get("msg", "Upload failed"))
    except json.JSONDecodeError:
        pass

    return filename, file_size, elapsed_time


def download(sock, name, dest_folder, reader=None):
    """Downloads a file to a temp file, verifies hash, and renames on success."""
    if reader is None:
        reader = ProtocolReader(sock)

    os.makedirs(dest_folder, exist_ok=True)
    temp_path = os.path.join(dest_folder, f"{name}.tmp")
    final_path = os.path.join(dest_folder, name)

    command = {"cmd": "DOWNLOAD", "name": name}

    # 1. START TIMING WINDOW
    start_time = time.perf_counter()

    sock.sendall((json.dumps(command) + "\n").encode("utf-8"))

    response_bytes = reader.recv_line()
    if not response_bytes:
        raise ConnectionError("Server disconnected during download.")

    response = json.loads(response_bytes.decode("utf-8").strip())
    if response.get("status") == "ERROR":
        raise RuntimeError(response.get("msg", "Download failed"))

    file_size = response.get("size")
    expected_sha256 = response.get("sha256")

    # Stream exact bytes into temp file
    sha256_acc = hashlib.sha256()
    with open(temp_path, "wb") as f:
        file_data = reader.recv_exact(file_size)
        f.write(file_data)
        sha256_acc.update(file_data)

    # 2. END TIMING WINDOW
    elapsed_time = time.perf_counter() - start_time

    # Verify integrity
    if sha256_acc.hexdigest() != expected_sha256:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise ValueError("SHA-256 hash mismatch! File was corrupted during download.")

    # Atomic rename on success
    os.replace(temp_path, final_path)
    return name, file_size, elapsed_time


# =====================================================================
# CLI LOGGING & RUNNER (argparse)
# =====================================================================

def log_transfer(filename, bytes_count, seconds, op_type):
    """Calculates throughput (Mbps), prints summary, and writes to transfers.csv."""
    mbps = (bytes_count * 8) / (seconds * 1e6) if seconds > 0 else 0.0
    print(f"[{op_type.upper()}] {filename}, {bytes_count} bytes, {seconds:.4f} s, {mbps:.2f} Mbps")

    csv_exists = os.path.exists("transfers.csv")
    with open("transfers.csv", "a") as f:
        if not csv_exists:
            f.write("timestamp,operation,filename,bytes,seconds,mbps\n")
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')},{op_type},{filename},{bytes_count},{seconds:.4f},{mbps:.2f}\n")


def main():
    parser = argparse.ArgumentParser(description="Secure Client CLI")
    parser.add_argument("--host", required=True, help="Server IP address")
    parser.add_argument("--port", type=int, required=True, help="Server port number")
    parser.add_argument("--user", required=True, help="Username")
    parser.add_argument("--password", required=True, help="Password")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # List command
    subparsers.add_parser("list")

    # Upload command
    up_parser = subparsers.add_parser("upload")
    up_parser.add_argument("file", help="Path to local file to upload")

    # Download command
    down_parser = subparsers.add_parser("download")
    down_parser.add_argument("name", help="Name of file on server to download")
    down_parser.add_argument("--dest", default=".", help="Destination folder for saving file")

    args = parser.parse_args()

    # Wrap CLI execution to catch exceptions and print a 1-line error message (no tracebacks)
    try:
        sock = connect(args.host, args.port)
        reader = ProtocolReader(sock)

        login(sock, args.user, args.password, reader)

        if args.command == "list":
            files = list_files(sock, reader)
            print(f"\n{'FILENAME':<20} | {'OWNER':<10} | {'SIZE (bytes)':<15} | {'DOWNLOADS':<10}")
            print("-" * 85)
            for filename, details in files.items():
                owner = details.get("owner", "unknown")
                size = details.get("size", 0)
                downloads = details.get("downloads", 0)
                uploaded = details.get("uploaded", "unknown")
                print(f"{filename:<20} | {owner:<10} | {size:<15} | {downloads:<10} | {uploaded}")
            print("-" * 85)

        elif args.command == "upload":
            fname, bytes_cnt, duration = upload(sock, args.file, reader)
            log_transfer(fname, bytes_cnt, duration, "upload")

        elif args.command == "download":
            fname, bytes_cnt, duration = download(sock, args.name, args.dest, reader)
            log_transfer(fname, bytes_cnt, duration, "download")

        sock.close()
        sys.exit(0)

    except Exception as e:
        print(f"[-] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
