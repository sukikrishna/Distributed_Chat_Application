#custom_protocol_groupchat

from dataclasses import dataclass
from enum import Enum
import socket
import selectors
import struct
import threading
import queue
import hashlib
import time
import json
from typing import Optional, List, Dict, Tuple

class MessageType(Enum):
    CREATE_ACCOUNT = 1
    LOGIN = 2
    LIST_ACCOUNTS = 3
    SEND_MESSAGE = 4
    READ_MESSAGES = 5
    DELETE_MESSAGES = 6
    DELETE_ACCOUNT = 7
    LOGOUT = 8
    GROUP_CHAT = 9
    ERROR = 10
    SUCCESS = 11
    UPDATE_SETTINGS = 12

@dataclass
class Message:
    type: MessageType
    payload_length: int
    payload: bytes

@dataclass
class ChatMessage:
    id: int
    sender: str
    recipient: str
    content: str
    timestamp: float
    read: bool = False

class CustomProtocolServer:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.selector = selectors.DefaultSelector()
        self.accounts: Dict[str, Tuple[str, bool, dict]] = {}
        self.messages: Dict[str, List[ChatMessage]] = {}
        self.active_connections: Dict[str, socket.socket] = {}
        self.group_clients: Dict[str, socket.socket] = {}
        self.message_id_counter = 0

    def _hash_password(self, password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    def _generate_message_id(self) -> int:
        self.message_id_counter += 1
        return self.message_id_counter

    def create_account(self, username: str, password: str) -> bool:
        if username in self.accounts:
            return False
        hashed_password = self._hash_password(password)
        self.accounts[username] = (hashed_password, False, {})
        self.messages[username] = []
        return True

    def login(self, username: str, password: str) -> bool:
        if username not in self.accounts:
            return False
        stored_password, is_logged_in, _ = self.accounts[username]
        if stored_password == self._hash_password(password):
            self.accounts[username] = (stored_password, True, {})
            return True
        return False

    def logout(self, username: str) -> bool:
        if username in self.accounts:
            stored_password, _, settings = self.accounts[username]
            self.accounts[username] = (stored_password, False, settings)
            return True
        return False

    def handle_client(self, client_socket):
        """Handles client connection and message routing."""
        try:
            init_message = client_socket.recv(1024).decode()
            
            if init_message.startswith("GROUP_CHAT:"):
                username = init_message[11:]
                self.handle_group_chat_client(username, client_socket)
            elif init_message.startswith(("CREATE:", "LOGIN:")):
                self.handle_account_operation(init_message, client_socket)
            else:
                # Handle regular chat client
                username = init_message
                self.handle_private_chat_client(username, client_socket)
                
        except Exception as e:
            print(f"Error handling client: {e}")
            client_socket.close()

    def handle_account_operation(self, message: str, client_socket: socket.socket):
        """Handle account creation and login operations."""
        parts = message.split(":")
        operation = parts[0]
        username = parts[1]
        password = parts[2]

        if operation == "CREATE":
            if self.create_account(username, password):
                client_socket.send("SUCCESS".encode())
            else:
                client_socket.send("Account already exists".encode())
        elif operation == "LOGIN":
            if self.login(username, password):
                client_socket.send("SUCCESS".encode())
                self.active_connections[username] = client_socket
                
                # Start a thread to handle this client's messages
                threading.Thread(target=self.handle_private_chat_client, 
                               args=(username, client_socket), 
                               daemon=True).start()
            else:
                client_socket.send("Invalid username or password".encode())

    def handle_private_chat_client(self, username: str, client_socket: socket.socket):
        """Handles private chat messaging."""
        self.active_connections[username] = client_socket
        
        while True:
            try:
                message = client_socket.recv(1024).decode()
                if not message:
                    break
                    
                if message == "LIST_ACCOUNTS":
                    # Send list of all usernames
                    account_list = list(self.accounts.keys())
                    client_socket.send(json.dumps(account_list).encode())
                    
                elif message.startswith("MSG:"):
                    # Handle private message
                    _, recipient, content = message.split(":", 2)
                    self.send_private_message(username, recipient, content)
                    
            except Exception as e:
                print(f"Error in private chat: {e}")
                break
                
        # Cleanup when client disconnects
        if username in self.active_connections:
            del self.active_connections[username]
        self.logout(username)
        client_socket.close()

    def handle_group_chat_client(self, username: str, client_socket: socket.socket):
        """Handles a group chat client connection."""
        self.group_clients[username] = client_socket
        self.broadcast_group_message("SYSTEM", f"{username} joined the group chat")
        
        while True:
            try:
                message = client_socket.recv(1024).decode()
                if not message:
                    break
                    
                self.broadcast_group_message(username, message)
                
            except Exception as e:
                print(f"Error in group chat: {e}")
                break
                
        # Cleanup when client disconnects
        if username in self.group_clients:
            del self.group_clients[username]
            self.broadcast_group_message("SYSTEM", f"{username} left the group chat")
        client_socket.close()

    def broadcast_group_message(self, sender: str, message: str):
        """Broadcasts a message to all group chat participants."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        formatted_message = f"[{timestamp}] {sender}: {message}" if sender != "SYSTEM" else message
        
        # Send to all connected group chat clients
        disconnected_clients = []
        for username, client_socket in self.group_clients.items():
            try:
                client_socket.send(formatted_message.encode())
            except:
                disconnected_clients.append(username)
                
        # Cleanup disconnected clients
        for username in disconnected_clients:
            if username in self.group_clients:
                del self.group_clients[username]

    def send_private_message(self, sender: str, recipient: str, content: str):
        """Sends a private message between users."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        formatted_message = f"[{timestamp}] {sender}: {content}"
        
        # Store message in recipient's message list
        message = ChatMessage(
            id=self._generate_message_id(),
            sender=sender,
            recipient=recipient,
            content=content,
            timestamp=time.time()
        )
        self.messages[recipient].append(message)
        
        # Send to recipient if they're online
        if recipient in self.active_connections:
            try:
                self.active_connections[recipient].send(formatted_message.encode())
            except:
                # Handle disconnected recipient
                if recipient in self.active_connections:
                    del self.active_connections[recipient]
        
        # Send confirmation to sender
        if sender in self.active_connections:
            try:
                self.active_connections[sender].send(formatted_message.encode())
            except:
                if sender in self.active_connections:
                    del self.active_connections[sender]

    def delete_account(self, username: str) -> bool:
        """Deletes a user account."""
        if username in self.accounts:
            del self.accounts[username]
            del self.messages[username]
            if username in self.active_connections:
                self.active_connections[username].close()
                del self.active_connections[username]
            return True
        return False

    def start(self):
        """Starts the server."""
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((self.host, self.port))
        server_socket.listen(5)
        print(f"Server started on {self.host}:{self.port}")

        while True:
            try:
                client_socket, address = server_socket.accept()
                print(f"New connection from {address}")
                threading.Thread(target=self.handle_client, 
                               args=(client_socket,), 
                               daemon=True).start()
            except Exception as e:
                print(f"Error accepting connection: {e}")
                continue

if __name__ == "__main__":
    server = CustomProtocolServer("127.0.0.1", 50011)
    server.start()