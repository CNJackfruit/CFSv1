import hashlib
import json
import os
import socket
import ssl
import struct
import threading
import argparse
import metadata
from utils import ProtocolReader
import auth
from pathlib import Path
HOST = "0.0.0.0"

BUFFER_SIZE = 4096

def parse_args():
    server_dir = Path(__file__).resolve().parent
    CFSv1_root = server_dir.parent

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
        default="database", 
        help="Directory path for file storage (default: storage/)"
    )
    
    args = parser.parse_args()
    
    folder_name = Path(args.storage).name
    
    
    args.storage = str(CFSv1_root / folder_name)
    
    return args

class FileSizeError(Exception):
    """Raised when an upload exceeds the maximum allowed file size."""
    pass

def handle_upload(reader, conn, client_id, header_data,STORAGE_DIR,owner=None):

    """Handles the file upload logic."""
    filename = header_data.get("name")
    file_size = header_data.get("size")
    max_size_bytes = 209715200
    if(file_size>=max_size_bytes):
        raise FileSizeError(f"Rejected: {client_file_size} bytes exceeds the 200 MB limit.")
    expected_sha256 = header_data.get("sha256")

    print(f"[*] [{client_id}] Upload request for: '{filename}' ({file_size} bytes)")
    print(f"[*] [{client_id}] Expected SHA256: {expected_sha256}")

    os.makedirs(STORAGE_DIR, exist_ok=True)
    
    clean_filename = os.path.basename(filename)
    
    save_filename = os.path.join(STORAGE_DIR, clean_filename)
    
    safe_client_id = client_id.replace(":","_")
    temp_save_filename = f"{save_filename}.part.{safe_client_id}"
    
    sha256_acc = hashlib.sha256()
    received_bytes = 0

    try:
        with open(temp_save_filename, "wb") as f:
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
            
            # Just pass where the file is, where it's going, and its stats
            success, msg = metadata.add_or_update(
                temp_save_filename, 
                save_filename, 
                owner, 
                file_size, 
                calculated_sha256
            )
            
            if success:
                print(f"[+] [{client_id}] Success! Saved to '{save_filename}'. SHA256 verified")
                response = {"status": "SUCCESS", "msg": msg}
                conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
            else:
                print(f"[-] [{client_id}] Denied: {msg}")
                response = {"status": "ERROR", "msg": msg}
                conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
                if os.path.exists(temp_save_filename):
                    os.remove(temp_save_filename)
            
        else:
            print(f"[-] [{client_id}] Hash mismatch or incomplete transfer!")
            error_msg = {"status": "ERROR", "msg": "Hash or size mismatch."}
            conn.sendall((json.dumps(error_msg) + "\n").encode("utf-8"))
            if os.path.exists(temp_save_filename):
                os.remove(temp_save_filename)
                
    except FileSizeError as e:
        print(f"[-] [{client_id}] {e}")
        error_msg = {"status": "ERROR", "msg": str(e)}
        conn.sendall((json.dumps(error_msg) + "\n").encode("utf-8"))
        return
        
    except Exception as e:
        print(f"[-] [{client_id}] Upload error: {e}")
        if os.path.exists(temp_save_filename):
            os.remove(temp_save_filename)
        
        # Send JSON error back to client instead of crashing thread
        error_msg = {"status": "ERROR", "msg": f"Server fault: {str(e)}"}
        conn.sendall((json.dumps(error_msg) + "\n").encode("utf-8"))
        return
        
def handle_download(conn, client_id, header_data, login_user):
    """Handles the server-side logic for verifying and sending a requested file."""
    filename = header_data.get("name")
    file_meta = metadata.get(filename)
    file_path = os.path.join(STORAGE_DIR, filename)

    # EDGE CASE CHECK: Is it missing from JSON?
    if not file_meta:
        conn.sendall(b'{"status": "ERROR", "msg": "file not found in database"}\n')
        return

    # EDGE CASE CHECK: Is it in JSON, but physically missing from the disk?
    if not os.path.exists(file_path):
        print(f"[-] WARNING: Database mismatch! '{filename}' is missing from disk.")
        conn.sendall(b'{"status": "ERROR", "msg": "file is corrupted or missing on server"}\n')
        return

    # 1. Send the header so the client knows what to expect
    response = {
        "status": "OK",
        "size": file_meta["size"],
        "sha256": file_meta["sha256"]
    }
    conn.sendall((json.dumps(response) + "\n").encode("utf-8"))

    # 2. Stream the physical file bytes to the client
    print(f"[*] [{client_id}] Sending '{filename}' to client...")
    with open(file_path, "rb") as f:
        while chunk := f.read(4096):
            conn.sendall(chunk)

    # 3. Update the download counter safely
    metadata.count_download(filename)
    print(f"[+] [{client_id}] Finished sending '{filename}'.")

