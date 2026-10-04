import socket
import os
import threading

HOST = '127.0.0.1'
PORT = 9000

def handle_client(conn, addr):
	print(f"[+] Connected by {addr}")
	while True:
		data = conn.recv(1024)
		if not data:
			break
		conn.sendall(data)
	print(f"[-] Disconnected {addr}")
	conn.close()

def main():
	server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	server.bind((HOST, PORT))
	server.listen()
	print(f"[*] Echo server listening on {HOST}:{PORT}")

	while True:
		conn, addr = server.accept()
		#start a new thread for each client
		client_thread = threading.Thread(target=handle_client, args=(conn,addr))
		client_thread.start()

if __name__ == "__main__":
	main()
