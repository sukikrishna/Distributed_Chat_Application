import socket
from config import Config
from custom_protocol import CustomProtocol
from json_protocol import JSONProtocol

class ChatClient:
    """Chat client to interact with the chat server using either JSON or Custom Binary Protocol."""
    
    def __init__(self, use_json=False):
        """Initializes the chat client using dynamically loaded configurations.
        
        Args:
            use_json (bool): Determines whether to use JSON or Custom Binary Protocol.
        """
        self.host = Config.SERVER_HOST
        self.port = Config.SERVER_PORT
        self.use_json = use_json
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_socket.connect((self.host, self.port))
    
    def send_request(self, opcode, username, payload):
        """Sends a request to the server.
        
        Args:
            opcode (str or int): Operation code for the request.
            username (str): Username sending the request.
            payload (str): The request payload.
        
        Returns:
            tuple: Response success status and optional data.
        """
        request = JSONProtocol.encode(opcode, username, payload) if self.use_json else CustomProtocol.encode(opcode, username, payload)
        self.client_socket.sendall(request)
        response = self.client_socket.recv(1024)
        return JSONProtocol.decode_response(response) if self.use_json else CustomProtocol.decode_response(response)
    
    def create_account(self, username, password):
        """Creates a new account on the server.
        
        Args:
            username (str): The new account username.
            password (str): The account password.
        
        Returns:
            bool: Whether the account was successfully created.
        """
        return self.send_request(JSONProtocol.OP_CREATE_ACCOUNT if self.use_json else CustomProtocol.OP_CREATE_ACCOUNT, username, password)
    
    def login(self, username, password):
        """Logs into an existing account.
        
        Args:
            username (str): The account username.
            password (str): The account password.
        
        Returns:
            bool: Whether login was successful.
        """
        return self.send_request(JSONProtocol.OP_LOGIN if self.use_json else CustomProtocol.OP_LOGIN, username, password)
    
    def send_message(self, sender, recipient, message):
        """Sends a message to another user.
        
        Args:
            sender (str): The sender's username.
            recipient (str): The recipient's username.
            message (str): The message content.
        
        Returns:
            bool: Whether the message was sent successfully.
        """
        return self.send_request(JSONProtocol.OP_SEND_MESSAGE if self.use_json else CustomProtocol.OP_SEND_MESSAGE, sender, f"{recipient}|{message}")
    
    def read_messages(self, username):
        """Reads all messages for the logged-in user.
        
        Args:
            username (str): The username whose messages should be retrieved.
        
        Returns:
            list: List of messages received.
        """
        return self.send_request(JSONProtocol.OP_READ_MESSAGES if self.use_json else CustomProtocol.OP_READ_MESSAGES, username, "")
    
if __name__ == "__main__":
    client = ChatClient(use_json=True)  # Set to False for Custom Binary Protocol
    client.create_account("alice", "password123")
    client.login("alice", "password123")
    client.send_message("alice", "bob", "Hello Bob!")
    print(client.read_messages("bob"))
