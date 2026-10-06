import socket
import os
import threading
import hashlib
import ssl  # 1. FIXED: Added ssl import

HOST = '127.0.0.1'
PORT = 9000
BUFFER_SIZE = 4096
HEADER_SIZE = 1024


def handle_client(conn, addr):
	client_id = f"{addr[0]}:{addr[1]}"
    print(f"[+] Thread started for client {client_id}")
    
    save_filename = None  # 4. FIXED: Prevent UnboundLocalError in except block
    
    try: 
		header_bytes = conn.recv(HEADER_SIZE)
		if not header_bytes:
			print(f"[-] [{client_id}] Empty header received. Closing connection.")
            return 
            
        header_str = header_bytes.decode('utf-8').strip()
        expected_sha256, file_size_str, filename = header_str.split('|')
        file_size = int(file_size_str)
        
        print(f"[*] [{client_id}] Receiving: '{filename}' ({file_size} bytes)")
        print(f"[*] [{client_id}] Expected SHA256: {expected_sha256}")
        
        save_filename = f"saved_{addr[1]}_{os.path.basename(filename)}"
        sha256_acc = hashlib.sha256()
        received_bytes = 0
        
        with open(save_filename, 'wb') as f:
            while received_bytes < file_size:
                chunk_limit = min(BUFFER_SIZE, file_size - received_bytes)
                chunk = conn.recv(chunk_limit)
                
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
                    print(f"[*] [{client_id}] Deleted invalid file: '{save_filename}'")
                
    except Exception as e:
        print(f"[-] [{client_id}] Error handling transfer: {e}")
            
        if save_filename and os.path.exists(save_filename):
            os.remove(save_filename)
            print(f"[*] [{client_id}] Cleaned up partial file: '{save_filename}'")
    finally: 
        conn.close()
        print(f"[-] Connection with {client_id} closed.")
            
                
def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    # 1. Setup SSL Context
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(certfile="server.crt", keyfile="server.key")

    # 2. Bind and listen (2. FIXED: Removed redundant server_socket creation)
    server.bind((HOST, PORT))
    server.listen(5)
    print(f"[*] TLS File Server listening on {HOST}:{PORT}")

    while True:
        raw_conn, addr = server.accept()
        print(f"\n[*] Client connected from {addr[0]}:{addr[1]}")
        
        try:
            # 3. FIXED: Wrap raw socket into a secure TLS socket before passing to thread
            tls_conn = server_context.wrap_socket(raw_conn, server_side=True)
            
            client_thread = threading.Thread(
                target=handle_client, 
                args=(tls_conn, addr),
                daemon=True
            )
            client_thread.start()
            
            active_count = threading.active_count() - 1
            print(f"[*] Active client threads: {active_count}")
            
        except ssl.SSLError as e:
            print(f"[-] TLS Handshake failed with {addr[0]}:{addr[1]}: {e}")
            raw_conn.close()


if __name__ == "__main__":
    start_server()
