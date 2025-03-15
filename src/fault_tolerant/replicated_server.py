import sys
import os
import grpc
import threading
import time
import logging
import pickle
import json
import uuid
import socket
from concurrent import futures
from collections import defaultdict

# Add the parent directory to sys.path to ensure we find our local modules
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

# Import local modules
from config import Config

# Create logs directory if it doesn't exist
LOG_DIR = os.path.join(os.path.dirname(current_dir), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "replicated_server.log")),
        logging.StreamHandler()
    ]
)

# Specify the proto module paths
# sys.path.append(os.path.join(parent_dir, "gRPC_protocol"))
sys.path.append(os.path.join(current_dir))
import chat_extended_pb2 as chat
import chat_extended_pb2_grpc as rpc

class ReplicatedChatServer(rpc.ChatServerServicer):
    """A fault-tolerant, replicated chat server with persistence.
    
    This server implements a master-slave replication architecture for fault tolerance.
    It persists messages and user data to disk and synchronizes state with other servers.
    
    Attributes:
        server_id (str): Unique identifier for this server instance
        config (Config): Configuration object
        persistence_dir (str): Directory for persisting server state
        users (dict): Stored user credentials and settings
        messages (defaultdict): Messages per user
        active_users (dict): Active user connections
        active_streams (dict): Active message streams per user
        message_id_counter (int): Counter for message IDs
        is_master (bool): Flag indicating if this server is the master
        replica_servers (list): List of replica server addresses
        replica_stubs (dict): gRPC stubs for communicating with replicas
        lock (threading.Lock): Lock for thread-safe operations
        heartbeat_interval (int): Interval for sending heartbeats to replicas in seconds
    """
    
    def __init__(self, server_id, host, port, replica_addresses=None, persistence_dir=None, is_master=False):
        """Initialize the replicated chat server.
        
        Args:
            server_id (str): Unique identifier for this server
            host (str): Host address to bind to
            port (int): Port to bind to
            replica_addresses (list, optional): Addresses of replica servers in format ["host:port"]
            persistence_dir (str, optional): Directory to store persistent data
            is_master (bool, optional): Whether this server starts as the master
        """
        self.server_id = server_id
        self.config = Config()
        self.address = f"{host}:{port}"
        
        # Set persistence directory
        if persistence_dir:
            self.persistence_dir = persistence_dir
        else:
            self.persistence_dir = os.path.join(os.path.dirname(current_dir), "data", f"server_{server_id}")
        
        # Create persistence directory if it doesn't exist
        os.makedirs(self.persistence_dir, exist_ok=True)
        
        # Server state
        self.users = {}  # username -> (password_hash, settings)
        self.messages = defaultdict(list)  # username -> [messages]
        self.active_users = {}  # username -> connected (context)
        self.active_streams = {}  # username -> list of stream contexts
        self.message_id_counter = 0
        
        # Replication state
        self.is_master = is_master
        self.replica_servers = replica_addresses or []
        self.replica_stubs = {}  # address -> stub
        self.lock = threading.Lock()
        self.heartbeat_interval = 5  # seconds
        
        # Load persisted state or initialize new state
        self.load_state()
        
        # Connect to replicas
        if self.replica_servers:
            self.connect_to_replicas()
            
        # Start heartbeat thread if master
        if self.is_master:
            self.heartbeat_thread = threading.Thread(target=self.send_heartbeats, daemon=True)
            self.heartbeat_thread.start()
            logging.info(f"Server {self.server_id} started as MASTER")
        else:
            logging.info(f"Server {self.server_id} started as REPLICA")

    def persist_state(self):
        """Persist server state to disk."""
        try:
            with self.lock:
                # Serialize users
                user_path = os.path.join(self.persistence_dir, "users.pkl")
                with open(user_path, 'wb') as f:
                    pickle.dump(self.users, f)
                
                # Serialize messages
                messages_path = os.path.join(self.persistence_dir, "messages.pkl")
                with open(messages_path, 'wb') as f:
                    pickle.dump(dict(self.messages), f)
                
                # Serialize counter
                counter_path = os.path.join(self.persistence_dir, "counter.pkl")
                with open(counter_path, 'wb') as f:
                    pickle.dump(self.message_id_counter, f)
                    
                # Write server metadata
                metadata = {
                    "server_id": self.server_id,
                    "is_master": self.is_master,
                    "last_updated": time.time(),
                    "replica_servers": self.replica_servers
                }
                metadata_path = os.path.join(self.persistence_dir, "metadata.json")
                with open(metadata_path, 'w') as f:
                    json.dump(metadata, f)
                    
                logging.debug(f"Server {self.server_id} state persisted successfully")
        except Exception as e:
            logging.error(f"Error persisting state: {e}")

    def load_state(self):
        """Load server state from disk if available."""
        try:
            # Load users if file exists
            user_path = os.path.join(self.persistence_dir, "users.pkl")
            if os.path.exists(user_path):
                with open(user_path, 'rb') as f:
                    self.users = pickle.load(f)
            
            # Load messages if file exists
            messages_path = os.path.join(self.persistence_dir, "messages.pkl")
            if os.path.exists(messages_path):
                with open(messages_path, 'rb') as f:
                    messages_dict = pickle.load(f)
                    self.messages = defaultdict(list)
                    for username, msgs in messages_dict.items():
                        self.messages[username] = msgs
            
            # Load counter if file exists
            counter_path = os.path.join(self.persistence_dir, "counter.pkl")
            if os.path.exists(counter_path):
                with open(counter_path, 'rb') as f:
                    self.message_id_counter = pickle.load(f)
                    
            # Load metadata if file exists
            metadata_path = os.path.join(self.persistence_dir, "metadata.json")
            if os.path.exists(metadata_path):
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                    
                # Only restore replica_servers if none were provided
                if not self.replica_servers and "replica_servers" in metadata:
                    self.replica_servers = metadata["replica_servers"]
                    
            logging.info(f"Server {self.server_id} state loaded successfully")
        except Exception as e:
            logging.error(f"Error loading state: {e}")

    def connect_to_replicas(self):
        """Establish gRPC connections to all replica servers."""
        self.replica_stubs = {}
        for address in self.replica_servers:
            if address != self.address:  # Don't connect to self
                try:
                    channel = grpc.insecure_channel(address)
                    stub = rpc.ChatServerStub(channel)
                    self.replica_stubs[address] = stub
                    logging.info(f"Connected to replica at {address}")
                except Exception as e:
                    logging.error(f"Failed to connect to replica at {address}: {e}")

    def send_heartbeats(self):
        """Periodically send heartbeats to replica servers."""
        while True:
            if not self.is_master:
                # If not master, stop sending heartbeats
                return
                
            for address, stub in list(self.replica_stubs.items()):
                try:
                    # Create heartbeat message
                    request = chat.Heartbeat(
                        server_id=self.server_id,
                        timestamp=time.time(),
                        is_master=True,
                        message_id_counter=self.message_id_counter
                    )
                    
                    # Send heartbeat
                    response = stub.SendHeartbeat(request, timeout=2)
                    logging.debug(f"Heartbeat sent to {address}: {response.message}")
                except Exception as e:
                    logging.warning(f"Failed to send heartbeat to {address}: {e}")
                    # Remove failed replica
                    if address in self.replica_stubs:
                        del self.replica_stubs[address]
            
            time.sleep(self.heartbeat_interval)

    def replicate_operation(self, operation_name, request):
        """Replicate an operation to all replica servers.
        
        Args:
            operation_name (str): Name of the operation method to call
            request: The request to send to replicas
            
        Returns:
            list: List of successful replica addresses
        """
        if not self.is_master:
            return []
            
        successful_replicas = []
        for address, stub in list(self.replica_stubs.items()):
            try:
                operation = getattr(stub, operation_name)
                response = operation(request, timeout=5)
                successful_replicas.append(address)
                logging.debug(f"Operation {operation_name} replicated to {address}")
            except Exception as e:
                logging.warning(f"Failed to replicate {operation_name} to {address}: {e}")
                
        return successful_replicas

    def hash_password(self, password):
        """Hash a password using SHA-256."""
        import hashlib
        return hashlib.sha256(password.encode()).hexdigest()

    def validate_password(self, password):
        """Validate password strength."""
        import re
        if len(password) < 8:
            return False
        if not re.search(r"\d", password):
            return False
        if not re.search(r"[A-Z]", password):
            return False
        return True

    def get_unread_count(self, username):
        """Get the count of unread messages for a user."""
        return len([msg for msg in self.messages[username] if not msg["read"]])

    def ChatStream(self, request_iterator, context):
        """Create a bidirectional stream for sending real-time messages to the client."""
        # Extract client address for logging
        client_address = context.peer()
        
        # Get username from the first request
        try:
            first_request = next(request_iterator)
            username = first_request.username
            
            # Register this stream for the user
            with self.lock:
                if username not in self.active_users:  # Check if still logged in
                    context.cancel()
                    return
                self.active_streams.setdefault(username, []).append(context)
            logging.info(f"ChatStream connected for {username}")
                                
            while True:  # Persistent connection loop
                time.sleep(0.1)  # Prevent CPU spin
                with self.lock:
                    if username not in self.active_users:
                        context.cancel()
                        break
                    # Get messages that haven't been notified OR read
                    undelivered = [
                        msg for msg in self.messages[username]
                        if not msg.get("stream_notified") and not msg["read"]
                    ]

                    for msg in undelivered:
                        # Send notification WITHOUT marking as read
                        yield chat.Message(
                            id=msg["id"],
                            username=msg["from"],
                            to=username,
                            content=msg["content"],
                            timestamp=msg["timestamp"],
                            read=False,  # Maintain unread status
                            delivered_while_offline=msg["delivered_while_offline"]
                        )
                        msg["stream_notified"] = True  # Track notification

        except StopIteration:
            logging.warning(f"Client {username} disconnected")
        except Exception as e:
            if context.is_active():
                context.cancel()
            logging.error(f"Stream error: {e}")
        finally:
            with self.lock:
                if username:
                    # Cleanup stream registration
                    if context in self.active_streams.get(username, []):
                        self.active_streams[username].remove(context)
                    # Mark user offline if no active streams
                    if not self.active_streams.get(username):
                        del self.active_users[username]

    def SendHeartbeat(self, request, context):
        """Handle heartbeat messages from other servers."""
        sender_id = request.server_id
        sender_is_master = request.is_master
        
        # Update message ID counter if needed
        if sender_is_master and self.message_id_counter < request.message_id_counter:
            self.message_id_counter = request.message_id_counter
        
        # If sender is master and we think we're master, resolve conflict
        if sender_is_master and self.is_master:
            # Simple conflict resolution: highest server_id wins
            if sender_id > self.server_id:
                logging.warning(f"Master conflict detected. Yielding to server {sender_id}")
                self.is_master = False
                self.persist_state()
        
        # If we're told to become master
        if request.promote_to_master and not self.is_master:
            logging.info(f"Promoted to master by server {sender_id}")
            self.is_master = True
            
            # Start heartbeat thread
            self.heartbeat_thread = threading.Thread(target=self.send_heartbeats, daemon=True)
            self.heartbeat_thread.start()
            
            self.persist_state()
        
        return chat.Reply(error=False, message=f"Heartbeat received by server {self.server_id}")

    def SendSyncState(self, request, context):
        """Synchronize state with another server."""
        if not self.is_master and request.from_master:
            # We're a replica receiving state from the master
            try:
                # Deserialize state
                users = pickle.loads(request.users_data)
                messages = pickle.loads(request.messages_data)
                
                # Update local state
                with self.lock:
                    self.users = users
                    self.messages = defaultdict(list)
                    for username, msgs in messages.items():
                        self.messages[username] = msgs
                    self.message_id_counter = request.message_id_counter
                    
                # Persist updated state
                self.persist_state()
                
                logging.info(f"State synchronized from master {request.server_id}")
                return chat.Reply(error=False, message="State synchronized successfully")
            except Exception as e:
                logging.error(f"Error synchronizing state: {e}")
                return chat.Reply(error=True, message=f"State synchronization failed: {e}")
        elif self.is_master and not request.from_master:
            # We're the master and a replica is requesting our state
            try:
                with self.lock:
                    # Serialize state
                    users_data = pickle.dumps(self.users)
                    messages_data = pickle.dumps(dict(self.messages))
                    
                    # Create response with our state
                    response = chat.SyncState(
                        server_id=self.server_id,
                        from_master=True,
                        users_data=users_data,
                        messages_data=messages_data,
                        message_id_counter=self.message_id_counter,
                        timestamp=time.time()
                    )
                    
                return response
            except Exception as e:
                logging.error(f"Error preparing state for synchronization: {e}")
                return chat.Reply(error=True, message=f"Failed to prepare state: {e}")
        else:
            # Invalid synchronization request
            return chat.Reply(error=True, message="Invalid synchronization request")

    def SendCreateAccount(self, request, context):
        """Create a new user account."""
        client_address = context.peer()
        username = request.username
        password = request.password
        
        with self.lock:
            # Validate input
            if not username or not password:
                logging.warning(f"Failed account creation from {client_address}: Missing fields")
                return chat.Reply(error=True, message="Username and password required")
            elif not self.validate_password(password):
                logging.warning(f"Failed account creation from {client_address}: Weak password")
                return chat.Reply(
                    error=True,
                    message="Password must be at least 8 characters with 1 number and 1 uppercase letter"
                )
            elif username in self.users:
                logging.warning(f"Failed account creation from {client_address}: Username '{username}' already exists")
                return chat.Reply(error=True, message="Username already exists")
                
            # If not master, forward to master
            if not self.is_master:
                # TODO: Implement forwarding to master
                logging.warning(f"Non-master server received create account request")
                return chat.Reply(error=True, message="Server is not the master. Please reconnect to the master server.")
            
            # Create account
            self.users[username] = (self.hash_password(password), {})
            self.messages[username] = []
            
            # Persist changes
            self.persist_state()
            
            # If master, replicate to other servers
            self.replicate_operation("SendCreateAccount", request)
            
            logging.info(f"New account created: {username} from {client_address}")
            return chat.Reply(error=False, message="Account created successfully")

    def SendLogin(self, request, context):
        """Log in a user."""
        client_address = context.peer()
        username = request.username
        password = request.password
        
        with self.lock:
            # Validate credentials
            if username not in self.users:
                logging.warning(f"Failed login attempt from {client_address}: User '{username}' not found")
                return chat.Reply(error=True, message="User not found")
            elif self.users[username][0] != self.hash_password(password):
                logging.warning(f"Failed login attempt from {client_address}: Incorrect password for '{username}'")
                return chat.Reply(error=True, message="Invalid password")
            elif username in self.active_users:
                logging.warning(f"Failed login attempt from {client_address}: '{username}' already logged in")
                return chat.Reply(error=True, message="User already logged in")
                
            # If not master, forward to master
            if not self.is_master:
                # TODO: Implement forwarding to master
                logging.warning(f"Non-master server received login request")
                return chat.Reply(error=True, message="Server is not the master. Please reconnect to the master server.")
            
            # Process login
            self.active_users[username] = True
            unread_count = self.get_unread_count(username)
            
            # Persist changes
            self.persist_state()
            
            # If master, replicate to other servers
            self.replicate_operation("SendLogin", request)
            
            logging.info(f"User '{username}' logged in from {client_address}")
            
            # Include unread count in the reply message
            reply_message = f"Login successful. You have {unread_count} unread messages."
            return chat.Reply(error=False, message=reply_message)

    def SendLogout(self, request, context):
        """Log out a user."""
        username = request.username
        client_address = context.peer()
        
        with self.lock:
            # Validate user is logged in
            if username not in self.active_users:
                logging.warning(f"Failed logout attempt from {client_address}: User not logged in")
                return chat.Reply(error=True, message="Not logged in")
            
            # If not master, forward to master
            if not self.is_master:
                # TODO: Implement forwarding to master
                logging.warning(f"Non-master server received logout request")
                return chat.Reply(error=True, message="Server is not the master. Please reconnect to the master server.")
                
            # Process logout
            if username in self.active_streams:
                del self.active_streams[username]
            del self.active_users[username]
            
            # Persist changes
            self.persist_state()
            
            # If master, replicate to other servers
            self.replicate_operation("SendLogout", request)
            
            logging.info(f"User '{username}' logged out from {client_address}")
            return chat.Reply(error=False, message="Logged out successfully")

    def SendDeleteAccount(self, request, context):
        """Delete a user account."""
        username = request.username
        password = request.password
        client_address = context.peer()
        
        with self.lock:
            # Validate credentials
            if username not in self.users:
                logging.warning(f"Failed account deletion from {client_address}: User not found")
                return chat.Reply(error=True, message="User not found")
            elif self.users[username][0] != self.hash_password(password):
                logging.warning(f"Failed account deletion for {username} - Incorrect password")
                return chat.Reply(error=True, message="Invalid password")
                
            # If not master, forward to master
            if not self.is_master:
                # TODO: Implement forwarding to master
                logging.warning(f"Non-master server received delete account request")
                return chat.Reply(error=True, message="Server is not the master. Please reconnect to the master server.")
            
            # Delete account
            del self.users[username]
            del self.messages[username]
            
            if username in self.active_users:
                del self.active_users[username]
                
            # Persist changes
            self.persist_state()
            
            # If master, replicate to other servers
            self.replicate_operation("SendDeleteAccount", request)
            
            logging.info(f"Account deleted: {username} from {client_address}")
            return chat.Reply(error=False, message="Account deleted")

    def SendMessage(self, request, context):
        """Send a message to another user."""
        sender = request.username
        recipient = request.to
        content = request.content
        client_address = context.peer()
        
        with self.lock:
            # Validate user is logged in and recipient exists
            if sender not in self.active_users:
                logging.warning(f"Failed message send from {client_address}: User not logged in")
                return chat.Reply(error=True, message="Not logged in")
            elif recipient not in self.users:
                logging.warning(f"Message failed: '{recipient}' does not exist (from {sender})")
                return chat.Reply(error=True, message="Recipient not found")
                
            # If not master, forward to master
            if not self.is_master:
                # TODO: Implement forwarding to master
                logging.warning(f"Non-master server received send message request")
                return chat.Reply(error=True, message="Server is not the master. Please reconnect to the master server.")
            
            # Create message
            message = {
                "id": self.message_id_counter,
                "from": sender,
                "to": recipient,
                "content": content,
                "timestamp": time.time(),
                "read": False,
                "delivered_while_offline": recipient not in self.active_users
            }
            self.message_id_counter += 1
            self.messages[recipient].append(message)
            
            # Persist changes
            self.persist_state()
            
            # If master, replicate to other servers
            self.replicate_operation("SendMessage", request)
            
            # If recipient has active streams, notify them
            if recipient in self.active_streams and self.active_streams[recipient]:
                proto_message = chat.Message(
                    id=message["id"],
                    username=message["from"],
                    to=message["to"],
                    content=message["content"],
                    timestamp=message["timestamp"],
                    read=message["read"],
                    delivered_while_offline=message["delivered_while_offline"]
                )
                
                # Notify recipient
                for stream_context in self.active_streams[recipient]:
                    threading.Thread(
                        target=self.notify_user_async,
                        args=(recipient, proto_message, stream_context),
                        daemon=True
                    ).start()
            
            logging.info(f"Message sent from '{sender}' to '{recipient}'")
            return chat.Reply(error=False, message="Message sent")

    def notify_user_async(self, username, message, stream_context):
        """Notify a user asynchronously about a new message."""
        try:
            # In a real implementation, we would use the stream_context to send the message
            # However, gRPC streams are bidirectional but not random-access
            # The client will receive the message in the next poll of ChatStream
            pass
        except Exception as e:
            logging.error(f"Error notifying user {username}: {e}")

    def SendGetMessages(self, request, context):
        """Get messages for a user."""
        username = request.username
        count = request.count
        client_address = context.peer()
        
        with self.lock:
            # Validate user is logged in
            if username not in self.active_users:
                logging.warning(f"Failed get_messages request from {client_address}: User not logged in")
                return chat.MessageList(error=True, message="Not logged in")

            # Get read messages sorted by timestamp
            read_messages = sorted(
                [msg for msg in self.messages[username] if msg["read"]],
                key=lambda x: x["timestamp"],
                reverse=True
            )
            
            # Convert to proto messages
            proto_messages = [
                chat.Message(
                    id=m["id"],
                    username=m["from"],
                    to=username,
                    content=m["content"],
                    timestamp=m["timestamp"],
                    read=True,
                    delivered_while_offline=m["delivered_while_offline"]
                ) for m in read_messages
            ]
            
            return chat.MessageList(
                error=False,
                messages=proto_messages
            )

    def SendGetUndelivered(self, request, context):
        """Get unread messages for a user."""
        username = request.username
        count = request.count
        client_address = context.peer()

        with self.lock:
            # Validate user is logged in
            if username not in self.active_users:
                logging.warning(f"Failed get_undelivered request from {client_address}: User not logged in")
                return chat.MessageList(error=True, message="Not logged in")
            
            # Get unread messages and mark them as read
            unread = [msg for msg in self.messages[username] if not msg["read"]]
            unread_sorted = sorted(unread, key=lambda x: x["timestamp"], reverse=True)[:count]
            
            # Finalize read status and clean flags
            for msg in unread_sorted:
                msg["read"] = True
                if "stream_notified" in msg:
                    del msg["stream_notified"]  # Clean notification flag
                                
            # Convert to proto messages
            proto_messages = [
                chat.Message(
                    id=m["id"],
                    username=m["from"],
                    to=username,
                    content=m["content"],
                    timestamp=m["timestamp"],
                    read=True,
                    delivered_while_offline=m["delivered_while_offline"]
                ) for m in unread_sorted
            ]
            
            # Persist changes (messages marked as read)
            self.persist_state()
            
            # If master, replicate change to other servers
            if self.is_master:
                self.replicate_operation("SendGetUndelivered", request)
            
            return chat.MessageList(
                error=False,
                messages=proto_messages
            )
    
    def SendDeleteMessages(self, request, context):
        """Delete messages for a user."""
        username = request.username
        msg_ids = list(request.message_ids)
        client_address = context.peer()
        
        with self.lock:
            # Validate user is logged in
            if username not in self.active_users:
                logging.warning(f"Failed delete_messages request from {client_address}: User not logged in")
                return chat.Reply(error=True, message="Not logged in")
                
            # If not master, forward to master
            if not self.is_master:
                # TODO: Implement forwarding to master
                logging.warning(f"Non-master server received delete messages request")
                return chat.Reply(error=True, message="Server is not the master. Please reconnect to the master server.")
            
            # Delete messages
            self.messages[username] = [
                m for m in self.messages[username] if m["id"] not in msg_ids
            ]
            
            # Persist changes
            self.persist_state()
            
            # If master, replicate to other servers
            self.replicate_operation("SendDeleteMessages", request)
            
            logging.info(f"User '{username}' deleted {len(msg_ids)} messages")
            return chat.Reply(error=False, message=f"{len(msg_ids)} messages deleted")

    def SendListAccounts(self, request, context):
        """List user accounts matching a pattern."""
        username = request.username
        pattern = request.wildcard
        client_address = context.peer()
        
        # Ensure a valid pattern (default to "*")
        if not pattern:
            pattern = "*"
        elif not pattern.endswith("*"):
            pattern = pattern + "*"
        
        with self.lock:
            # Find matching users
            import fnmatch
            matches = []
            for user in self.users:
                if fnmatch.fnmatch(user.lower(), pattern.lower()):
                    matches.append(chat.User(
                        username=user,
                        status="online" if user in self.active_users else "offline"
                    ))
            
            logging.info(f"User list requested from {client_address}, found {len(matches)} users")
            return chat.UserList(
                error=False,
                message=f"Found {len(matches)} users",
                users=matches
            )

    def JoinCluster(self, request, context):
        """Handle a request from a new server to join the cluster."""
        new_server_id = request.server_id
        new_server_address = request.address
        
        with self.lock:
            # Only the master can add new servers
            if not self.is_master:
                return chat.Reply(error=True, message="Only the master server can add new servers to the cluster")
            
            # Check if server is already in the list
            if new_server_address in self.replica_servers:
                return chat.Reply(error=True, message="Server is already part of the cluster")
            
            # Add server to replica list
            self.replica_servers.append(new_server_address)
            
            # Connect to the new server
            try:
                channel = grpc.insecure_channel(new_server_address)
                stub = rpc.ChatServerStub(channel)
                self.replica_stubs[new_server_address] = stub
                
                # Sync state to the new server
                with self.lock:
                    # Serialize state
                    users_data = pickle.dumps(self.users)
                    messages_data = pickle.dumps(dict(self.messages))
                    
                    # Create sync state request
                    sync_request = chat.SyncState(
                        server_id=self.server_id,
                        from_master=True,
                        users_data=users_data,
                        messages_data=messages_data,
                        message_id_counter=self.message_id_counter,
                        timestamp=time.time()
                    )
                    
                    # Send state to new server
                    response = stub.SendSyncState(sync_request)
                    
                    if response.error:
                        logging.error(f"Failed to sync state with new server: {response.message}")
                        return chat.Reply(error=True, message=f"Failed to sync state with new server: {response.message}")
                
                # Persist updated replica list
                self.persist_state()
                
                # Notify all other replicas of the new server
                cluster_update = chat.ClusterUpdate(
                    server_id=self.server_id,
                    replica_servers=self.replica_servers
                )
                
                for address, stub in self.replica_stubs.items():
                    if address != new_server_address:  # Don't send to the new server
                        try:
                            stub.UpdateCluster(cluster_update)
                        except Exception as e:
                            logging.warning(f"Failed to notify {address} about new server: {e}")
                
                logging.info(f"New server {new_server_id} at {new_server_address} joined the cluster")
                return chat.Reply(error=False, message=f"Successfully joined the cluster as a replica")
            except Exception as e:
                logging.error(f"Error adding new server to cluster: {e}")
                # Remove from list if failed
                if new_server_address in self.replica_servers:
                    self.replica_servers.remove(new_server_address)
                return chat.Reply(error=True, message=f"Failed to add server to cluster: {e}")

    def UpdateCluster(self, request, context):
        """Update local cluster configuration based on master's information."""
        master_id = request.server_id
        replica_servers = request.replica_servers
        
        with self.lock:
            # Only accept cluster updates from the master
            if self.is_master:
                return chat.Reply(error=True, message="Master server received cluster update request")
            
            # Update replica list
            self.replica_servers = replica_servers
            
            # Reconnect to replicas
            self.connect_to_replicas()
            
            # Persist updated configuration
            self.persist_state()
            
            logging.info(f"Cluster configuration updated from master {master_id}")
            return chat.Reply(error=False, message="Cluster configuration updated")