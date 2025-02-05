import socket
import threading
from protocol import CustomProtocol
from json_protocol import JSONProtocol
from database import Database

class ChatServer:
    def __init__(self, host='127.0.0.1', port=5000, use_json=False):
        self.host = host
        self.port = port
        self.use_json = use_json
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
                
                if self.use_json:
                    opcode, username, payload = JSONProtocol.decode(data)
                    response = self.process_request(opcode, username, payload, json_format=True)
                    client_socket.sendall(response)
                else:
                    opcode, username, payload = CustomProtocol.decode(data)
                    response = self.process_request(opcode, username, payload)
                    client_socket.sendall(response)
            except Exception as e:
                print(f"Error handling client: {e}")
                break
    
    def process_request(self, opcode, username, payload, json_format=False):
        if opcode in [CustomProtocol.OP_CREATE_ACCOUNT, JSONProtocol.OP_CREATE_ACCOUNT]:
            success = self.database.create_account(username, payload)
        elif opcode in [CustomProtocol.OP_LOGIN, JSONProtocol.OP_LOGIN]:
            success = self.database.login(username, payload)
        elif opcode in [CustomProtocol.OP_SEND_MESSAGE, JSONProtocol.OP_SEND_MESSAGE]:
            recipient, message = payload.split('|', 1)
            success = self.database.send_message(username, recipient, message)
        elif opcode in [CustomProtocol.OP_READ_MESSAGES, JSONProtocol.OP_READ_MESSAGES]:
            success = self.database.read_messages(username)
        else:
            success = False
        
        if json_format:
            return JSONProtocol.encode_response(success)
        return CustomProtocol.encode_response(success)
    
if __name__ == "__main__":
    server = ChatServer(use_json=True)  # Set to False for Custom Binary Protocol
    threading.Thread(target=server.start, daemon=True).start()
