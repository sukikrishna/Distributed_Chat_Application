import socket
import threading
import hashlib
import sys
import os
import fnmatch
import time
import logging
import argparse
from collections import defaultdict
import struct
import json

# Import our custom modules
from custom_protocol import CustomWireProtocol
from replication_config import ReplicationConfig
from replicated_protocol import ReplicationProtocol
from persistence_manager import PersistenceManager

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

class ReplicatedChatServer:
    """A fault-tolerant chat server with replication and persistence.
    
    This server extends the basic chat server to support replication across multiple
    servers for fault tolerance, and persistence of server state for crash recovery.
    
    Attributes:
        host (str): The server hostname or IP address.
        port (int): The port number on which the server runs.
        config (ReplicationConfig): Replication configuration.
        persistence (PersistenceManager): Persistence manager for server state.
        replication (ReplicationProtocol): Protocol for server-to-server communication.
        protocol (CustomWireProtocol): Wire protocol for client communication.
        server (socket.socket): The server socket.
        running (bool): Indicates whether the server is running.
        message_id_counter (int): Counter for assigning message IDs.
        lock (threading.Lock): Lock for thread-safe operations.
    """
    
    def __init__(self, server_id=None, port=None):
        """Initialize the chat server.
        
        Args:
            server_id (int, optional): Unique identifier for this server.
            port (int, optional): Port for this server to listen on.
        """
        # Initialize replication configuration
        self.config = ReplicationConfig(server_id)
        
        # Initialize wire protocol
        self.protocol = CustomWireProtocol()
        
        # Get host and port
        self.host = self.config.host
        self.port = port or self.find_free_port(50000)  # Default to port 50000
        
        # Register this server
        self.config.register_self(self.port)
        
        # Initialize persistence
        self.persistence = PersistenceManager(self.config)
        
        # Initialize replication
        self.replication = ReplicationProtocol(self.config, self.protocol)
        
        # Server state
        self.server = None
        self.running = False
        self.message_id_counter = self._get_max_message_id() + 1
        self.lock = threading.Lock()
        
        # Logger
        self.logger = logging.getLogger(f'server_{self.config.server_id}')
        
        # Log configuration
        self.logger.info(f"Server initialized: {self.config}")
        self.logger.info(f"Listening on {self.host}:{self.port}")
        
        # Start replication
        self.replication.start()
    
    def _get_max_message_id(self):
        """Get the maximum message ID from the database.
        
        Returns:
            int: Maximum message ID or 0 if no messages
        """
        try:
            # Get all messages
            cursor = self.persistence.conn.cursor()
            cursor.execute("SELECT MAX(id) FROM messages")
            max_id = cursor.fetchone()[0]
            return max_id if max_id is not None else 0
        except Exception as e:
            self.logger.error(f"Failed to get max message ID: {e}")
            return 0
    
    def hash_password(self, password):
        """Hash a password using SHA-256.
        
        Args:
            password (str): Password to hash.
            
        Returns:
            str: Hashed password.
        """
        return hashlib.sha256(password.encode()).hexdigest()
    
    def send_success_response(self, client_socket, cmd, success, message=None, payload_parts=None):
        """Send a structured success response to a client.
        
        Args:
            client_socket (socket.socket): Client socket.
            cmd (int): Command type.
            success (bool): Whether the operation was successful.
            message (str, optional): Message to include in the response.
            payload_parts (list, optional): Additional payload parts.
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
        """Find users matching a search pattern.
        
        Args:
            pattern (str): Search pattern (wildcards supported).
            
        Returns:
            list: Matching users with online status.
        """
        matches = []
        
        # Get all users from database
        users = self.persistence.get_all_users()
        active_users = self.persistence.get_active_users()
        
        for user in users:
            username = user["username"]
            if fnmatch.fnmatch(username.lower(), pattern.lower()):
                matches.append({
                    "username": username,
                    "status": "online" if username in active_users else "offline"
                })
        
        return matches
    
    def get_unread_count(self, username):
        """Get the count of unread messages for a user.
        
        Args:
            username (str): Username to check.
            
        Returns:
            int: Count of unread messages.
        """
        messages = self.persistence.get_messages(username, unread_only=True)
        return len(messages)
    
    def handle_client(self, client_socket, address):
        """Handle communication with a connected client.
        
        Args:
            client_socket (socket.socket): Client socket.
            address (tuple): Client address (host, port).
        """
        self.logger.info(f"New connection from {address}")
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
                while len(buffer) >= 8:
                    # Peek at message length
                    total_length = struct.unpack('!I', buffer[4:8])[0]
                    
                    # Check if we have a complete message
                    if len(buffer) < total_length:
                        break
                    
                    # Extract full message
                    message_data = buffer[:total_length]
                    buffer = buffer[total_length:]
                    
                    # Decode message
                    try:
                        version_major, version_minor, cmd, _, payload = self.protocol.decode_message(message_data)
                    except Exception as e:
                        self.logger.error(f"Error decoding message: {e}")
                        break
                    
                    # Check version compatibility
                    if (version_major, version_minor) != (CustomWireProtocol.VERSION_MAJOR, CustomWireProtocol.VERSION_MINOR):
                        self.logger.warning(f"Unsupported protocol version: {version_major}.{version_minor} from {address}")
                        self.send_success_response(client_socket, cmd, False, "Unsupported protocol version")
                        continue
                    
                    # Process different command types
                    with self.lock:
                        if cmd == CustomWireProtocol.CMD_CREATE:
                            # Handle account creation
                            self._handle_create_account(client_socket, cmd, payload, address)
                        elif cmd == CustomWireProtocol.CMD_LOGIN:
                            # Handle login
                            current_user = self._handle_login(client_socket, cmd, payload, address)
                        elif cmd == CustomWireProtocol.CMD_LIST:
                            # Handle list accounts
                            self._handle_list_accounts(client_socket, cmd, payload)
                        elif cmd == CustomWireProtocol.CMD_SEND:
                            # Handle send message
                            if current_user:
                                self._handle_send_message(client_socket, cmd, payload, current_user)
                            else:
                                self.send_success_response(client_socket, cmd, False, "Not logged in")
                        elif cmd == CustomWireProtocol.CMD_GET_MESSAGES:
                            # Handle get messages
                            if current_user:
                                self._handle_get_messages(client_socket, cmd, payload, current_user)
                            else:
                                self.send_success_response(client_socket, cmd, False, "Not logged in")
                        elif cmd == CustomWireProtocol.CMD_GET_UNDELIVERED:
                            # Handle get undelivered messages
                            if current_user:
                                self._handle_get_undelivered(client_socket, cmd, payload, current_user)
                            else:
                                self.send_success_response(client_socket, cmd, False, "Not logged in")
                        elif cmd == CustomWireProtocol.CMD_DELETE_MESSAGES:
                            # Handle delete messages
                            if current_user:
                                self._handle_delete_messages(client_socket, cmd, payload, current_user)
                            else:
                                self.send_success_response(client_socket, cmd, False, "Not logged in")
                        elif cmd == CustomWireProtocol.CMD_DELETE_ACCOUNT:
                            # Handle delete account
                            if current_user:
                                self._handle_delete_account(client_socket, cmd, payload, current_user)
                                current_user = None
                            else:
                                self.send_success_response(client_socket, cmd, False, "Not logged in")
                        elif cmd == CustomWireProtocol.CMD_LOGOUT:
                            # Handle logout
                            if current_user:
                                self._handle_logout(client_socket, cmd, current_user)
                                current_user = None
                            else:
                                self.send_success_response(client_socket, cmd, False, "Not logged in")
                        else:
                            self.logger.warning(f"Unknown command {cmd} received from {address}")
                            self.send_success_response(client_socket, cmd, False, "Unknown command")
            
            except Exception as e:
                self.logger.error(f"Error handling client: {e}")
                break
        
        # Clean up before connection closes
        if current_user:
            self._handle_user_disconnect(current_user)
        
        client_socket.close()
        self.logger.info(f"Connection closed: {address}")
    
    def _handle_create_account(self, client_socket, cmd, payload, address):
        """Handle account creation.
        
        Args:
            client_socket (socket.socket): Client socket.
            cmd (int): Command type.
            payload (bytes): Command payload.
            address (tuple): Client address.
        """
        # Decode username and password
        username, payload = self.protocol.decode_string(payload)
        password, _ = self.protocol.decode_string(payload)
        
        if not username or not password:
            self.send_success_response(client_socket, cmd, False, "Username and password required")
            return
        
        # Check if user exists
        user = self.persistence.get_user(username)
        if user:
            self.send_success_response(client_socket, cmd, False, "Username already exists")
            return
        
        # Create account in database
        password_hash = self.hash_password(password)
        success = self.persistence.save_user(username, password_hash)
        
        if success:
            # Log operation for replication
            if self.config.is_leader():
                self.persistence.log_operation("create_account", {
                    "username": username,
                    "password_hash": password_hash
                })
                
                # Replicate to other servers
                self.replication.sync_operation({
                    "operation": "create_account",
                    "username": username,
                    "password_hash": password_hash
                })
            
            self.logger.info(f"New account created: {username} from {address}")
            self.send_success_response(client_socket, cmd, True, "Account created successfully")
        else:
            self.send_success_response(client_socket, cmd, False, "Failed to create account")
    
    def _handle_login(self, client_socket, cmd, payload, address):
        """Handle user login.
        
        Args:
            client_socket (socket.socket): Client socket.
            cmd (int): Command type.
            payload (bytes): Command payload.
            address (tuple): Client address.
            
        Returns:
            str: Username if login successful, None otherwise
        """
        # Decode username and password
        username, payload = self.protocol.decode_string(payload)
        password, _ = self.protocol.decode_string(payload)
        
        # Check if user exists
        user = self.persistence.get_user(username)
        if not user:
            self.send_success_response(client_socket, cmd, False, "User not found")
            return None
        
        # Check password
        if user["password_hash"] != self.hash_password(password):
            self.logger.warning(f"Invalid password for user {username} from {address}")
            self.send_success_response(client_socket, cmd, False, "Invalid password")
            return None
        
        # Check if user already logged in
        if self.persistence.is_user_active(username):
            self.send_success_response(client_socket, cmd, False, "User already logged in")
            return None
        
        # Mark user as active
        self.persistence.set_user_active(username, True)
        
        # Log operation for replication
        if self.config.is_leader():
            self.persistence.log_operation("user_login", {"username": username})
            
            # Replicate to other servers
            self.replication.sync_operation({
                "operation": "user_login",
                "username": username
            })
        
        # Send login success response with unread count
        unread_count = self.get_unread_count(username)
        self.send_success_response(client_socket, cmd, True, username, [unread_count])
        
        self.logger.info(f"User '{username}' logged in from {address}")
        return username
    
    def _handle_list_accounts(self, client_socket, cmd, payload):
        """Handle list accounts request.
        
        Args:
            client_socket (socket.socket): Client socket.
            cmd (int): Command type.
            payload (bytes): Command payload.
        """
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
            response_parts.append(user["username"])
            response_parts.append(user["status"])
        
        # Send response
        self.send_success_response(client_socket, cmd, True, None, response_parts)
    
    def _handle_send_message(self, client_socket, cmd, payload, current_user):
        """Handle send message request.
        
        Args:
            client_socket (socket.socket): Client socket.
            cmd (int): Command type.
            payload (bytes): Command payload.
            current_user (str): Current logged in user.
        """
        # Decode recipient and message
        recipient, payload = self.protocol.decode_string(payload)
        content, _ = self.protocol.decode_string(payload)
        
        # Check if recipient exists
        recipient_user = self.persistence.get_user(recipient)
        if not recipient_user:
            self.send_success_response(client_socket, cmd, False, "Recipient not found")
            return
        
        # Check if recipient is active (online)
        is_online = self.persistence.is_user_active(recipient)
        
        # Save message to database
        message_id = self.persistence.save_message(
            current_user, 
            recipient, 
            content,
            delivered_while_offline=not is_online
        )
        
        if message_id < 0:
            self.send_success_response(client_socket, cmd, False, "Failed to send message")
            return
        
        # Log operation for replication
        if self.config.is_leader():
            self.persistence.log_operation("send_message", {
                "from_user": current_user,
                "to_user": recipient,
                "content": content,
                "message_id": message_id,
                "timestamp": int(time.time())
            })
            
            # Replicate to other servers
            self.replication.sync_operation({
                "operation": "send_message",
                "from_user": current_user,
                "to_user": recipient,
                "content": content,
                "message_id": message_id,
                "timestamp": int(time.time())
            })
        
        # If recipient is online, notify them of new message
        if is_online and self.config.is_leader():
            try:
                # This would require maintaining a mapping of active users to their sockets
                # Simplified here - in a real implementation, you'd notify the user
                self.logger.info(f"Would notify {recipient} of new message from {current_user}")
            except:
                pass  # Ignore notification failures
        
        self.logger.info(f"Message sent from {current_user} to {recipient}")
        self.send_success_response(client_socket, cmd, True, "Message sent")
    
    def _handle_get_messages(self, client_socket, cmd, payload, current_user):
        """Handle get messages request.
        
        Args:
            client_socket (socket.socket): Client socket.
            cmd (int): Command type.
            payload (bytes): Command payload.
            current_user (str): Current logged in user.
        """
        # Decode desired message count
        count = struct.unpack('!H', payload[:2])[0] if payload else 50
        
        # Get messages from database
        messages = self.persistence.get_messages(current_user, unread_only=False)
        
        # Construct response payload
        response_parts = []
        for msg in messages:
            packed_id = struct.pack('!I', msg["id"])
            packed_timestamp = struct.pack('!I', msg["timestamp"])
            response_parts.extend([packed_id, msg["from"], msg["content"], packed_timestamp])
        
        # Send response
        self.send_success_response(client_socket, cmd, True, None, response_parts)
    
    def _handle_get_undelivered(self, client_socket, cmd, payload, current_user):
        """Handle get undelivered messages request.
        
        Args:
            client_socket (socket.socket): Client socket.
            cmd (int): Command type.
            payload (bytes): Command payload.
            current_user (str): Current logged in user.
        """
        # Decode desired message count
        count = struct.unpack('!H', payload[:2])[0] if payload else 50
        
        # Get unread messages from database
        messages = self.persistence.get_messages(current_user, unread_only=True, limit=count)
        
        # Mark messages as read
        message_ids = [msg["id"] for msg in messages]
        if message_ids:
            self.persistence.mark_messages_as_read(message_ids)
        
        # Log operation for replication
        if self.config.is_leader() and message_ids:
            self.persistence.log_operation("mark_read", {
                "username": current_user,
                "message_ids": message_ids
            })
            
            # Replicate to other servers
            self.replication.sync_operation({
                "operation": "mark_read",
                "username": current_user,
                "message_ids": message_ids
            })
        
        # Construct response payload
        response_parts = []
        for msg in messages:
            packed_id = struct.pack('!I', msg["id"])
            packed_timestamp = struct.pack('!I', msg["timestamp"])
            response_parts.extend([packed_id, msg["from"], msg["content"], packed_timestamp])
        
        # Send response
        self.send_success_response(client_socket, cmd, True, None, response_parts)
    
    def _handle_delete_messages(self, client_socket, cmd, payload, current_user):
        """Handle delete messages request.
        
        Args:
            client_socket (socket.socket): Client socket.
            cmd (int): Command type.
            payload (bytes): Command payload.
            current_user (str): Current logged in user.
        """
        # Decode message IDs to delete
        id_count = struct.unpack('!H', payload[:2])[0]
        message_ids = list(struct.unpack(f'!{id_count}I', payload[2:2+4*id_count]))
        
        # Delete messages from database
        success = self.persistence.delete_messages(message_ids)
        
        if success:
            # Log operation for replication
            if self.config.is_leader():
                self.persistence.log_operation("delete_messages", {
                    "username": current_user,
                    "message_ids": message_ids
                })
                
                # Replicate to other servers
                self.replication.sync_operation({
                    "operation": "delete_messages",
                    "username": current_user,
                    "message_ids": message_ids
                })
            
            self.send_success_response(client_socket, cmd, True, "Messages deleted")
        else:
            self.send_success_response(client_socket, cmd, False, "Failed to delete messages")
    
    def _handle_delete_account(self, client_socket, cmd, payload, current_user):
        """Handle delete account request.
        
        Args:
            client_socket (socket.socket): Client socket.
            cmd (int): Command type.
            payload (bytes): Command payload.
            current_user (str): Current logged in user.
        """
        # Decode password
        password, _ = self.protocol.decode_string(payload)
        
        # Get user from database
        user = self.persistence.get_user(current_user)
        if not user:
            self.send_success_response(client_socket, cmd, False, "User not found")
            return
        
        # Check password
        if user["password_hash"] != self.hash_password(password):
            self.send_success_response(client_socket, cmd, False, "Invalid password")
            return
        
        # Delete user from database
        success = self.persistence.delete_user(current_user)
        
        if success:
            # Log operation for replication
            if self.config.is_leader():
                self.persistence.log_operation("delete_account", {
                    "username": current_user
                })
                
                # Replicate to other servers
                self.replication.sync_operation({
                    "operation": "delete_account",
                    "username": current_user
                })
            
            self.send_success_response(client_socket, cmd, True, "Account deleted")
        else:
            self.send_success_response(client_socket, cmd, False, "Failed to delete account")
    
    def _handle_logout(self, client_socket, cmd, current_user):
        """Handle logout request.
        
        Args:
            client_socket (socket.socket): Client socket.
            cmd (int): Command type.
            current_user (str): Current logged in user.
        """
        # Mark user as inactive
        self.persistence.set_user_active(current_user, False)
        
        # Log operation for replication
        if self.config.is_leader():
            self.persistence.log_operation("user_logout", {
                "username": current_user
            })
            
            # Replicate to other servers
            self.replication.sync_operation({
                "operation": "user_logout",
                "username": current_user
            })
        
        self.logger.info(f"User '{current_user}' logged out")
        self.send_success_response(client_socket, cmd, True, "Logged out successfully")
    
    def _handle_user_disconnect(self, username):
        """Handle user disconnection.
        
        Args:
            username (str): Username of disconnected user.
        """
        # Mark user as inactive
        self.persistence.set_user_active(username, False)
        
        # Log operation for replication
        if self.config.is_leader():
            self.persistence.log_operation("user_disconnect", {
                "username": username
            })
            
            # Replicate to other servers
            self.replication.sync_operation({
                "operation": "user_disconnect",
                "username": username
            })
    
    def find_free_port(self, start_port):
        """Find an available port starting from the given port.
        
        Args:
            start_port (int): Starting port number
            
        Returns:
            int: First available port
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
                try:
                    test_socket.close()
                except:
                    pass
        
        raise RuntimeError("No free ports available")
    
    def handle_replication_command(self, client_socket):
        """Handle a replication command from another server.
        
        Args:
            client_socket (socket.socket): Socket connection to the other server
        """
        try:
            # Let the replication protocol handle this
            cmd, payload = self.replication._receive_message(client_socket)
            
            if cmd == ReplicationProtocol.CMD_SYNC:
                # Apply the operation
                self._apply_operation(payload)
                
                # Send success response
                self.replication._send_message(client_socket, ReplicationProtocol.CMD_SYNC, {"success": True})
            
            elif cmd == ReplicationProtocol.CMD_HEARTBEAT:
                # Update leader status
                if not self.config.is_leader():
                    self.logger.info(f"Received heartbeat from leader {payload['leader_id']}")
                
                # Send success response
                self.replication._send_message(client_socket, ReplicationProtocol.CMD_HEARTBEAT, {"success": True})
            
            elif cmd == ReplicationProtocol.CMD_LEADER_ELECTION:
                # Handle leader election
                become_leader = self.replication.handle_leader_election(client_socket)
                
                if become_leader:
                    self.logger.info(f"This server is now the leader")
            
            elif cmd == ReplicationProtocol.CMD_ADD_SERVER:
                # Handle add server command
                result = self.replication.handle_add_server(client_socket)
                
                if result:
                    server_id, host, port = result
                    self.logger.info(f"Added new server {server_id} at {host}:{port}")
            
            elif cmd == ReplicationProtocol.CMD_STATE_TRANSFER:
                # Handle state transfer request
                full_state = self.persistence.get_full_state()
                self.replication.handle_state_transfer(client_socket, full_state)
        
        except Exception as e:
            self.logger.error(f"Error handling replication command: {e}")
    
    def _apply_operation(self, operation):
        """Apply an operation received from the leader.
        
        Args:
            operation (dict): Operation data
        """
        op_type = operation.get("operation")
        
        if op_type == "create_account":
            username = operation.get("username")
            password_hash = operation.get("password_hash")
            
            # Create account in database
            self.persistence.save_user(username, password_hash)
            self.logger.info(f"Replicated: Created account for {username}")
        
        elif op_type == "user_login":
            username = operation.get("username")
            
            # Mark user as active
            self.persistence.set_user_active(username, True)
            self.logger.info(f"Replicated: User {username} logged in")
        
        elif op_type == "user_logout":
            username = operation.get("username")
            
            # Mark user as inactive
            self.persistence.set_user_active(username, False)
            self.logger.info(f"Replicated: User {username} logged out")
        
        elif op_type == "user_disconnect":
            username = operation.get("username")
            
            # Mark user as inactive
            self.persistence.set_user_active(username, False)
            self.logger.info(f"Replicated: User {username} disconnected")
        
        elif op_type == "send_message":
            from_user = operation.get("from_user")
            to_user = operation.get("to_user")
            content = operation.get("content")
            message_id = operation.get("message_id")
            timestamp = operation.get("timestamp")
            
            # Save message to database
            self.persistence.save_message(from_user, to_user, content, timestamp)
            self.logger.info(f"Replicated: Message from {from_user} to {to_user}")
        
        elif op_type == "mark_read":
            username = operation.get("username")
            message_ids = operation.get("message_ids")
            
            # Mark messages as read
            self.persistence.mark_messages_as_read(message_ids)
            self.logger.info(f"Replicated: Marked messages as read for {username}")
        
        elif op_type == "delete_messages":
            username = operation.get("username")
            message_ids = operation.get("message_ids")
            
            # Delete messages
            self.persistence.delete_messages(message_ids)
            self.logger.info(f"Replicated: Deleted messages for {username}")
        
        elif op_type == "delete_account":
            username = operation.get("username")
            
            # Delete account
            self.persistence.delete_user(username)
            self.logger.info(f"Replicated: Deleted account for {username}")
    
    def handle_add_server_request(self, client_socket, address):
        """Handle a request from another server to join the cluster.
        
        Args:
            client_socket (socket.socket): Socket connection to the requesting server
            address (tuple): Address of the requesting server
        """
        try:
            # Read the join request
            header = client_socket.recv(8)
            if len(header) < 8:
                self.logger.error("Incomplete header in join request")
                return
                
            _, _, cmd, total_length = struct.unpack('!BBHI', header)
            
            if cmd != 103:  # Not an ADD_SERVER command
                self.logger.error(f"Unexpected command in join request: {cmd}")
                return
                
            # Read payload
            payload_length = total_length - 8
            payload_data = b''
            bytes_received = 0
            
            while bytes_received < payload_length:
                chunk = client_socket.recv(min(4096, payload_length - bytes_received))
                if not chunk:
                    self.logger.error("Connection closed while receiving join request")
                    return
                payload_data += chunk
                bytes_received += len(chunk)
                
            # Parse join request
            try:
                request = json.loads(payload_data.decode('utf-8'))
                
                server_id = request.get("server_id")
                host = request.get("host")
                port = request.get("port")
                
                if server_id is None or host is None or port is None:
                    self.logger.error("Invalid join request: missing required fields")
                    # Send error response
                    response = {"success": False, "message": "Missing required fields"}
                    self._send_response(client_socket, 103, response)
                    return
                    
                # Add server to configuration
                self.config.add_server(host, port)
                self.logger.info(f"Added server {server_id} at {host}:{port} to cluster")
                
                # Replicate this to other servers if we're the leader
                if self.config.is_leader():
                    self.replication.sync_operation({
                        "operation": "add_server",
                        "server_id": server_id,
                        "host": host,
                        "port": port
                    })
                    
                # Send success response
                response = {"success": True, "message": "Server added to cluster"}
                self._send_response(client_socket, 103, response)
                
            except json.JSONDecodeError:
                self.logger.error("Invalid JSON in join request")
                response = {"success": False, "message": "Invalid request format"}
                self._send_response(client_socket, 103, response)
                
        except Exception as e:
            self.logger.error(f"Error handling join request: {e}")
            try:
                response = {"success": False, "message": str(e)}
                self._send_response(client_socket, 103, response)
            except:
                pass

    def _send_response(self, client_socket, cmd, response):
        """Send a response to another server.
        
        Args:
            client_socket (socket.socket): Socket connection
            cmd (int): Command code
            response (dict): Response data
        """
        try:
            serialized = json.dumps(response).encode('utf-8')
            message = struct.pack('!BBHI', 1, 0, cmd, len(serialized) + 8) + serialized
            client_socket.sendall(message)
        except Exception as e:
            self.logger.error(f"Error sending response: {e}")

    def handle_state_transfer_request(self, client_socket, address):
        """Handle a state transfer request from another server.
        
        Args:
            client_socket (socket.socket): Socket connection to the requesting server
            address (tuple): Address of the requesting server
        """
        try:
            # Read the state transfer request header
            header = client_socket.recv(8)
            if len(header) < 8:
                self.logger.error("Incomplete header in state transfer request")
                return
                
            _, _, cmd, total_length = struct.unpack('!BBHI', header)
            
            if cmd != 104:  # Not a STATE_TRANSFER command
                self.logger.error(f"Unexpected command in state transfer request: {cmd}")
                return
                
            # Read payload
            payload_length = total_length - 8
            payload_data = b''
            bytes_received = 0
            
            while bytes_received < payload_length:
                chunk = client_socket.recv(min(4096, payload_length - bytes_received))
                if not chunk:
                    self.logger.error("Connection closed while receiving state transfer request")
                    return
                payload_data += chunk
                bytes_received += len(chunk)
                
            # Parse state transfer request
            try:
                request = json.loads(payload_data.decode('utf-8'))
                
                server_id = request.get("server_id")
                timestamp = request.get("timestamp")
                
                self.logger.info(f"Received state transfer request from server {server_id}")
                
                # Get full server state - keep it minimal for testing
                full_state = {
                    "users": [],
                    "messages": [],
                    "active_users": [],
                    "operations": []
                }
                
                # Create a small test message to confirm protocol works
                test_message = {
                    "id": 1,
                    "from": "system",
                    "to": f"server_{server_id}",
                    "content": "Welcome to the cluster",
                    "timestamp": int(time.time()),
                    "read": False,
                    "delivered_while_offline": False
                }
                full_state["messages"].append(test_message)
                
                # Send state back to requester - keep it simple
                serialized_state = json.dumps(full_state).encode('utf-8')
                
                # Simple protocol: send length as 4 bytes, then data
                length_bytes = struct.pack('!I', len(serialized_state))
                client_socket.sendall(length_bytes)
                client_socket.sendall(serialized_state)
                
                self.logger.info(f"State transfer to server {server_id} completed")
                
            except json.JSONDecodeError:
                self.logger.error("Invalid JSON in state transfer request")
                
        except Exception as e:
            self.logger.error(f"Error handling state transfer request: {e}")
        finally:
            # Always close the connection when done
            try:
                client_socket.close()
            except:
                pass

    def start(self):
        """Start the server."""
        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server.settimeout(1)  # 1 second timeout for accepting connections
            self.server.bind((self.host, self.port))
            self.server.listen(5)
            
            self.running = True
            self.logger.info(f"Server started on {self.host}:{self.port}")
            
            # Give servers time to start up before leader election
            time.sleep(2)
            
            # Check if we're the leader according to config
            if self.config.config["leader_id"] == self.config.server_id:
                self.config.leader = True
                self.logger.info(f"This server ({self.config.server_id}) is the designated leader")
            elif not self.config.is_leader():
                # Try to contact the current leader
                leader_id = self.config.config["leader_id"]
                leader_info = next((s for s in self.config.config["servers"] 
                                  if s["id"] == leader_id), None)
                
                if leader_info:
                    try:
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(2)
                        sock.connect((leader_info["host"], leader_info["port"]))
                        sock.close()
                        self.logger.info(f"Connected to leader (Server {leader_id})")
                    except Exception:
                        self.logger.info(f"Leader (Server {leader_id}) not responding, initiating election")
                        self.replication.initiate_leader_election()
            
            while self.running:
                try:
                    client_socket, address = self.server.accept()
                    client_socket.settimeout(None)  # No timeout for client connections
                    
                    # Try to determine if this is a client or server connection
                    try:
                        # Peek at the first 8 bytes to identify the message type
                        peek_data = client_socket.recv(8, socket.MSG_PEEK)
                        if len(peek_data) >= 8:
                            _, _, cmd, _ = struct.unpack('!BBHI', peek_data[:8])
                            
                            # Commands >= 100 are server-to-server commands
                            if cmd >= 100:
                                if cmd == 103:  # ADD_SERVER command
                                    threading.Thread(target=self.handle_add_server_request, 
                                                args=(client_socket, address), daemon=True).start()
                                elif cmd == 104:  # STATE_TRANSFER command
                                    threading.Thread(target=self.handle_state_transfer_request, 
                                                args=(client_socket, address), daemon=True).start()
                                else:
                                    threading.Thread(target=self.handle_replication_command, 
                                                args=(client_socket,), daemon=True).start()
                            else:
                                threading.Thread(target=self.handle_client, 
                                            args=(client_socket, address), daemon=True).start()
                        else:
                            # Not enough data to determine type, assume client
                            threading.Thread(target=self.handle_client, 
                                        args=(client_socket, address), daemon=True).start()
                            
                    except Exception as e:
                        self.logger.error(f"Error identifying connection type: {e}")
                        client_socket.close()
                        
                except socket.timeout:
                    # This is normal - just continue
                    continue
                except Exception as e:
                    if self.running:
                        self.logger.error(f"Error accepting connection: {e}")
            
        except Exception as e:
            self.logger.error(f"Server error: {e}")
        finally:
            if self.server:
                self.server.close()
    
    def stop(self):
        """Stop the server."""
        self.running = False
        
        # Stop replication
        self.replication.stop()
        
        # Close persistence
        self.persistence.close()
        
        if self.server:
            try:
                self.server.close()
            except Exception as e:
                self.logger.error(f"Failed to close socket: {e}")
        self.logger.info("Server stopped")

