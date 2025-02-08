# custom_protocol.py

from dataclasses import dataclass
from enum import Enum
import socket
import selectors
import types
import hashlib
import struct
from typing import Optional, List, Dict
import threading
import queue

# Message type enumeration for our wire protocol
class MessageType(Enum):
    CREATE_ACCOUNT = 1
    LOGIN = 2
    LIST_ACCOUNTS = 3
    SEND_MESSAGE = 4
    READ_MESSAGES = 5
    DELETE_MESSAGES = 6
    DELETE_ACCOUNT = 7
    ERROR = 8
    SUCCESS = 9

@dataclass
class Message:
    """Base message structure for our wire protocol"""
    type: MessageType
    payload_length: int
    payload: bytes

class CustomProtocolServer:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.selector = selectors.DefaultSelector()
        # Store user accounts: username -> (hashed_password, logged_in)
        self.accounts: Dict[str, tuple] = {}
        # Store messages: recipient -> List[tuple(sender, message)]
        self.messages: Dict[str, List[tuple]] = {}
        
    def _hash_password(self, password: str) -> str:
        """Hash password using SHA-256"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def pack_message(self, msg_type: MessageType, payload: bytes) -> bytes:
        """Pack message according to our wire protocol format"""
        # Format: | type (1 byte) | payload_length (4 bytes) | payload |
        return struct.pack('!BL', msg_type.value, len(payload)) + payload
    
    def unpack_message(self, data: bytes) -> Message:
        """Unpack message according to our wire protocol format"""
        msg_type, payload_length = struct.unpack('!BL', data[:5])
        payload = data[5:5+payload_length]
        return Message(MessageType(msg_type), payload_length, payload)
    
    def handle_create_account(self, payload: bytes) -> bytes:
        """Handle account creation request"""
        username, password = payload.decode().split(':')
        if username in self.accounts:
            return self.pack_message(MessageType.ERROR, b"Username already exists")
        self.accounts[username] = (self._hash_password(password), False)
        return self.pack_message(MessageType.SUCCESS, b"Account created successfully")
    
    def handle_login(self, payload: bytes) -> bytes:
        """Handle login request"""
        username, password = payload.decode().split(':')
        if username not in self.accounts:
            return self.pack_message(MessageType.ERROR, b"Username does not exist")
        stored_hash, logged_in = self.accounts[username]
        if stored_hash != self._hash_password(password):
            return self.pack_message(MessageType.ERROR, b"Invalid password")
        
        self.accounts[username] = (stored_hash, True)
        unread_count = len(self.messages.get(username, []))
        return self.pack_message(MessageType.SUCCESS, f"Login successful. {unread_count} unread messages".encode())
    
    def handle_list_accounts(self, payload: bytes) -> bytes:
        """Handle account listing request"""
        pattern = payload.decode()
        matching_accounts = [username for username in self.accounts.keys() 
                           if pattern in username]
        return self.pack_message(MessageType.SUCCESS, 
                               ','.join(matching_accounts).encode())
    
    def handle_send_message(self, payload: bytes) -> bytes:
        """Handle message sending request"""
        sender, recipient, message = payload.decode().split(':', 2)
        if recipient not in self.accounts:
            return self.pack_message(MessageType.ERROR, b"Recipient does not exist")
        
        if recipient not in self.messages:
            self.messages[recipient] = []
        self.messages[recipient].append((sender, message))
        return self.pack_message(MessageType.SUCCESS, b"Message sent successfully")
    
    def start(self):
        """Start the server"""
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind((self.host, self.port))
        server_socket.listen()
        server_socket.setblocking(False)
        self.selector.register(server_socket, selectors.EVENT_READ, data=None)
        
        print(f"Server started on {self.host}:{self.port}")
        
        try:
            while True:
                events = self.selector.select()
                for key, mask in events:
                    if key.data is None:
                        # Accept new connection
                        self.accept_connection(key.fileobj)
                    else:
                        # Handle existing connection
                        self.service_connection(key, mask)
        except KeyboardInterrupt:
            print("Server shutting down...")
        finally:
            self.selector.close()
    
    def accept_connection(self, sock):
        """Accept new client connection"""
        conn, addr = sock.accept()
        print(f"Accepted connection from {addr}")
        conn.setblocking(False)
        data = types.SimpleNamespace(addr=addr, inb=b"", outb=b"")
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        self.selector.register(conn, events, data=data)
    
    def service_connection(self, key, mask):
        """Handle client connection events"""
        sock = key.fileobj
        data = key.data
        
        if mask & selectors.EVENT_READ:
            recv_data = sock.recv(1024)
            if recv_data:
                data.inb += recv_data
                # Process complete messages
                while len(data.inb) >= 5:  # Minimum message size
                    try:
                        message = self.unpack_message(data.inb)
                        # Process message based on type
                        if message.type == MessageType.CREATE_ACCOUNT:
                            response = self.handle_create_account(message.payload)
                        elif message.type == MessageType.LOGIN:
                            response = self.handle_login(message.payload)
                        elif message.type == MessageType.LIST_ACCOUNTS:
                            response = self.handle_list_accounts(message.payload)
                        elif message.type == MessageType.SEND_MESSAGE:
                            response = self.handle_send_message(message.payload)
                        data.outb += response
                        data.inb = data.inb[5+message.payload_length:]
                    except Exception as e:
                        print(f"Error processing message: {e}")
                        break
            else:
                print(f"Closing connection to {data.addr}")
                self.selector.unregister(sock)
                sock.close()
                
        if mask & selectors.EVENT_WRITE:
            if data.outb:
                sent = sock.send(data.outb)
                data.outb = data.outb[sent:]

class CustomProtocolClient:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.receive_queue = queue.Queue()
        self.current_user = None
        
    def connect(self):
        """Connect to the server"""
        try:
            self.socket.connect((self.host, self.port))
            # Start receive thread
            self.receive_thread = threading.Thread(target=self._receive_messages)
            self.receive_thread.daemon = True
            self.receive_thread.start()
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False
    
    def pack_message(self, msg_type: MessageType, payload: bytes) -> bytes:
        """Pack message according to wire protocol format"""
        return struct.pack('!BL', msg_type.value, len(payload)) + payload
    
    def unpack_message(self, data: bytes) -> Message:
        """Unpack message according to wire protocol format"""
        msg_type, payload_length = struct.unpack('!BL', data[:5])
        payload = data[5:5+payload_length]
        return Message(MessageType(msg_type), payload_length, payload)
    
    def _receive_messages(self):
        """Background thread to receive messages"""
        while True:
            try:
                # Read header first (5 bytes)
                header = self.socket.recv(5)
                if not header:
                    break
                    
                msg_type, payload_length = struct.unpack('!BL', header)
                # Read payload
                payload = self.socket.recv(payload_length)
                message = Message(MessageType(msg_type), payload_length, payload)
                self.receive_queue.put(message)
            except Exception as e:
                print(f"Error receiving message: {e}")
                break
    
    def create_account(self, username: str, password: str) -> str:
        """Create a new account"""
        payload = f"{username}:{password}".encode()
        self.socket.send(self.pack_message(MessageType.CREATE_ACCOUNT, payload))
        response = self.receive_queue.get()
        return response.payload.decode()
    
    def login(self, username: str, password: str) -> str:
        """Log in to an existing account"""
        payload = f"{username}:{password}".encode()
        self.socket.send(self.pack_message(MessageType.LOGIN, payload))
        response = self.receive_queue.get()
        if response.type == MessageType.SUCCESS:
            self.current_user = username
        return response.payload.decode()
    
    def list_accounts(self, pattern: str = "") -> List[str]:
        """List accounts matching the given pattern"""
        self.socket.send(self.pack_message(MessageType.LIST_ACCOUNTS, pattern.encode()))
        response = self.receive_queue.get()
        return response.payload.decode().split(',') if response.payload else []
    
    def send_message(self, recipient: str, message: str) -> str:
        """Send a message to another user"""
        if not self.current_user:
            return "Not logged in"
        payload = f"{self.current_user}:{recipient}:{message}".encode()
        self.socket.send(self.pack_message(MessageType.SEND_MESSAGE, payload))
        response = self.receive_queue.get()
        return response.payload.decode()
    
    def close(self):
        """Close the connection"""
        self.socket.close()

if __name__ == "__main__":
    # Example server usage
    server = CustomProtocolServer("localhost", 54321)
    server.start()