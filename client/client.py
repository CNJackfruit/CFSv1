import hashlib
import os
import socket
import ssl
import json
import threading 
from utils import ProtocolReader

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

def perform_login(sock, reader):
    """Handles the initial authentication loop before granting menu access."""
    while True:
        print("\n--- AUTHENTICATION ---")
        print("1. Login")
        print("2. Register")
        print("3. Quit")
        
        choice = input("Select an option: ").strip()
        
        if choice == "3":
            return False
            
        if choice not in ["1", "2"]:
            print("[-] Invalid option.")
            continue
            
        username = input("Username: ").strip()
        
        # You can use getpass for hidden password typing if you want: 
        # import getpass; password = getpass.getpass("Password: ")
        password = input("Password: ").strip() 
        
        if not username or not password:
            print("[-] Username and password cannot be empty.")
            continue

        cmd = "LOGIN" if choice == "1" else "REGISTER"
        
        # 1. Send the credentials to the server
        request = {"cmd": cmd, "username": username, "password": password}
        sock.sendall((json.dumps(request) + "\n").encode("utf-8"))
        
        # 2. Read the server's response
        response_bytes = reader.recv_line()
        if not response_bytes:
            print("[-] Server disconnected.")
            return False
            
        response = json.loads(response_bytes.decode("utf-8").strip())
        
        if response.get("status") == "OK":
            print(f"[+] {response.get('msg')}")
            if cmd == "LOGIN":
                return True  # Access granted, proceeds to main menu
            # If they just registered, loop back so they can actually log in
        else:
            print(f"[-] {response.get('msg')}")

def handle_download(sock, reader):
    """Requests a file from the server and downloads it safely."""
    filename = input("Enter the filename to download: ").strip()
    if not filename:
        return
        
    # 1. Send the DOWNLOAD command
    command = {"cmd": "DOWNLOAD", "name": filename}
    sock.sendall((json.dumps(command) + "\n").encode("utf-8"))
    
    # 2. Read the server's response header
    response_bytes = reader.recv_line()
    if not response_bytes:
        print("[-] Server disconnected.")
        return
        
    response = json.loads(response_bytes.decode("utf-8").strip())
    
    # Check if the server rejected it (like your missing file scenario)
    if response.get("status") == "ERROR":
        print(f"[-] Server Error: {response.get('msg')}")
        return
        
    file_size = response.get("size")
    expected_sha256 = response.get("sha256")
    
    # Create a local downloads folder to avoid clutter
    os.makedirs("client_downloads", exist_ok=True)
    save_path = os.path.join("client_downloads", filename)
    
    print(f"[*] Downloading '{filename}' ({file_size} bytes)...")
    
    # 3. Download the exact bytes using ProtocolReader and verify the hash
    sha256_acc = hashlib.sha256()
    
    with open(save_path, "wb") as f:
        file_data = reader.recv_exact(file_size)
        f.write(file_data)
        sha256_acc.update(file_data)
        
    calculated_sha256 = sha256_acc.hexdigest()
    
    if calculated_sha256 == expected_sha256:
        print(f"[+] Success! File saved to '{save_path}'")
        print(f"[+] SHA256 match: {calculated_sha256}")
    else:
        print("[-] Hash mismatch! The file was corrupted during transfer.")
        os.remove(save_path) # Instantly delete the bad file

def handle_upload(sock,reader):
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
        
     
def handle_list(sock,reader):
    """Requests the file list from the server and prints it."""
    
    command = {"cmd":"LIST"}
    sock.sendall((json.dumps(command)+"\n").encode("utf-8"))
    
    response_bytes = reader.recv_line()
    if not response_bytes:
        print("[-] Server disconncted or failed to respond.")
        return
    
    try:
        response = json.loads(response_bytes.decode("utf-8").strip())
    except json.JSONDecodeError:
        print("[-] Failed to parse server response.")
        return
    
    if response.get("status") == "ERROR":
        print(f"[-] Server Error: {response.get('msg')}")
        return 
    
    files = response.get("files",{})
    
    if not files:
        print("[*] No files currently hosted on server.")
    
    print(f"\n{'FILENAME':<20} | {'OWNER':<10} | {'SIZE (bytes)':<15} | {'DOWNLOADS':<10}")
    print("-"*85)
    
    for filename, details in files.items():
        owner = details.get("owner","unknown")
        size = details.get("size", 0)
        downloads = details.get("downloads", 0)
        uploaded = details.get("uploaded", "unknown")
        
        print(f"{filename:<20} | {owner:<10} | {size:<15} | {downloads:<10} | {uploaded}")
    print("-"*85)


def main():
    print(f"[*] Connecting to server at {HOST}:{PORT}...")
    try:
        sock = create_secure_connection()
        print("[*] Connected securely.")
        
        reader = ProtocolReader(sock)
    except Exception as e:
        print(f"[-] Connection failed: {e}")
        return 
    
    if not perform_login(sock,reader):
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
                func(sock,reader)
            else:
                print("[-] Invalid option. Please choose a valid number.")
    finally:
        sock.close()
        print("[*] Connection closed. ")
                
if __name__ == "__main__":
    main()
