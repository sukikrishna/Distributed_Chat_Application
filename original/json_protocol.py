# json_protocol.py

import json
import socket
import selectors
import types
import hashlib
import threading
import queue
from typing import Optional, List, Dict
from dataclasses import dataclass
from enum import Enum

class MessageType(Enum):
    CREATE_ACCOUNT = "create_account"
    LOGIN = "login"
    LIST_ACCOUNTS = "list_accounts"
    SEND_MESSAGE = "send_message"
    READ_MESSAGES = "read_messages"
    DELETE_MESSAGES = "delete_messages"
    DELETE_ACCOUNT = "delete_account"
    ERROR = "error"
    SUCCESS = "success"

@dataclass
class JsonMessage:
    """JSON message structure"""
    type: MessageType
    payload: dict
    
class JsonProtocolServer:
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
    
    def handle_create_account(self, payload: dict) -> dict:
        """Handle account creation request"""
        username = payload["username"]
        password = payload["password"]
        
        if username in self.accounts:
            return {
                "type": MessageType.ERROR.value,
                "payload": {"message": "Username already exists"}
            }
            
        self.accounts[username] = (self._hash_password(password), False)
        return {
            "type": MessageType.SUCCESS.value,
            "payload": {"message": "Account created successfully"}
        }
    
    def handle_login(self, payload: dict) -> dict:
        """Handle login request"""
        username = payload["username"]
        password = payload["password"]
        
        if username not in self.accounts:
            return {
                "type": MessageType.ERROR.value,
                "payload": {"message": "Username does not exist"}
            }
            
        stored_hash, logged_in = self.accounts[username]
        if stored_hash != self._hash_password(password):
            return {
                "type": MessageType.ERROR.value,
                "payload": {"message": "Invalid password"}
            }
            
        self.accounts[username] = (stored_hash, True)
        unread_count = len(self.messages.get(username, []))
        return {
            "type": MessageType.SUCCESS.value,
            "payload": {
                "message": f"Login successful",
                "unread_messages": unread_count
            }
        }
    
    def handle_list_accounts(self, payload: dict) -> dict:
        """Handle account listing request"""
        pattern = payload.get("pattern", "")
        matching_accounts = [username for username in self.accounts.keys() 
                           if pattern in username]
        return {
            "type": MessageType.SUCCESS.value,
            "payload": {"accounts": matching_accounts}
        }
    
    def handle_send_message(self, payload: dict) -> dict:
        """Handle message sending request"""
        sender = payload["sender"]
        recipient = payload["recipient"]
        message = payload["message"]
        
        if recipient not in self.accounts:
            return {
                "type": MessageType.ERROR.value,
                "payload": {"message": "Recipient does not exist"}
            }
            
        if recipient not in self.messages:
            self.messages[recipient] = []
        self.messages[recipient].append((sender, message))
        
        return {
            "type": MessageType.SUCCESS.value,
            "payload": {"message": "Message sent successfully"}
        }
    
    def handle_read_messages(self, payload: dict) -> dict:
        """Handle reading messages request"""
        username = payload["username"]
        count = payload.get("count", None)  # Optional: number of messages to read
        
        if username not in self.accounts:
            return {
                "type": MessageType.ERROR.value,
                "payload": {"message": "User does not exist"}
            }
            
        user_messages = self.messages.get(username, [])
        if count is not None:
            messages_to_read = user_messages[:count]
            self.messages[username] = user_messages[count:]
        else:
            messages_to_read = user_messages
            self.messages[username] = []
            
        return {
            "type": MessageType.SUCCESS.value,
            "payload": {
                "messages": [
                    {"sender": sender, "message": msg}
                    for sender, msg in messages_to_read
                ]
            }
        }
    
    def handle_delete_messages(self, payload: dict) -> dict:
        """Handle message deletion request"""
        username = payload["username"]
        message_indices = payload.get("indices", [])
        
        if username not in self.messages:
            return {
                "type": MessageType.ERROR.value,
                "payload": {"message": "No messages found"}
            }
            
        # Sort indices in reverse order to avoid shifting problems
        for idx in sorted(message_indices, reverse=True):
            if 0 <= idx < len(self.messages[username]):
                self.messages[username].pop(idx)
                
        return {
            "type": MessageType.SUCCESS.value,
            "payload": {"message": "Messages deleted successfully"}
        }
    
    def handle_delete_account(self, payload: dict) -> dict:
        """Handle account deletion request"""
        username = payload["username"]
        password = payload["password"]
        
        if username not in self.accounts:
            return {
                "type": MessageType.ERROR.value,
                "payload": {"message": "Account does not exist"}
            }
            
        stored_hash, _ = self.accounts[username]
        if stored_hash != self._hash_password(password):
            return {
                "type": MessageType.ERROR.value,
                "payload": {"message": "Invalid password"}
            }
            
        # Delete account and all associated messages
        del self.accounts[username]
        if username in self.messages:
            del self.messages[username]
            
        return {
            "type": MessageType.SUCCESS.value,
            "payload": {"message": "Account deleted successfully"}
        }
    
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
                        self.accept_connection(key.fileobj)
                    else:
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
                try:
                    # Try to decode complete JSON messages
                    messages = data.inb.decode().split('\n')
                    for i, message_str in enumerate(messages[:-1]):  # Process all complete messages
                        message = json.loads(message_str)
                        # Handle message based on type
                        if message["type"] == MessageType.CREATE_ACCOUNT.value:
                            response = self.handle_create_account(message["payload"])
                        elif message["type"] == MessageType.LOGIN.value:
                            response = self.handle_login(message["payload"])
                        elif message["type"] == MessageType.LIST_ACCOUNTS.value:
                            response = self.handle_list_accounts(message["payload"])
                        elif message["type"] == MessageType.SEND_MESSAGE.value:
                            response = self.handle_send_message(message["payload"])
                        elif message["type"] == MessageType.READ_MESSAGES.value:
                            response = self.handle_read_messages(message["payload"])
                        elif message["type"] == MessageType.DELETE_MESSAGES.value:
                            response = self.handle_delete_messages(message["payload"])
                        elif message["type"] == MessageType.DELETE_ACCOUNT.value:
                            response = self.handle_delete_account(message["payload"])
                        
                        # Send response
                        data.outb += (json.dumps(response) + '\n').encode()
                    
                    # Keep any incomplete message
                    data.inb = messages[-1].encode()
                    
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    print(f"Error processing message: {e}")
            else:
                print(f"Closing connection to {data.addr}")
                self.selector.unregister(sock)
                sock.close()
                
        if mask & selectors.EVENT_WRITE:
            if data.outb:
                sent = sock.send(data.outb)
                data.outb = data.outb[sent:]

