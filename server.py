import socket
import json
import threading
import hashlib
import re
import fnmatch
from collections import defaultdict
import time
from config import Config

class ChatServer:
    def __init__(self, host=None, port=None):
        config = Config()
        self.host = host or config.get("host")
        self.port = port or config.get("port")
        self.users = {}  # username -> (password_hash, settings)
        self.messages = defaultdict(list)  # username -> [messages]
        self.active_users = {}  # username -> connection
        self.message_id_counter = 0
        self.lock = threading.Lock()
        self.server = None
        self.running = False

    def hash_password(self, password):
        """Hash password using SHA-256."""
        return hashlib.sha256(password.encode()).hexdigest()

    def validate_password(self, password):
        """Ensure password meets minimum requirements."""
        if len(password) < 8:
            return False
        if not re.search(r"\d", password):
            return False
        if not re.search(r"[A-Z]", password):
            return False
        return True

    def get_unread_count(self, username):
        """Get count of messages received while user was offline."""
        return len([msg for msg in self.messages[username] 
                   if not msg["read"] and msg.get("delivered_while_offline", True)])

    def handle_client(self, client_socket, address):
        print(f"New connection from {address}")
        current_user = None

        while True:
            try:
                data = client_socket.recv(4096).decode()
                if not data:
                    break

                msg = json.loads(data)
                cmd = msg.get("cmd")
                response = {"success": False, "message": "Invalid command"}

                with self.lock:
                    if cmd == "create":
                        username = msg["username"]
                        password = msg["password"]
                        
                        if not self.validate_password(password):
                            response = {
                                "success": False,
                                "message": "Password must be at least 8 characters with 1 number and 1 uppercase letter"
                            }
                            print(f"Failed account creation attempt from {address} (Username: {username}) - Password requirements not met")
                        elif username in self.users:
                            response = {
                                "success": False,
                                "message": "Username already exists"
                            }
                            print(f"Failed account creation attempt from {address} (Username: {username}) - Username already exists")
                        else:
                            self.users[username] = (self.hash_password(password), {})
                            self.messages[username] = []
                            response = {
                                "success": True,
                                "message": "Account created successfully",
                                "username": username
                            }
                            print(f"New account created from {address} (User: {username})")

                    elif cmd == "login":
                        username = msg["username"]
                        password = msg["password"]
                        
                        if username not in self.users:
                            response = {
                                "success": False,
                                "message": "User not found"
                            }
                            print(f"Failed login attempt from {address} (Username: {username}) - User not found")
                        elif self.users[username][0] != self.hash_password(password):
                            response = {
                                "success": False,
                                "message": "Invalid password"
                            }
                            print(f"Failed login attempt from {address} (Username: {username}) - Incorrect password")
                        elif username in self.active_users:
                            response = {
                                "success": False,
                                "message": "User already logged in"
                            }
                            print(f"Failed login attempt from {address} (Username: {username}) - Already logged in")
                        else:
                            current_user = username
                            self.active_users[username] = client_socket
                            unread_count = self.get_unread_count(username)
                            response = {
                                "success": True,
                                "message": "Login successful",
                                "username": username,
                                "unread": unread_count
                            }
                            print(f"User logged in from {address} (Username: {username})")

                    elif cmd == "list":
                        pattern = msg.get("pattern", "*")
                        matches = []
                        for username in self.users:
                            if fnmatch.fnmatch(username.lower(), pattern.lower()):
                                matches.append({
                                    "username": username,
                                    "status": "online" if username in self.active_users else "offline"
                                })
                        response = {"success": True, "users": matches}

                    elif cmd == "send":
                        if not current_user:
                            response = {"success": False, "message": "Not logged in"}
                        else:
                            recipient = msg["to"]
                            content = msg["content"]
                            
                            if recipient not in self.users:
                                response = {"success": False, "message": "Recipient not found"}
                                print(f"Failed message send from {current_user} to {recipient} - Recipient not found")
                            else:
                                message = {
                                    "id": self.message_id_counter,
                                    "from": current_user,
                                    "content": content,
                                    "timestamp": time.time(),
                                    "read": False,
                                    "delivered_while_offline": recipient not in self.active_users
                                }
                                self.message_id_counter += 1
                                self.messages[recipient].append(message)
                                
                                # If recipient is active, send immediately
                                if recipient in self.active_users:
                                    try:
                                        self.active_users[recipient].send(json.dumps({
                                            "success": True,
                                            "message_type": "new_message",
                                            "message": message
                                        }).encode())
                                    except:
                                        pass  # Handle disconnected socket
                                
                                response = {"success": True, "message": "Message sent"}
                                print(f"Message sent from {current_user} to {recipient}")

                    elif cmd == "get_messages":
                        if not current_user:
                            response = {"success": False, "message": "Not logged in"}
                        else:
                            count = msg.get("count", 10)
                            messages = self.messages[current_user]
                            # Get all messages, sorted by timestamp
                            sorted_messages = sorted(
                                messages,
                                key=lambda x: x["timestamp"],
                                reverse=True
                            )
                            # Mark messages as read
                            for m in sorted_messages:
                                if not m["read"]:
                                    m["read"] = True
                                    
                            response = {"success": True, "messages": sorted_messages}

                    elif cmd == "get_undelivered":
                        if not current_user:
                            response = {"success": False, "message": "Not logged in"}
                        else:
                            count = msg.get("count", 10)
                            messages = self.messages[current_user]
                            # Get only undelivered messages
                            undelivered = sorted(
                                [m for m in messages if not m["read"] and m.get("delivered_while_offline", True)],
                                key=lambda x: x["timestamp"],
                                reverse=True
                            )
                            # Mark as read
                            for m in undelivered:
                                m["read"] = True
                                    
                            response = {"success": True, "messages": undelivered}
                            print(f"User {current_user} retrieved {len(unread)} messages")
                    elif cmd == "delete_messages":
                        if not current_user:
                            response = {"success": False, "message": "Not logged in"}
                        else:
                            msg_ids = set(msg["message_ids"])
                            self.messages[current_user] = [
                                m for m in self.messages[current_user]
                                if m["id"] not in msg_ids
                            ]
                            response = {"success": True, "message": "Messages deleted"}
                            print(f"User {current_user} deleted messages {msg_ids}")

                    elif cmd == "delete_account":
                        if not current_user:
                            response = {"success": False, "message": "Not logged in"}
                        else:
                            password = msg["password"]
                            if self.users[current_user][0] != self.hash_password(password):
                                response = {"success": False, "message": "Invalid password"}
                                print(f"Failed account deletion for {current_user} - Incorrect password")
                            elif any(not m["read"] for m in self.messages[current_user]):
                                response = {"success": False, "message": "Cannot delete account with unread messages"}
                                print(f"Failed account deletion for {current_user} - Unread messages exist")
                            else:
                                del self.users[current_user]
                                del self.messages[current_user]
                                if current_user in self.active_users:
                                    del self.active_users[current_user]
                                print(f"Account deleted: {current_user}")
                                current_user = None
                                response = {"success": True, "message": "Account deleted"}

                    elif cmd == "logout":
                        if current_user in self.active_users:
                            del self.active_users[current_user]
                        print(f"User logged out: {current_user}")
                        current_user = None
                        response = {"success": True, "message": "Logged out successfully"}

                client_socket.send(json.dumps(response).encode())

            except Exception as e:
                print(f"Error handling client: {e}")
                break

        if current_user in self.active_users:
            del self.active_users[current_user]
        client_socket.close()

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
        # Find next available port if needed
        try:
            self.port = self.find_free_port(self.port)
            # Update config with the new port
            config = Config()
            config.update("port", self.port)
        except RuntimeError as e:
            print(f"Server error: {e}")
            return

        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.settimeout(1)

        try:
            self.server.bind((self.host, self.port))
            self.server.listen(5)
            self.running = True
            print(f"Server started on {self.host}:{self.port}")

            while self.running:
                try:
                    client_socket, address = self.server.accept()
                    client_socket.settimeout(None)
                    threading.Thread(target=self.handle_client, 
                                    args=(client_socket, address), 
                                    daemon=True).start()
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"Error accepting connection: {e}")
                    continue
        finally:
            self.server.close()


    def stop(self):
        self.running = False
        if self.server:
            self.server.close()

if __name__ == "__main__":
    server = ChatServer()
    try:
        server.start()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.stop()