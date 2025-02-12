import socket
import struct
import threading
import hashlib
import sys
import re
import os
import fnmatch
import time
import logging
from collections import defaultdict

from custom_protocol import CustomWireProtocol

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))
from config import Config

# Ensure logs directory exists in the project root
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Set log file path
LOG_FILE = os.path.join(LOG_DIR, "custom_server.log")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

class ChatServer:
    """A multi-threaded chat server using a custom wire protocol.

    This server handles user authentication, message exchange, and 
    account management using `CustomWireProtocol`.

    Attributes:
        host (str): The server hostname or IP address.
        port (int): The port number on which the server runs.
        users (dict): Stores user credentials and settings.
        messages (defaultdict): Stores messages for each user.
        active_users (dict): Tracks online users and their connections.
        message_id_counter (int): Counter for assigning message IDs.
        lock (threading.Lock): Ensures thread-safe operations.
        server (socket.socket): The server socket.
        running (bool): Indicates whether the server is running.
        protocol (CustomWireProtocol): Instance of `CustomWireProtocol` for encoding/decoding messages.
    """
    def __init__(self, host=None, port=None):
        """Initializes the chat server.

        Args:
            host (str, optional): The server hostname. Defaults to `Config` value.
            port (int, optional): The server port. Defaults to `Config` value.
        """
        # Clear log file on server restart
        open(LOG_FILE, "w").close()

        self.config = Config()
        self.host = host or self.config.get("host")
        self.port = port or self.config.get("port")
        self.users = {}  # username -> (password_hash, settings)
        self.messages = defaultdict(list)  # username -> [messages]
        self.active_users = {}  # username -> connection
        self.message_id_counter = 0
        self.lock = threading.Lock()
        self.server = None
        self.running = False
        self.protocol = CustomWireProtocol()

    def hash_password(self, password):
        """Hashes a password using SHA-256.

        Args:
            password (str): The password to hash.

        Returns:
            str: The hashed password.
        """
        return hashlib.sha256(password.encode()).hexdigest()

    def validate_password(self, password):
        """Validates password strength.

        Args:
            password (str): The password to validate.

        Returns:
            bool: True if the password meets security requirements, False otherwise.
        """
        if len(password) < 8:
            return False
        if not re.search(r"\d", password):
            return False
        if not re.search(r"[A-Z]", password):
            return False
        return True

    def send_success_response(self, client_socket, cmd, success, message=None, payload_parts=None):
        """Sends a structured success response to a client.

        Args:
            client_socket (socket.socket): The client socket to send the response to.
            cmd (int): The command type identifier.
            success (bool): Indicates whether the operation was successful.
            message (str, optional): A message describing the response.
            payload_parts (list, optional): Additional payload data to include.
        """
        response_parts = [success]
        
        # Add message if provided
        if message:
            response_parts.append(message)
        else:
            response_parts.append("")
        
        # Add any additional payload parts
        if payload_parts:
            response_parts.extend(payload_parts)
        
        # Send encoded response
        response = self.protocol.encode_message(cmd, response_parts)
        client_socket.send(response)

    def list_users(self, pattern):
        """Finds users matching a given search pattern.

        Args:
            pattern (str): The search pattern (supports wildcards).

        Returns:
            list: A list of matching users with their online/offline status.
        """
        matches = []
        for username in self.users:
            if fnmatch.fnmatch(username.lower(), pattern.lower()):
                matches.append({
                    "username": username,
                    "status": "online" if username in self.active_users else "offline"
                })
        return matches

    def get_unread_count(self, username):
        """Gets the count of unread messages for a user.

        Args:
            username (str): The username to check messages for.

        Returns:
            int: The number of unread messages.
        """
        return len([msg for msg in self.messages[username] if not msg["read"]])

    def handle_client(self, client_socket, address):
        """Handles communication with a connected client.

        Args:
            client_socket (socket.socket): The socket representing the client connection.
            address (tuple): The client's IP address and port.
        """
        logging.info(f"New connection from {address}")
        current_user = None
        buffer = b''

        while True:
            try:
                # Receive data
                chunk = client_socket.recv(4096)
                if not chunk:
                    break
                
                buffer += chunk

                # Process complete messages
                while len(buffer) >= 6:
                    try:
                        total_length = struct.unpack('!I', buffer[:4])[0]
                    except struct.error:
                        logging.error("Invalid message length")
                        break

                    # Check if we have a complete message
                    if len(buffer) < total_length:
                        break
                    
                    # Extract full message
                    message_data = buffer[:total_length]
                    buffer = buffer[total_length:]

                    # Safely decode message
                    try:
                        _, cmd, payload = self.protocol.decode_message(message_data)
                    except Exception as decode_error:
                        logging.error(f"Error decoding message: {decode_error}")
                        break

                    # Process different command types
                    with self.lock:
                        if cmd == CustomWireProtocol.CMD_CREATE:
                            # Decode username and password
                            username, payload = self.protocol.decode_string(payload)
                            password, _ = self.protocol.decode_string(payload)

                            if not username or not password:
                                self.send_success_response(
                                    client_socket, 
                                    cmd, 
                                    False, 
                                    "Username and password required"
                                )
                                continue

                            if not self.validate_password(password):
                                self.send_success_response(
                                    client_socket, 
                                    cmd, 
                                    False, 
                                    "Password must be at least 8 characters with 1 number and 1 uppercase letter"
                                )
                                continue

                            if username in self.users:
                                self.send_success_response(
                                    client_socket, 
                                    cmd, 
                                    False, 
                                    "Username already exists"
                                )
                                continue

                            # Create account
                            self.users[username] = (self.hash_password(password), {})
                            self.messages[username] = []
                            logging.info(f"New account created: {username} from {address}")
                            
                            self.send_success_response(
                                client_socket, 
                                cmd, 
                                True, 
                                "Account created successfully"
                            )

                        elif cmd == CustomWireProtocol.CMD_LOGIN:
                            # Decode username and password
                            username, payload = self.protocol.decode_string(payload)
                            password, _ = self.protocol.decode_string(payload)

                            if username not in self.users:
                                self.send_success_response(
                                    client_socket, 
                                    cmd, 
                                    False, 
                                    "User not found"
                                )
                                continue

                            if self.users[username][0] != self.hash_password(password):
                                self.send_success_response(
                                    client_socket, 
                                    cmd, 
                                    False, 
                                    "Invalid password"
                                )
                                continue

                            if username in self.active_users:
                                self.send_success_response(
                                    client_socket, 
                                    cmd, 
                                    False, 
                                    "User already logged in"
                                )
                                continue

                            # Successful login
                            current_user = username
                            self.active_users[username] = client_socket
                            
                            # Send login success response
                            unread_count = self.get_unread_count(username)
                            self.send_success_response(
                                client_socket, 
                                cmd, 
                                True, 
                                username,
                                [unread_count]
                            )

                        elif cmd == CustomWireProtocol.CMD_LIST:
                            # Decode search pattern
                            pattern, _ = self.protocol.decode_string(payload)
                            if not pattern:
                                pattern = "*"
                            elif not pattern.endswith("*"):
                                pattern = pattern + "*"

                            # Find matching users
                            matches = self.list_users(pattern)
                            
                            # Construct response payload
                            response_parts = []
                            for user in matches:
                                response_parts.append(user['username'])
                                response_parts.append(user['status'])
                            
                            # Send response
                            self.send_success_response(
                                client_socket, 
                                cmd, 
                                True,
                                None,
                                response_parts
                            )

                        elif cmd == CustomWireProtocol.CMD_SEND:
                            if not current_user:
                                self.send_success_response(
                                    client_socket, 
                                    cmd, 
                                    False, 
                                    "Not logged in"
                                )
                                continue

                            # Decode recipient and message content
                            recipient, payload = self.protocol.decode_string(payload)
                            content, _ = self.protocol.decode_string(payload)

                            if recipient not in self.users:
                                self.send_success_response(
                                    client_socket, 
                                    cmd, 
                                    False, 
                                    "Recipient not found"
                                )
                                continue

                            # Create and store message
                            message = {
                                "id": self.message_id_counter,
                                "from": current_user,
                                "content": content,
                                "timestamp": int(time.time()),  # Store as integer timestamp
                                "read": False,
                                "delivered_while_offline": recipient not in self.active_users
                            }
                            self.message_id_counter += 1
                            self.messages[recipient].append(message)
                            
                            # If recipient is active, send notification
                            if recipient in self.active_users:
                                try:
                                    notification = self.protocol.encode_message(
                                        CustomWireProtocol.CMD_SEND,
                                        [True, "new_message", current_user, content]
                                    )
                                    self.active_users[recipient].send(notification)
                                except:
                                    pass  # Ignore notification failures
                            
                            # Send success response to sender
                            self.send_success_response(
                                client_socket, 
                                cmd, 
                                True, 
                                "Message sent"
                            )

                        elif cmd == CustomWireProtocol.CMD_GET_MESSAGES:
                            if not current_user:
                                self.send_success_response(
                                    client_socket, 
                                    cmd, 
                                    False, 
                                    "Not logged in"
                                )
                                continue

                            # Decode desired message count
                            count = struct.unpack('!H', payload[:2])[0] if payload else 50
                            
                            # Get messages sorted by timestamp
                            messages = sorted(
                                [msg for msg in self.messages[current_user] if msg["read"]],
                                key=lambda x: x['timestamp'],
                                reverse=True
                            )
                            
                            # Construct response payload
                            response_parts = []
                            
                            for msg in messages:
                                packed_id = struct.pack('!I', msg['id'])
                                packed_timestamp = struct.pack('!I', msg['timestamp'])
                                response_parts.extend([packed_id, msg['from'], msg['content'], packed_timestamp])
                                                       
                            self.send_success_response(
                                client_socket, 
                                cmd, 
                                True,
                                None,
                                response_parts
                            )

                        elif cmd == CustomWireProtocol.CMD_GET_UNDELIVERED:
                            if not current_user:
                                self.send_success_response(
                                    client_socket, 
                                    cmd, 
                                    False, 
                                    "Not logged in"
                                )
                                continue

                            # Decode desired message count
                            count = struct.unpack('!H', payload[:2])[0] if payload else 50
                            
                            # Get unread messages
                            unread_messages = sorted(
                                [msg for msg in self.messages[current_user] if not msg["read"]],
                                key=lambda x: x['timestamp'],
                                reverse=True
                            )[:count]
                            
                            # Mark messages as read
                            for msg in unread_messages:
                                msg["read"] = True
                            
                            # Construct response payload
                            response_parts = []
                            for msg in unread_messages:
                                packed_id = struct.pack('!I', msg['id'])
                                packed_timestamp = struct.pack('!I', msg['timestamp'])
                                response_parts.extend([packed_id, msg['from'], msg['content'], packed_timestamp])
                            
                            # Send response
                            self.send_success_response(
                                client_socket, 
                                cmd, 
                                True,
                                None,
                                response_parts
                            )

                        elif cmd == CustomWireProtocol.CMD_DELETE_MESSAGES:
                            if not current_user:
                                self.send_success_response(
                                    client_socket, 
                                    cmd, 
                                    False, 
                                    "Not logged in"
                                )
                                continue

                            # Decode message IDs to delete
                            id_count = struct.unpack('!H', payload[:2])[0]
                            ids_to_delete = struct.unpack(f'!{id_count}I', payload[2:2+4*id_count])
                            
                            # Remove specified messages
                            self.messages[current_user] = [
                                msg for msg in self.messages[current_user] 
                                if msg['id'] not in ids_to_delete
                            ]
                            
                            # Send success response
                            self.send_success_response(
                                client_socket, 
                                cmd, 
                                True, 
                                "Messages deleted"
                            )

                        elif cmd == CustomWireProtocol.CMD_DELETE_ACCOUNT:
                            if not current_user:
                                self.send_success_response(
                                    client_socket, 
                                    cmd, 
                                    False, 
                                    "Not logged in"
                                )
                                continue

                            # Decode password
                            password, _ = self.protocol.decode_string(payload)

                            if self.users[current_user][0] != self.hash_password(password):
                                self.send_success_response(
                                    client_socket, 
                                    cmd, 
                                    False, 
                                    "Invalid password"
                                )
                                continue

                            # Delete account
                            del self.users[current_user]
                            del self.messages[current_user]

                            if current_user in self.active_users:
                                del self.active_users[current_user]

                            logging.info(f"Account deleted: {current_user}")
                            current_user = None
                            
                            # Send success response
                            self.send_success_response(
                                client_socket, 
                                cmd, 
                                True, 
                                "Account deleted"
                            )

                        elif cmd == CustomWireProtocol.CMD_LOGOUT:
                            if not current_user:
                                self.send_success_response(
                                    client_socket, 
                                    cmd, 
                                    False, 
                                    "Not logged in"
                                )
                                continue

                            # Remove from active users
                            if current_user in self.active_users:
                                del self.active_users[current_user]

                            logging.info(f"User '{current_user}' logged out")
                            current_user = None
                            
                            # Send logout success response
                            self.send_success_response(
                                client_socket, 
                                cmd, 
                                True, 
                                "Logged out successfully"
                            )

            except Exception as e:
                logging.error(f"Error handling client: {e}")
                break

        # Handle disconnection
        if current_user in self.active_users:
            del self.active_users[current_user]
        
        client_socket.close()

    def start(self):
        """Starts the chat server.

        This method initializes the server, binds it to the specified 
        host and port, and listens for incoming client connections.
        """
        try:
            self.port = self.find_free_port(self.port)
            config = Config()
            config.update("port", self.port)
        except RuntimeError as e:
            logging.info(f"Server error: {e}")
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
                    logging.info(f"Error accepting connection: {e}")
                    continue
        finally:
            self.server.close()

    def stop(self):
        """Stops the chat server by closing the socket and terminating active connections."""
        self.running = False
        if self.server:
            self.server.close()

    def find_free_port(self, start_port):
        """Finds an available port starting from a given number.

        Args:
            start_port (int): The starting port number.

        Returns:
            int: The first available port number.

        Raises:
            RuntimeError: If no free ports are available.
        """
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

if __name__ == "__main__":
    server = ChatServer()
    try:
        server.start()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.stop()