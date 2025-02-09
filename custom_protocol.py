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
    LEAVE_GROUP = 10
    ERROR = 11
    SUCCESS = 12

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
        self.accounts: Dict[str, Tuple[str, bool, dict]] = {}  # username: (password_hash, is_logged_in, settings)
        self.messages: Dict[str, List[ChatMessage]] = {}  # username: [messages]
        self.active_connections: Dict[str, socket.socket] = {}
        self.group_clients: Dict[str, socket.socket] = {}
        self.message_id_counter = 0
        self.msgs_per_fetch = 10  # Default messages per fetch

    def _hash_password(self, password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    def _generate_message_id(self) -> int:
        self.message_id_counter += 1
        return self.message_id_counter

    def create_account(self, username: str, password: str) -> bool:
        if username in self.accounts:
            return False
        hashed_password = self._hash_password(password)
        self.accounts[username] = (hashed_password, False, {'msgs_per_fetch': self.msgs_per_fetch})
        self.messages[username] = []
        return True

    def login(self, username: str, password: str) -> bool:
        if username not in self.accounts:
            return False
        stored_password, _, settings = self.accounts[username]
        if stored_password == self._hash_password(password):
            self.accounts[username] = (stored_password, True, settings)
            return True
        return False

    def delete_account(self, username: str, password: str) -> bool:
        if username not in self.accounts:
            return False
        stored_password, _, _ = self.accounts[username]
        if stored_password == self._hash_password(password):
            # Remove all messages sent to/from this user
            del self.accounts[username]
            del self.messages[username]
            if username in self.active_connections:
                self.active_connections[username].close()
                del self.active_connections[username]
            return True
        return False

    def handle_client(self, client_socket):
        try:
            init_message = client_socket.recv(1024).decode()
            
            if init_message.startswith("GROUP_CHAT:"):
                username = init_message.split(":")[1]
                self.handle_group_chat_client(username, client_socket)
            elif init_message.startswith(("CREATE:", "LOGIN:")):
                self.handle_account_operation(init_message, client_socket)
            elif init_message.startswith("DELETE_ACCOUNT:"):
                self.handle_delete_account(init_message, client_socket)
            else:
                username = init_message
                self.handle_private_chat_client(username, client_socket)
                
        except Exception as e:
            print(f"Error handling client: {e}")
            client_socket.close()

    def handle_account_operation(self, message: str, client_socket: socket.socket):
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
                threading.Thread(target=self.handle_private_chat_client, 
                               args=(username, client_socket),
                               daemon=True).start()
            else:
                client_socket.send("Invalid credentials".encode())

    def handle_delete_account(self, message: str, client_socket: socket.socket):
        _, username, password = message.split(":")
        if self.delete_account(username, password):
            client_socket.send("SUCCESS".encode())
        else:
            client_socket.send("Invalid credentials".encode())

    def handle_private_chat_client(self, username: str, client_socket: socket.socket):
        self.active_connections[username] = client_socket
        
        while True:
            try:
                message = client_socket.recv(1024).decode()
                if not message:
                    break
                    
                if message == "LIST_ACCOUNTS":
                    account_list = ",".join(self.accounts.keys())
                    client_socket.send(account_list.encode())

                elif message.startswith("MSG:"):
                    _, recipient, content = message.split(":", 2)
                    self.send_private_message(username, recipient, content)
                    
                elif message.startswith("DELETE_MESSAGES:"):
                    msg_ids = message.split(":")[1].split(",")
                    self.delete_messages(username, [int(mid) for mid in msg_ids])
                    client_socket.send("SUCCESS".encode())
                    
                elif message.startswith("READ_MESSAGES:"):
                    count = int(message.split(":")[1])
                    unread = self.get_unread_messages(username, count)
                    client_socket.send(json.dumps(unread).encode())
                    
                elif message.startswith("LOGOUT:"):
                    break
                    
            except Exception as e:
                print(f"Error in private chat: {e}")
                break
                
        if username in self.active_connections:
            del self.active_connections[username]
        self.logout(username)
        client_socket.close()

    def handle_group_chat_client(self, username: str, client_socket: socket.socket):
        self.group_clients[username] = client_socket
        self.broadcast_group_message("SYSTEM", f"{username} joined the group chat")
        
        while True:
            try:
                message = client_socket.recv(1024).decode()
                if not message:
                    break
                
                if message.startswith("LEAVE_GROUP:"):
                    break
                    
                self.broadcast_group_message(username, message)
                
            except Exception as e:
                print(f"Error in group chat: {e}")
                break
                
        if username in self.group_clients:
            del self.group_clients[username]
            self.broadcast_group_message("SYSTEM", f"{username} left the group chat")
        client_socket.close()

    def broadcast_group_message(self, sender: str, message: str):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        formatted_message = f"[{timestamp}] {sender}: {message}" if sender != "SYSTEM" else message
        
        disconnected_clients = []
        for username, client_socket in self.group_clients.items():
            try:
                client_socket.send(formatted_message.encode())
            except:
                disconnected_clients.append(username)
                
        for username in disconnected_clients:
            if username in self.group_clients:
                del self.group_clients[username]

    def send_private_message(self, sender: str, recipient: str, content: str):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        formatted_message = f"[{timestamp}] {sender}: {content}"
        
        message = ChatMessage(
            id=self._generate_message_id(),
            sender=sender,
            recipient=recipient,
            content=content,
            timestamp=time.time()
        )
        
        if recipient in self.messages:
            self.messages[recipient].append(message)
        
        if recipient in self.active_connections:
            try:
                self.active_connections[recipient].send(formatted_message.encode())
            except:
                if recipient in self.active_connections:
                    del self.active_connections[recipient]
        
        if sender in self.active_connections:
            try:
                self.active_connections[sender].send(formatted_message.encode())
            except:
                if sender in self.active_connections:
                    del self.active_connections[sender]

    def get_unread_messages(self, username: str, count: int) -> List[Dict]:
        if username not in self.messages:
            return []
            
        unread = [msg for msg in self.messages[username] if not msg.read]
        to_send = unread[:count]
        
        for msg in to_send:
            msg.read = True
            
        return [{
            'id': msg.id,
            'sender': msg.sender,
            'content': msg.content,
            'timestamp': msg.timestamp
        } for msg in to_send]

    def delete_messages(self, username: str, message_ids: List[int]) -> None:
        if username not in self.messages:
            return
            
        self.messages[username] = [
            msg for msg in self.messages[username]
            if msg.id not in message_ids
        ]

    def logout(self, username: str) -> bool:
        if username in self.accounts:
            stored_password, _, settings = self.accounts[username]
            self.accounts[username] = (stored_password, False, settings)
            if username in self.active_connections:
                del self.active_connections[username]
            return True
        return False

    def start(self):
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
    server = CustomProtocolServer("127.0.0.1", 50022)
    server.start()