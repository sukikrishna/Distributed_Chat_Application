import socket
import json
from protocol import CustomProtocol

class ChatClient:
    def __init__(self, host='127.0.0.1', port=5000):
        self.host = host
        self.port = port
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_socket.connect((self.host, self.port))
    
    def send_request(self, opcode, username, payload):
        request = CustomProtocol.encode(opcode, username, payload)
        self.client_socket.sendall(request)
        response = self.client_socket.recv(1024)
        return CustomProtocol.decode_response(response)
    
    def create_account(self, username, password):
        return self.send_request(CustomProtocol.OP_CREATE_ACCOUNT, username, password)
    
    def login(self, username, password):
        return self.send_request(CustomProtocol.OP_LOGIN, username, password)
    
    def send_message(self, sender, recipient, message):
        return self.send_request(CustomProtocol.OP_SEND_MESSAGE, sender, f"{recipient}|{message}")
    
    def read_messages(self, username):
        return self.send_request(CustomProtocol.OP_READ_MESSAGES, username, "")
    
if __name__ == "__main__":
    client = ChatClient()
    client.create_account("alice", "password123")
    client.login("alice", "password123")
    client.send_message("alice", "bob", "Hello Bob!")
    print(client.read_messages("bob"))
