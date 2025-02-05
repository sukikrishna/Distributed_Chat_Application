import socket
import threading
import json
from protocol import CustomProtocol
from database import Database

class ChatServer:
    def __init__(self, host='127.0.0.1', port=5000):
        self.host = host
        self.port = port
        self.clients = {}
        self.database = Database()
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        print(f"Server started on {self.host}:{self.port}")
    
    def start(self):
        while True:
            client_socket, addr = self.server_socket.accept()
            print(f"New connection from {addr}")
            threading.Thread(target=self.handle_client, args=(client_socket,)).start()
    
    def handle_client(self, client_socket):
        while True:
            try:
                data = client_socket.recv(1024)
                if not data:
                    break
                
                opcode, username, payload = CustomProtocol.decode(data)
                response = self.process_request(opcode, username, payload)
                client_socket.sendall(response)
            except Exception as e:
                print(f"Error handling client: {e}")
                break
    
    def process_request(self, opcode, username, payload):
        if opcode == CustomProtocol.OP_CREATE_ACCOUNT:
            return CustomProtocol.encode_response(self.database.create_account(username, payload))
        elif opcode == CustomProtocol.OP_LOGIN:
            return CustomProtocol.encode_response(self.database.login(username, payload))
        elif opcode == CustomProtocol.OP_SEND_MESSAGE:
            recipient, message = payload.split('|', 1)
            return CustomProtocol.encode_response(self.database.send_message(username, recipient, message))
        elif opcode == CustomProtocol.OP_READ_MESSAGES:
            return CustomProtocol.encode_response(self.database.read_messages(username))
        return CustomProtocol.encode_response(False)
    
if __name__ == "__main__":
    server = ChatServer()
    threading.Thread(target=server.start, daemon=True).start()
