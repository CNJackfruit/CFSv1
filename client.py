import socket 

HOST = '127.0.0.1'
PORT = 9000

def main():
	with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
		client.connect((HOST,PORT))
		print("[*] Connected to server. Type your message below (or 'exit' to quit):")
		
		while True:
			msg = input("> ")
			if msg.lower() == 'exit':
				break
			client.sendall(msg.encode('utf-8'))
			data = client.recv(1024)
			print(f"Echo from server: {data.decode('utf-8')}")

if __name__ == "__main__":
	main()