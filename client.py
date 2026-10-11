import hashlib
import os
import socket
import ssl
import json
import threading 

HOST = "0.0.0.0"
PORT = 8080
BUFFER_SIZE = 4096
HEADER_SIZE = 1024

def create_secure_connection():
    """Helper function to establish a secure SSL socket connection."""
    raw_socket = socket.create_connection((HOST, PORT))
    context = ssl.create_default_context()
    
    # LOCAL DEVELOPMENT TESTING: BYPASS CERTIFICATE CHECK
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    
    return context.wrap_socket(raw_socket)

def perform_login(sock):
  """Mandatory fake login gate that always returns True."""
  print("\n--- AUTHENTICATION REQUIRED ---")
  username = input("Username: ").strip()
  password = input("Password: ").strip()

  # Send login command to server over persistent socket
  header_dict = {"cmd": "LOGIN", "username": username, "password": password}
  sock.sendall((json.dumps(header_dict) + "\n").encode("utf-8"))

  # Receive server response
  response = sock.recv(BUFFER_SIZE).decode("utf-8")
  print(f"[Server Response]: {response.strip()}")

  return True
    
def handle_upload(sock):
    """Handles the UPLOAD command logic."""
    file_path = input("Enter path of the file to send: ").strip("\"'")
    
    if not os.path.exists(file_path):
        print(f"[-] Error: File '{file_path}' does not exist.")
        return

    file_size = os.path.getsize(file_path)
    filename = os.path.basename(file_path)
    
    sha256_hash = hashlib.sha256()
    print(f"[*] Reading '{filename}' and calculating SHA-256...")

    with open(file_path, "rb") as f:
        while chunk := f.read(BUFFER_SIZE):
            sha256_hash.update(chunk)

    expected_sha256 = sha256_hash.hexdigest()
    print(f"[*] Calculated SHA256: {expected_sha256}")

    header_dict = {
        "cmd": "UPLOAD",
        "name": filename,
        "size": file_size,
        "sha256": expected_sha256
    }

    header_bytes = (json.dumps(header_dict) + "\n").encode("utf-8")

    if len(header_bytes) > HEADER_SIZE:
        print("[-] Error: Header metadata exceeds maximum header size!")
        return

    try:
        
        sock.sendall(header_bytes)
        print("[+] JSON command Header sent.")
        
        bytes_sent = 0
        with open(file_path, "rb") as f:
            while chunk := f.read(BUFFER_SIZE):
                sock.sendall(chunk)
                bytes_sent += len(chunk)
                print(f"\r[*] Progress: {bytes_sent}/{file_size} bytes sent", end="")

        print("\n[+] File transmission complete. Waiting for server response...")
        response = sock.recv(BUFFER_SIZE).decode("utf-8")
        print(f"[Server Response]: {response}")

    except Exception as e:
        print(f"[-] Network error: {e}")
        
     
def handle_list(sock):
    """Placeholder for LIST functionality."""
    print("[*] LIST feature selected. (Implement logic here)")

def handle_download(sock):
    """Placeholder for DOWNLOAD functionality."""
    print("[*] DOWNLOAD feature selected. (Implement logic here)")
    
def main():
    print(f"[*] Connecting to server at {HOST}:{PORT}...")
    try:
        sock = create_secure_connection()
        print("[*] Connected securely.")
    except Exception as e:
        print(f"[-] Connection failed: {e}")
        return 
    
    if not perform_login(sock):
        sock.close()
        return 
    
    commands = {
      "1": ("UPLOAD", handle_upload),
      "2": ("LIST", handle_list),
      "3": ("DOWNLOAD", handle_download),
    }
    
    try:
        while True:
            print("\n--- SECURE FILE MANAGER MENU ---")
            for key, (name, _) in commands.items():
                print(f"{key}. [{name}]")
            print("4. [QUIT]")
            
            choice = input("Select an option: ").strip()
            
            if choice == "4" or choice.upper() == "QUIT":
                sock.sendall((json.dumps({"cmd": "QUIT"}) + "\n").encode("utf-8"))
                print("Exiting client. Goodbye!")
                break
            elif choice in commands:
                cmd_name, func = commands[choice]
                print(f"[*] Executing {cmd_name}...")
                func(sock)
            else:
                print("[-] Invalid option. Please choose a valid number.")
    finally:
        sock.close()
        print("[*] Connection closed. ")
                
if __name__ == "__main__":
    main()
