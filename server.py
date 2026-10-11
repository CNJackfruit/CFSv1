import hashlib
import json
import os
import socket
import ssl
import struct
import threading
import argparse



HOST = "0.0.0.0"

BUFFER_SIZE = 4096

def parse_args():
    parser = argparse.ArgumentParser(description="Modular TLS File Transfer Server")
    parser.add_argument(
        "--port", 
        type=int, 
        default=9000, 
        help="Port to listen on (default: 9000)"
    )
    parser.add_argument(
        "--storage", 
        type=str, 
        default="storage/", 
        help="Directory path for file storage (default: storage/)"
    )
    return parser.parse_args()

class ProtocolReader:
    def __init__(self, sock):
        self.sock = sock
        self.buffer = bytearray()

    def recv_line(self, max_bytes=4096):
        """Reads up to a newline, keeping leftover bytes in the buffer."""
        while b'\n' not in self.buffer:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("Connection closed unexpectedly.")
            self.buffer.extend(chunk)
            if len(self.buffer) > max_bytes:
                raise ValueError("Line exceeded maximum length.")

        idx = self.buffer.index(b'\n') + 1
        line = bytes(self.buffer[:idx])
        del self.buffer[:idx]  # Safely remove the line, leaving the rest!
        return line

    def recv_exact(self, n):
        """Reads exactly n bytes, pulling from the leftover buffer first."""
        while len(self.buffer) < n:
            chunk = self.sock.recv(max(4096, n - len(self.buffer)))
            if not chunk:
                raise ConnectionError("Connection closed before exact bytes arrived.")
            self.buffer.extend(chunk)

        data = bytes(self.buffer[:n])
        del self.buffer[:n]  # Remove the consumed body bytes
        return data

def handle_upload(reader, conn, client_id, header_data,STORAGE_DIR):

    """Handles the file upload logic."""
    filename = header_data.get("name")
    file_size = header_data.get("size")
    expected_sha256 = header_data.get("sha256")

    print(f"[*] [{client_id}] Upload request for: '{filename}' ({file_size} bytes)")
    print(f"[*] [{client_id}] Expected SHA256: {expected_sha256}")

    os.makedirs("database", exist_ok=True)
    
    # FIX: Use client_id (safely formatted) instead of missing 'addr'
    safe_client_id = client_id.replace(":", "_")
    save_filename = os.path.join("database", f"saved_{safe_client_id}_{os.path.basename(filename)}")
    
    sha256_acc = hashlib.sha256()
    received_bytes = 0

    try:
        with open(save_filename, "wb") as f:
            while received_bytes < file_size:
                chunk_limit = min(BUFFER_SIZE, file_size - received_bytes)
                chunk = reader.recv_exact(chunk_limit)

                if not chunk:
                    break

                f.write(chunk)
                sha256_acc.update(chunk)
                received_bytes += len(chunk)

        calculated_sha256 = sha256_acc.hexdigest()

        if received_bytes == file_size and calculated_sha256 == expected_sha256:
            print(f"[+] [{client_id}] Success! Saved to '{save_filename}'. SHA256 verified")
            conn.sendall(b"SUCCESS: File received and verified by server.")
        else:
            print(f"[-] [{client_id}] Hash mismatch or incomplete transfer!")
            conn.sendall(b"ERROR: Hash or size mismatch.")
            if os.path.exists(save_filename):
                os.remove(save_filename)
        
    except Exception as e:
        print(f"[-] [{client_id}] Upload error: {e}")
        if os.path.exists(save_filename):
            os.remove(save_filename)
        raise e
        

def handle_client(conn, addr,STORAGE_DIR):
    client_id = f"{addr[0]}:{addr[1]}"
    print(f"[+] Thread started for client {client_id}")

    conn.settimeout(60.0)
    try:
        reader = ProtocolReader(conn)
        
        while True:
            header_bytes = reader.recv_line()
            if not header_bytes:
                break

            header_str = header_bytes.decode("utf-8").strip()
            header_data = json.loads(header_str)
            cmd = header_data.get("cmd")

            print(f"[*] [{client_id}] Received command: {cmd}")

            # Command routing
            if cmd == "LOGIN":
                username = header_data.get("username")
                print(f"[*] [{client_id}] Fake login received for user: {username}")
                conn.sendall(b"SUCCESS: Fake login approved.\n")

            elif cmd == "UPLOAD":
                handle_upload(reader, conn, client_id, header_data, STORAGE_DIR)

            elif cmd == "LIST":
                conn.sendall(b"LIST stub: No files implemented yet.\n")

            elif cmd == "DOWNLOAD":
                conn.sendall(b"DOWNLOAD stub: Not implemented yet.\n")

            elif cmd == "QUIT":
                print(f"[*] [{client_id}] Client requested quit.")
                break
            else:
                print(f"[-] [{client_id}] Unknown command: {cmd}")
                conn.sendall(b"ERROR: Unsupported command.\n")

    except socket.timeout:
        print(f"[-] [{client_id}] Connection timed out due to inactivity.")
    except Exception as e:
        print(f"[-] [{client_id}] Error handling client session: {e}")
    finally:
        conn.close()
        print(f"[-] Connection with {client_id} closed.")

def start_server(PORT,STORAGE_DIR):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # Setup SSL Context
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(certfile="server.crt", keyfile="server.key")

    # Bind and listen
    server.bind((HOST, PORT))
    server.listen(20)
    print(f"[*] TLS File Server listening on {HOST}:{PORT}")

    while True:
        raw_conn, addr = server.accept()
        print(f"\n[*] Client connected from {addr[0]}:{addr[1]}")
        print(f"[*] Storage directory set to: {STORAGE_DIR}")
        
        try:
            tls_conn = server_context.wrap_socket(raw_conn, server_side=True)

            client_thread = threading.Thread(
                target=handle_client, args=(tls_conn, addr,STORAGE_DIR), daemon=True
            )
            client_thread.start()

            active_count = threading.active_count() - 1
            print(f"[*] Active client threads: {active_count}")

        except ssl.SSLError as e:
            print(f"[-] TLS Handshake failed with {addr[0]}:{addr[1]}: {e}")
            raw_conn.close()

if __name__ == "__main__":
    args = parse_args()
    PORT = args.port
    STORAGE_DIR = args.storage
    start_server(PORT,STORAGE_DIR)
