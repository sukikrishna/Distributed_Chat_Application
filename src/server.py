import socket
import threading
from config import Config
from t_custom_protocol import CustomProtocol
from json_protocol import JSONProtocol
from database import Database

class ChatServer:
    """Chat server handling client connections, authentication, and message routing."""
    
    def __init__(self, use_json=False):
        """Initializes the chat server using dynamically loaded configurations.
        
        Args:
            use_json (bool): Determines whether to use JSON or Custom Binary Protocol.
        """
        self.host = Config.SERVER_HOST
        self.port = Config.SERVER_PORT
        self.use_json = use_json
        self.clients = {}  # Stores connected clients
        self.database = Database()
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        print(f"Server started on {self.host}:{self.port}")
    
    def start(self):
        """Starts the server to accept client connections."""
        while True:
            client_socket, addr = self.server_socket.accept()
            print(f"New connection from {addr}")
            threading.Thread(target=self.handle_client, args=(client_socket,)).start()
    
    def handle_client(self, client_socket):
        """Handles communication with a connected client.
        
        Args:
            client_socket (socket): The socket object for the connected client.
        """
        try:
            username = client_socket.recv(1024).decode("utf-8")  # First message is the username
            self.clients[username] = client_socket  # Store active client
            print(f"{username} connected.")
            
            while True:
                data = client_socket.recv(1024)
                if not data:
                    break
                
                opcode, sender, payload = (JSONProtocol.decode(data) if self.use_json else CustomProtocol.decode(data))
                response = self.process_request(opcode, sender, payload)
                client_socket.sendall(response)
        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            self.disconnect_client(username)
    
    def process_request(self, opcode, username, payload):
        """Processes a client request and returns the appropriate response.
        
        Args:
            opcode (str or int): Operation code for the request.
            username (str): Username associated with the request.
            payload (str): Request payload.
        
        Returns:
            bytes: Encoded response message.
        """
        if opcode in [CustomProtocol.OP_CREATE_ACCOUNT, JSONProtocol.OP_CREATE_ACCOUNT]:
            success = self.database.create_account(username, payload)
        elif opcode in [CustomProtocol.OP_LOGIN, JSONProtocol.OP_LOGIN]:
            success = self.database.login(username, payload)
        elif opcode in [CustomProtocol.OP_SEND_MESSAGE, JSONProtocol.OP_SEND_MESSAGE]:
            recipient, message = payload.split('|', 1)
            if recipient in self.clients:  # If recipient is online, send immediately
                self.clients[recipient].sendall(JSONProtocol.encode_response(True, f"{username}: {message}") if self.use_json else CustomProtocol.encode_response(True, f"{username}: {message}"))
            else:
                self.database.send_message(username, recipient, message)  # Store for later
            success = True
        elif opcode in [CustomProtocol.OP_READ_MESSAGES, JSONProtocol.OP_READ_MESSAGES]:
            success = self.database.read_messages(username)
        else:
            success = False
        
        return JSONProtocol.encode_response(success) if self.use_json else CustomProtocol.encode_response(success)
    
    def disconnect_client(self, username):
        """Removes a client from the active client list upon disconnection.
        
        Args:
            username (str): The username of the disconnected client.
        """
        if username in self.clients:
            print(f"{username} disconnected.")
            del self.clients[username]
    
if __name__ == "__main__":
    server = ChatServer(use_json=True)  # Set to False for Custom Binary Protocol
    threading.Thread(target=server.start, daemon=True).start()
