import hashlib
import os
import socket
import ssl

HOST = "127.0.0.1"
PORT = 9000
BUFFER_SIZE = 4096
HEADER_SIZE = 1024
	

def send_file(file_path):
    # 1. Validate file existence
    if not os.path.exists(file_path):
        print(f"[-] Error: File '{file_path}' does not exist.")
        return

    # 2. Extract file metadata and compute SHA-256 hash
    file_size = os.path.getsize(file_path)
    filename = os.path.basename(file_path)
  	
    sha256_hash = hashlib.sha256()
    print(f"[*] Reading '{filename}' and calculating SHA-256...")

    with open(file_path, "rb") as f:
        while chunk := f.read(BUFFER_SIZE):
            sha256_hash.update(chunk)

    expected_sha256 = sha256_hash.hexdigest()
    print(f"[*] Calculated SHA256: {expected_sha256}")

    # 3. Format header: SHA256|filesize|filename
    # Padding with spaces to match exact HEADER_SIZE (1024 bytes) expected by server
    header_str = f"{expected_sha256}|{file_size}|{filename}"
    header_bytes = header_str.encode("utf-8")

    if len(header_bytes) > HEADER_SIZE:
        print("[-] Error: Header metadata exceeds maximum header size!")
        return

    header_padded = header_bytes.ljust(HEADER_SIZE, b" ")

    # 4. Connect to server and transmit
    try:
        print(f"[*] Connecting to server at {HOST}:{PORT}...")

        raw_socket = socket.create_connection((HOST, PORT))

        context = ssl.create_default_context()

        # LOCAL DEVELOPMENT TESTING: BYPASS CERTIFICATE CHECK
        # (Remove or replace with proper CA load in production)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        # FIX: Do not pass IP string as server_hostname when check_hostname is False
        client_socket = context.wrap_socket(raw_socket)

        # Send fixed-size header
        client_socket.sendall(header_padded)
        print("[+] Header sent.")

        # Send TLS-encrypted file payload in chunks
        bytes_sent = 0
        with open(file_path, "rb") as f:
            while chunk := f.read(BUFFER_SIZE):
                client_socket.sendall(chunk)
                bytes_sent += len(chunk)
                print(
                    f"\r[*] Progress: {bytes_sent}/{file_size} bytes sent",
                    end="",
                )

        print(
            "\n[+] File transmission complete. Waiting for server response..."
        )

        # Receive confirmation status back from server
        response = client_socket.recv(BUFFER_SIZE).decode("utf-8")
        print(f"[Server Response]: {response}")
        client_socket.close()

    except Exception as e:
        print(f"[-] Network error: {e}")


if __name__ == "__main__":
    file_input = input("Enter path of the file to send: ").strip("\"'")
    send_file(file_input)
