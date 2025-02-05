import socket
from protocol import CustomProtocol
from json_protocol import JSONProtocol

class ChatClient:
    def __init__(self, host='127.0.0.1', port=5000, use_json=False):
        self.host = host
        self.port = port
        self.use_json = use_json
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_socket.connect((self.host, self.port))
    
    def send_request(self, opcode, username, payload):
        if self.use_json:
            request = JSONProtocol.encode(opcode, username, payload)
        else:
            request = CustomProtocol.encode(opcode, username, payload)
        
        self.client_socket.sendall(request)
        response = self.client_socket.recv(1024)
        
        if self.use_json:
            return JSONProtocol.decode_response(response)
        return CustomProtocol.decode_response(response)
    
    def create_account(self, username, password):
        return self.send_request(JSONProtocol.OP_CREATE_ACCOUNT if self.use_json else CustomProtocol.OP_CREATE_ACCOUNT, username, password)
    
    def login(self, username, password):
        return self.send_request(JSONProtocol.OP_LOGIN if self.use_json else CustomProtocol.OP_LOGIN, username, password)
    
    def send_message(self, sender, recipient, message):
        return self.send_request(JSONProtocol.OP_SEND_MESSAGE if self.use_json else CustomProtocol.OP_SEND_MESSAGE, sender, f"{recipient}|{message}")
    
    def read_messages(self, username):
        return self.send_request(JSONProtocol.OP_READ_MESSAGES if self.use_json else CustomProtocol.OP_READ_MESSAGES, username, "")
    
if __name__ == "__main__":
    client = ChatClient(use_json=True)  # Set to False for Custom Binary Protocol
    client.create_account("alice", "password123")
    client.login("alice", "password123")
    client.send_message("alice", "bob", "Hello Bob!")
    print(client.read_messages("bob"))