class JsonProtocolClient:
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
    
    def _receive_messages(self):
        """Background thread to receive messages"""
        buffer = ""
        while True:
            try:
                data = self.socket.recv(1024).decode()
                if not data:
                    break
                    
                buffer += data
                while '\n' in buffer:
                    message_str, buffer = buffer.split('\n', 1)
                    message = json.loads(message_str)
                    self.receive_queue.put(message)
            except Exception as e:
                print(f"Error receiving message: {e}")
                break
    
    def send_message(self, message_type: MessageType, payload: dict) -> dict:
        """Send a message to the server and wait for response"""
        message = {
            "type": message_type.value,
            "payload": payload
        }
        self.socket.send((json.dumps(message) + '\n').encode())
        return self.receive_queue.get()
    
    def create_account(self, username: str, password: str) -> dict:
        """Create a new account"""
        return self.send_message(MessageType.CREATE_ACCOUNT, {
            "username": username,
            "password": password
        })
    
    def login(self, username: str, password: str) -> dict:
        """Log in to an existing account"""
        response = self.send_message(MessageType.LOGIN, {
            "username": username,
            "password": password
        })
        if response["type"] == MessageType.SUCCESS.value:
            self.current_user = username
        return response
    
    def list_accounts(self, pattern: str = "") -> dict:
        """List accounts matching the given pattern"""
        return self.send_message(MessageType.LIST_ACCOUNTS, {
            "pattern": pattern
        })
    
    def send_chat_message(self, recipient: str, message: str) -> dict:
        """Send a chat message to another user"""
        if not self.current_user:
            return {
                "type": MessageType.ERROR.value,
                "payload": {"message": "Not logged in"}
            }
        return self.send_message(MessageType.SEND_MESSAGE, {
            "sender": self.current_user,
            "recipient": recipient,
            "message": message
        })
    
    def read_messages(self, count: Optional[int] = None) -> dict:
        """Read messages from the server"""
        if not self.current_user:
            return {
                "type": MessageType.ERROR.value,
                "payload": {"message": "Not logged in"}
            }
        return self.send_message(MessageType.READ_MESSAGES, {
            "username": self.current_user,
            "count": count
        })
    
    def delete_messages(self, indices: List[int]) -> dict:
        """Delete specific messages"""
        if not self.current_user:
            return {
                "type": MessageType.ERROR.value,
                "payload": {"message": "Not logged in"}
            }
        return self.send_message(MessageType.DELETE_MESSAGES, {
            "username": self.current_user,
            "indices": indices
        })
    
    def delete_account(self, password: str) -> dict:
        """Delete the current account"""
        if not self.current_user:
            return {
                "type": MessageType.ERROR.value,
                "payload": {"message": "Not logged in"}
            }
        response = self.send_message(MessageType.DELETE_ACCOUNT, {
            "username": self.current_user,
            "password": password
        })
        if response["type"] == MessageType.SUCCESS.value:
            self.current_user = None
        return response
    
    def close(self):
        """Close the connection"""
        self.socket.close()

if __name__ == "__main__":
    # Example server usage
    server = JsonProtocolServer("localhost", 54322)
    server.start()