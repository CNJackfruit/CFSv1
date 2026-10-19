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