def handle_client(conn, addr, STORAGE_DIR):
    client_id = f"{addr[0]}:{addr[1]}"
    print(f"[+] Thread started for client {client_id}")

    conn.settimeout(60.0)
    login_user = None  # <--- FIXED: Defined outside the loop to persist state across commands

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
                password = header_data.get("password")
                
                if auth.authenticate(username, password):
                    login_user = username
                    print(f"[+] [{client_id}] User '{username}' authenticated successfully.")
                    conn.sendall(b'{"status": "OK", "msg": "Login successful"}\n')
                else:
                    print(f"[-] [{client_id}] Failed login attempt for '{username}'.")
                    conn.sendall(b'{"status": "ERROR", "msg": "Invalid username or password"}\n')
                    
            elif cmd == "REGISTER":
                username = header_data.get("username")
                password = header_data.get("password")
                
                success, msg = auth.register(username, password)
                if success:
                    print(f"[+] [{client_id}] New user registered: '{username}'")
                    conn.sendall((json.dumps({"status": "OK", "msg": msg}) + "\n").encode('utf-8'))
                else:
                    conn.sendall((json.dumps({"status": "ERROR", "msg": msg}) + "\n").encode('utf-8'))

            elif cmd == "UPLOAD":
                if not login_user:
                    conn.sendall(b'{"status": "ERROR", "msg": "not logged in"}\n')
                    continue
                handle_upload(reader, conn, client_id, header_data, STORAGE_DIR, owner=login_user)

            elif cmd == "LIST":
                if not login_user:
                    conn.sendall(b'{"status": "ERROR", "msg": "not logged in"}\n')
                    continue
                
                # 1. Safely grab the dictionary from memory
                files_dict = metadata.list_all()
                
                # 2. Format the response exactly as expected by the client
                response = {
                    "status": "OK",
                    "files": files_dict
                }
                
                # 3. Convert to a JSON string, add the newline, and send
                conn.sendall((json.dumps(response) + "\n").encode("utf-8"))

            elif cmd == "DOWNLOAD":
                if not login_user:
                    conn.sendall(b'{"status": "ERROR", "msg": "not logged in"}\n')
                    continue
                handle_download(conn, client_id, header_data, login_user)

            elif cmd == "QUIT":
                print(f"[*] [{client_id}] Client requested quit.")
                break
            else:
                print(f"[-] [{client_id}] Unknown command: {cmd}")
                conn.sendall(b'{"status": "ERROR", "msg": "Unsupported command"}\n')

    except socket.timeout:
        print(f"[-] [{client_id}] Connection timed out due to inactivity.")
    except Exception as e:
        print(f"[-] [{client_id}] Error handling client session: {e}")
    finally:
        conn.close()
        print(f"[-] Connection with {client_id} closed.")

### THE SERVER DOESNT REPSOND WITHOUT LOGIN COMMAND FIRST THE login_user variable is set to None and we can verify this by using netcat and sending the commands directly without login

def start_server(PORT,STORAGE_DIR):
    metadata.load()
    auth.load()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # Setup SSL Context
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(certfile="server/server.crt", keyfile="server/server.key")

    # Bind and listen
    server.bind((HOST, PORT))
    server.listen(20)
    print(f"[*] TLS File Server listening on {HOST}:{PORT}")
    print(f"[*] Storage directory set to: {STORAGE_DIR}")
    while True:
        raw_conn, addr = server.accept()
        print(f"\n[*] Client connected from {addr[0]}:{addr[1]}")
        
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
