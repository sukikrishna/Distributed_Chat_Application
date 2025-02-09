import socket
import json
import threading
import hashlib
import re
import fnmatch
from collections import defaultdict
import time

class ChatServer:
    def __init__(self, host='localhost', port=56789):
        self.host = host
        self.port = port
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
                        elif username in self.users:
                            response = {
                                "success": False,
                                "message": "Username already exists"
                            }
                        else:
                            self.users[username] = (self.hash_password(password), {})
                            self.messages[username] = []
                            response = {
                                "success": True,
                                "message": "Account created successfully",
                                "username": username
                            }

                    elif cmd == "login":
                        username = msg["username"]
                        password = msg["password"]
                        
                        if username not in self.users:
                            response = {
                                "success": False,
                                "message": "User not found"
                            }
                        elif self.users[username][0] != self.hash_password(password):
                            response = {
                                "success": False,
                                "message": "Invalid password"
                            }
                        elif username in self.active_users:
                            response = {
                                "success": False,
                                "message": "User already logged in"
                            }
                        else:
                            current_user = username
                            self.active_users[username] = client_socket
                            unread_count = self.get_unread_count(username)
                            response = {
                                "success": True,
                                "message": f"Login successful",
                                "username": username,
                                "unread": unread_count
                            }

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
                            )[:count]
                            
                            # Mark messages as read
                            for m in sorted_messages:
                                if not m["read"]:
                                    m["read"] = True
                                    
                            response = {"success": True, "messages": sorted_messages}

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

                    elif cmd == "delete_account":
                        if not current_user:
                            response = {"success": False, "message": "Not logged in"}
                        else:
                            password = msg["password"]
                            if self.users[current_user][0] != self.hash_password(password):
                                response = {"success": False, "message": "Invalid password"}
                            elif any(not m["read"] for m in self.messages[current_user]):
                                response = {"success": False, "message": "Cannot delete account with unread messages"}
                            else:
                                del self.users[current_user]
                                del self.messages[current_user]
                                if current_user in self.active_users:
                                    del self.active_users[current_user]
                                current_user = None
                                response = {"success": True, "message": "Account deleted"}

                    elif cmd == "logout":
                        if current_user and current_user in self.active_users:
                            del self.active_users[current_user]
                        current_user = None
                        response = {"success": True, "message": "Logged out successfully"}

                client_socket.send(json.dumps(response).encode())

            except Exception as e:
                print(f"Error handling client: {e}")
                break

        if current_user and current_user in self.active_users:
            del self.active_users[current_user]
        client_socket.close()

    def start(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind((self.host, self.port))
        self.server.listen(5)
        self.running = True
        print(f"Server running on {self.host}:{self.port}")

        while self.running:
            try:
                client, addr = self.server.accept()
                threading.Thread(target=self.handle_client, 
                               args=(client, addr), 
                               daemon=True).start()
            except Exception as e:
                if self.running:
                    print(f"Error accepting connection: {e}")

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