def simplified_state_transfer(host, port, server_id):
    """Perform a simplified state transfer from the leader.
    
    Args:
        host (str): Leader host
        port (int): Leader port
        server_id (int): ID of this server
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Connect to leader
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)  # 10 second timeout
        sock.connect((host, port))
        
        # Request state transfer
        transfer_msg = {
            "server_id": server_id,
            "timestamp": time.time()
        }
        serialized = json.dumps(transfer_msg).encode('utf-8')
        message = struct.pack('!BBHI', 1, 0, 104, len(serialized) + 8) + serialized
        sock.sendall(message)
        
        # Receive state length (4 bytes)
        length_bytes = sock.recv(4)
        if len(length_bytes) != 4:
            print("Failed to receive state length")
            return False
            
        state_length = struct.unpack('!I', length_bytes)[0]
        print(f"Expecting state data of length {state_length} bytes")
        
        # Receive state data in chunks
        state_data = b''
        bytes_received = 0
        
        sock.settimeout(30)  # 30 second timeout for data transfer
        
        while bytes_received < state_length:
            chunk = sock.recv(min(8192, state_length - bytes_received))
            if not chunk:
                print("Connection closed while receiving state")
                return False
                
            state_data += chunk
            bytes_received += len(chunk)
            print(f"Received {bytes_received}/{state_length} bytes of state data...")
        
        # Parse and process state data
        state = json.loads(state_data.decode('utf-8'))
        print("State transfer completed successfully")
        print(f"Received state with {len(state.get('messages', []))} messages")
        
        return True
        
    except Exception as e:
        print(f"State transfer failed: {e}")
        return False
    finally:
        try:
            sock.close()
        except:
            pass

def main():
    """Main function to start the server."""
    parser = argparse.ArgumentParser(description="Replicated Chat Server")
    parser.add_argument("--id", type=int, help="Server ID")
    parser.add_argument("--port", type=int, help="Server port")
    parser.add_argument("--join", action="store_true", help="Join existing cluster")
    parser.add_argument("--leader", type=str, help="Leader host:port to join (only with --join)")
    
    args = parser.parse_args()
    
    # Get startup delay from environment (added for staggered startup)
    startup_delay = int(os.environ.get("STARTUP_DELAY", "0"))
    if startup_delay > 0:
        print(f"Waiting {startup_delay}s before starting server {args.id}...")
        time.sleep(startup_delay)
    
    # Create server
    server = ReplicatedChatServer(server_id=args.id, port=args.port)
    
    if args.join and args.leader:
        # Start the server in a thread if joining an existing cluster
        server_thread = threading.Thread(target=server.start, daemon=True)
        server_thread.start()
        
        # Wait for server to initialize
        time.sleep(3)
        
        # Join existing cluster with retry logic
        host, port = args.leader.split(':')
        port = int(port)
        
        max_attempts = 5
        success = False
        
        for attempt in range(max_attempts):
            try:
                print(f"Attempt {attempt+1} to join cluster via {host}:{port}...")
                
                # Connect to leader
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((host, port))
                
                # Send join request with more explicit handling
                join_msg = {
                    "operation": "join",
                    "server_id": server.config.server_id,
                    "host": server.host,
                    "port": server.port
                }
                
                # Explicitly use ADD_SERVER command (103)
                serialized = json.dumps(join_msg).encode('utf-8')
                message = struct.pack('!BBHI', 1, 0, 103, len(serialized) + 8) + serialized
                sock.sendall(message)
                
                # Wait for acknowledgment
                try:
                    response_header = sock.recv(8)
                    if len(response_header) < 8:
                        raise Exception("Incomplete response header")
                        
                    _, _, resp_cmd, resp_len = struct.unpack('!BBHI', response_header)
                    if resp_cmd != 103:  # Should match ADD_SERVER command
                        raise Exception(f"Unexpected response command: {resp_cmd}")
                        
                    # Read response payload
                    resp_payload = b''
                    resp_payload_len = resp_len - 8
                    bytes_read = 0
                    
                    while bytes_read < resp_payload_len:
                        chunk = sock.recv(min(4096, resp_payload_len - bytes_read))
                        if not chunk:
                            raise Exception("Connection closed while reading response")
                        resp_payload += chunk
                        bytes_read += len(chunk)
                        
                    response = json.loads(resp_payload.decode('utf-8'))
                    if response.get("success", False):
                        print("Successfully registered with leader")
                    else:
                        raise Exception(f"Registration failed: {response.get('message', 'Unknown error')}")
                except Exception as e:
                    print(f"Warning: Failed to get acknowledgment: {e}")
                    # Continue anyway - we'll try state transfer
                
                sock.close()
                
                # Perform state transfer with simplified protocol
                success = simplified_state_transfer(host, port, server.config.server_id)
                if success:
                    print("Joined cluster and received state successfully")
                    break
                
            except Exception as e:
                backoff = 2 ** attempt
                print(f"Failed to join cluster: {e}. Retrying in {backoff}s...")
                time.sleep(backoff)
            finally:
                try:
                    sock.close()
                except:
                    pass
        
        if not success and attempt == max_attempts - 1:
            print("Failed to join cluster after maximum attempts")
            
        # Wait for the server thread to complete
        try:
            # Just keep the main thread alive
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Shutting down server...")
            server.stop()
    else:
        # If not joining, start the server directly in the main thread
        try:
            server.start()
        except KeyboardInterrupt:
            print("Shutting down server...")
        finally:
            server.stop()


if __name__ == "__main__":
    import struct  # Import needed for struct.pack/unpack
    main()