from dataclasses import dataclass
import socket
import selectors
import threading
import hashlib
import time
import json
from typing import List, Dict, Tuple
from config import Config

@dataclass
class ChatMessage:
    id: int
    sender: str
    recipient: str
    content: str
    timestamp: float
    read: bool = False

class CustomProtocolServer:
    def __init__(self, host=None, port=None):
        config = Config()
        self.host = host or config.get("host")
        self.port = port or config.get("port")
        self.selector = selectors.DefaultSelector()
        self.accounts: Dict[str, Tuple[str, bool, dict]] = {}  # username: (password_hash, is_logged_in, settings)
        self.messages: Dict[str, List[ChatMessage]] = {}  # username: [messages]
        self.active_connections: Dict[str, socket.socket] = {}
        self.group_clients: Dict[str, socket.socket] = {}
        self.message_id_counter = 0
        self.msgs_per_fetch = config.get("message_fetch_limit")

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

    def handle_delete_account(self, message: str, client_socket: socket.socket):
        try:
            _, username, password = message.split(":")
            
            if username not in self.accounts:
                client_socket.send("User not found".encode())
                return
                
            stored_password, _, _ = self.accounts[username]
            if stored_password != self._hash_password(password):
                client_socket.send("Invalid password".encode())
                return
                
            del self.accounts[username]
            del self.messages[username]
            if username in self.active_connections:
                del self.active_connections[username]
                
            client_socket.send("SUCCESS".encode())
            
        except Exception as e:
            client_socket.send(f"Error: {str(e)}".encode())
    
    def handle_client(self, client_socket):
        try:
            init_message = client_socket.recv(1024).decode()

            if init_message.startswith("GROUP_CHAT:"):
                username = init_message.split(":")[1]
                print(f"New connection from {client_socket.getpeername()} (Group Chat User: {username})")
                self.handle_group_chat_client(username, client_socket)

            elif init_message.startswith(("CREATE:", "LOGIN:")):
                success, username = self.handle_account_operation(init_message, client_socket)
                
                if success:
                    if init_message.startswith("CREATE:"):
                        print(f"New account created from {client_socket.getpeername()} (User: {username})")
                    else:  # LOGIN case
                        print(f"New connection from {client_socket.getpeername()} (Authenticated User: {username})")
                else:
                    if init_message.startswith("CREATE:"):
                        print(f"Failed account creation attempt from {client_socket.getpeername()}")
                    else:  # LOGIN case
                        print(f"Failed login attempt from {client_socket.getpeername()}")

                    client_socket.close()  # Close the socket on failure

            elif init_message.startswith("DELETE_ACCOUNT:"):
                self.handle_delete_account(init_message, client_socket)

            elif init_message.startswith("LOGOUT:"):
                username = init_message.split(":")[1]
                if username in self.active_connections:
                    del self.active_connections[username]
                    print(f"User {username} logged out.")
                client_socket.close()  # Close the connection

            else:
                username = init_message
                print(f"New connection from {client_socket.getpeername()} (Private Chat User: {username})")
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
                return True, username  # Return success
            else:
                client_socket.send("Account already exists".encode())
                return False, None  # Return failure

        elif operation == "LOGIN":
            if self.login(username, password):
                client_socket.send("SUCCESS".encode())
                self.active_connections[username] = client_socket
                threading.Thread(target=self.handle_private_chat_client, 
                                args=(username, client_socket),
                                daemon=True).start()
                return True, username  # Return success
            else:
                client_socket.send("Invalid username or password".encode())
                return False, None  # Return failure

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

    def delete_account(self, username: str, password: str) -> str:
        if username not in self.accounts:
            return "User not found"
        stored_password, _, _ = self.accounts[username]
        if stored_password == self._hash_password(password):
            # Remove all messages where user is recipient
            for user in list(self.messages.keys()):
                self.messages[user] = [msg for msg in self.messages[user] 
                                    if msg.recipient != username]
            
            # Close and remove active connections
            if username in self.active_connections:
                try:
                    self.active_connections[username].close()
                except:
                    pass
                del self.active_connections[username]
                
            # Remove from group chat if present
            if username in self.group_clients:
                try:
                    self.group_clients[username].close()
                except:
                    pass
                del self.group_clients[username]
                
            # Delete account data
            del self.accounts[username]
            del self.messages[username]
            
            return "Account deleted successfully"
        return "Invalid password"

    def logout(self, username: str) -> bool:
        if username in self.accounts:
            stored_password, _, settings = self.accounts[username]
            self.accounts[username] = (stored_password, False, settings)
            if username in self.active_connections:
                del self.active_connections[username]
            return True
        return False

    def find_free_port(self, start_port):
        port = start_port
        max_port = 65535
        
        while port <= max_port:
            try:
                test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                test_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                test_socket.bind((self.host, port))
                test_socket.close()
                return port
            except OSError:
                port += 1
            finally:
                test_socket.close()
        raise RuntimeError("No free ports available")

    def start(self):
        # Find next available port
        try:
            self.port = self.find_free_port(self.port)
            # Update config with new port
            config = Config()
            config.update("port", self.port)
        except RuntimeError as e:
            print(f"Server error: {e}")
            return

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.settimeout(1)
        
        try:
            server_socket.bind((self.host, self.port))
            server_socket.listen(5)
            print(f"Server started on {self.host}:{self.port}")

            while True:
                try:
                    client_socket, address = server_socket.accept()
                    client_socket.settimeout(None)
                    threading.Thread(target=self.handle_client, 
                                args=(client_socket,),
                                daemon=True).start()
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"Error accepting connection: {e}")
                    continue
        finally:
            server_socket.close()

if __name__ == "__main__":
    config = Config()
    server = CustomProtocolServer(config.get("host"), config.get("port"))
    server.start()