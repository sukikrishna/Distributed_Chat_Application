import grpc
import hashlib
import re
import os
import fnmatch
import time
import logging
import threading
import sys
from concurrent import futures
from collections import defaultdict

# Add the parent directory to sys.path to ensure we find our local modules
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from config import Config
import chat_pb2 as chat
import chat_pb2_grpc as rpc

# Ensure logs directory exists in the project root
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Set log file path
LOG_FILE = os.path.join(LOG_DIR, "grpc_server.log")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

class ChatServer(rpc.ChatServerServicer):
    """A gRPC-based chat server that handles client connections, user authentication, 
    and message exchange.

    Attributes:
        users (dict): Stores user credentials and settings.
        messages (defaultdict): Stores messages per user.
        active_users (dict): Tracks active user connections.
        message_id_counter (int): Counter for message IDs.
        lock (threading.Lock): Lock for thread-safe operations.
    """

    def __init__(self):
        """Initializes the chat server with configurations."""
        #Clear log file on server restart
        open(LOG_FILE, "w").close()

        self.config = Config()
        self.users = {}  # username -> (password_hash, settings)
        self.messages = defaultdict(list)  # username -> [messages]
        self.active_users = {}  # username -> connected (context)
        self.message_id_counter = 0
        self.lock = threading.Lock()
        self.active_streams = {}  # username -> list of stream contexts

    def hash_password(self, password):
        """Hashes a password using SHA-256.

        Args:
            password (str): Password to be hashed.

        Returns:
            str: Hashed password.
        """
        return hashlib.sha256(password.encode()).hexdigest()

    def validate_password(self, password):
        """Validates password strength.

        Args:
            password (str): Password to be validated.

        Returns:
            bool: True if password meets requirements, False otherwise.
        """
        if len(password) < 8:
            return False
        if not re.search(r"\d", password):
            return False
        if not re.search(r"[A-Z]", password):
            return False
        return True

    def get_unread_count(self, username):
        """Returns the count of unread messages for a user.

        Args:
            username (str): Username to check messages for.

        Returns:
            int: Number of unread messages.
        """
        return len([msg for msg in self.messages[username] if not msg["read"]])

    # The stream which will be used to send new messages to clients
    def ChatStream(self, request_iterator, context):
        """Creates a stream for sending real-time messages to the client.
        
        Args:
            request_iterator: Iterator of client requests.
            context: gRPC context.
            
        Yields:
            Message: New messages for the client.
        """
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
                        self.broadcast_user_list()  

    def SendCreateAccount(self, request, context):
        """Creates a new user account.
        
        Args:
            request: CreateAccount request.
            context: gRPC context.
            
        Returns:
            Reply: Operation result.
        """
        client_address = context.peer()
        username = request.username
        password = request.password
        
        with self.lock:
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
            else:
                self.users[username] = (self.hash_password(password), {})
                self.messages[username] = []
                logging.info(f"New account created: {username} from {client_address}")
                self.broadcast_user_list()
                return chat.Reply(error=False, message="Account created successfully")

    def SendLogin(self, request, context):
        """Logs in a user.
        
        Args:
            request: Login request.
            context: gRPC context.
            
        Returns:
            Reply: Operation result with unread count.
        """
        client_address = context.peer()
        username = request.username
        password = request.password
        
        with self.lock:
            if username not in self.users:
                logging.warning(f"Failed login attempt from {client_address}: User '{username}' not found")
                return chat.Reply(error=True, message="User not found")
            elif self.users[username][0] != self.hash_password(password):
                logging.warning(f"Failed login attempt from {client_address}: Incorrect password for '{username}'")
                return chat.Reply(error=True, message="Invalid password")
            elif username in self.active_users:
                logging.warning(f"Failed login attempt from {client_address}: '{username}' already logged in")
                return chat.Reply(error=True, message="User already logged in")
            else:
                self.active_users[username] = True
                unread_count = self.get_unread_count(username)
                logging.info(f"User '{username}' logged in from {client_address}")
                
                # Broadcast updated user list
                self.broadcast_user_list()
                
                # Include unread count in the reply message
                reply_message = f"Login successful. You have {unread_count} unread messages."
                return chat.Reply(error=False, message=reply_message)

    def SendLogout(self, request, context):
        """Logs out a user.
        
        Args:
            request: Logout request.
            context: gRPC context.
            
        Returns:
            Reply: Operation result.
        """
        username = request.username
        client_address = context.peer()
        
        with self.lock:
            if username in self.active_users:
                if username in self.active_streams:  
                    del self.active_streams[username]  
                del self.active_users[username] 
                logging.info(f"User '{username}' logged out from {client_address}")
                self.broadcast_user_list()
                return chat.Reply(error=False, message="Logged out successfully")
            else:
                logging.warning(f"Failed logout attempt from {client_address}: User not logged in")
                return chat.Reply(error=True, message="Not logged in")

    def SendDeleteAccount(self, request, context):
        """Deletes a user account.
        
        Args:
            request: DeleteAccount request.
            context: gRPC context.
            
        Returns:
            Reply: Operation result.
        """
        username = request.username
        password = request.password
        client_address = context.peer()
        
        with self.lock:
            if username not in self.users:
                logging.warning(f"Failed account deletion from {client_address}: User not found")
                return chat.Reply(error=True, message="User not found")
            elif self.users[username][0] != self.hash_password(password):
                logging.warning(f"Failed account deletion for {username} - Incorrect password")
                return chat.Reply(error=True, message="Invalid password")
            else:
                del self.users[username]
                del self.messages[username]
                
                if username in self.active_users:
                    del self.active_users[username]
                
                logging.info(f"Account deleted: {username} from {client_address}")
                self.broadcast_user_list()
                return chat.Reply(error=False, message="Account deleted")

    def SendMessage(self, request, context):
        """Sends a message to another user.
        
        Args:
            request: Message to send.
            context: gRPC context.
            
        Returns:
            Reply: Operation result.
        """
        sender = request.username
        recipient = request.to
        content = request.content
        client_address = context.peer()
        
        with self.lock:
            if sender not in self.active_users:
                logging.warning(f"Failed message send from {client_address}: User not logged in")
                return chat.Reply(error=True, message="Not logged in")
            elif recipient not in self.users:
                logging.warning(f"Message failed: '{recipient}' does not exist (from {sender})")
                return chat.Reply(error=True, message="Recipient not found")
            else:
                # Create the message
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
                
                # If recipient has active streams, send to them immediately
                if recipient in self.active_streams and self.active_streams[recipient]:
                    # Convert dict to protobuf message
                    proto_message = chat.Message(
                        id=message["id"],
                        username=message["from"],
                        to=message["to"],
                        content=message["content"],
                        timestamp=message["timestamp"],
                        read=message["read"],
                        delivered_while_offline=message["delivered_while_offline"]
                    )
                    
                    # Send message to all active streams for this user
                    for stream_context in self.active_streams[recipient]:
                        # This happens asynchronously in another thread
                        threading.Thread(
                            target=self.notify_user_async,
                            args=(recipient, proto_message, stream_context),
                            daemon=True
                        ).start()
                
                logging.info(f"Message sent from '{sender}' to '{recipient}'")
                return chat.Reply(error=False, message="Message sent")

    def notify_user_async(self, username, message, stream_context):
        """Notifies a user asynchronously about a new message.
        
        Args:
            username: Username to notify.
            message: Message to send.
            stream_context: Stream context.
        """
        try:
            # In a real implementation, we would use the stream_context to send the message
            # However, gRPC streams are bidirectional but not random-access
            # The client will receive the message in the next poll of ChatStream
            pass
        except Exception as e:
            logging.error(f"Error notifying user {username}: {e}")

    def SendGetMessages(self, request, context):
        """Gets messages for a user.
        
        Args:
            request: GetMessages request.
            context: gRPC context.
            
        Returns:
            MessageList: List of messages.
        """
        username = request.username
        count = request.count
        client_address = context.peer()
        
        with self.lock:
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
        """Gets unread messages for a user.
        
        Args:
            request: GetUndelivered request.
            context: gRPC context.
            
        Returns:
            MessageList: List of unread messages.
        """
        username = request.username
        count = request.count
        client_address = context.peer()

        with self.lock:  
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
            
            return chat.MessageList(  
                error=False,  
                messages=proto_messages  
            )  
    
    def SendDeleteMessages(self, request, context):
        """Deletes messages for a user.
        
        Args:
            request: DeleteMessages request.
            context: gRPC context.
            
        Returns:
            Reply: Operation result.
        """
        username = request.username
        msg_ids = list(request.message_ids)
        client_address = context.peer()
        
        with self.lock:
            if username not in self.active_users:
                logging.warning(f"Failed delete_messages request from {client_address}: User not logged in")
                return chat.Reply(error=True, message="Not logged in")
            else:
                # Keep only messages that are not in the list of IDs to delete
                self.messages[username] = [
                    m for m in self.messages[username] if m["id"] not in msg_ids
                ]
                
                logging.info(f"User '{username}' deleted {len(msg_ids)} messages")
                return chat.Reply(error=False, message=f"{len(msg_ids)} messages deleted")

    def SendListAccounts(self, request, context):
        """Lists user accounts matching a pattern.
        
        Args:
            request: ListAccounts request.
            context: gRPC context.
            
        Returns:
            UserList: List of users.
        """
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

    def broadcast_user_list(self):
        """Broadcasts the updated user list to all active clients through their streams.
        
        This is a helper method and not directly exposed as a gRPC method.
        """
        # This would normally be done through the ChatStream, but we'll just update
        # a global user list for now. In a real implementation, we would use a 
        # pub/sub system or similar to notify clients.
        # Since this is called with the lock held, it's thread-safe.
        pass

    def get_messages(self, username):
        """Retrieves read messages for a user.

        Args:
            username (str): Username to retrieve messages for.

        Returns:
            list: List of sorted read messages.
        """
        messages = self.messages[username]
        read_messages = [m for m in messages if m["read"]]
        return sorted(read_messages, key=lambda x: x["timestamp"], reverse=True)

    def get_unread_messages(self, username, count):
        """Retrieves unread messages for a user.

        Args:
            username (str): Username to retrieve messages for.
            count (int): Number of messages to retrieve.

        Returns:
            list: List of sorted unread messages.
        """
        messages = self.messages[username]
        unread_messages = [m for m in messages if not m["read"]]
        return sorted(unread_messages, key=lambda x: x["timestamp"], reverse=True)[:count]

def serve(host, port):
    """Starts the gRPC server.
    
    Args:
        host (str): Host to bind to.
        port (int): Port to bind to.
    """
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    rpc.add_ChatServerServicer_to_server(ChatServer(), server)
    
    try:
        # Attempt to find an available port
        while port < 65535:
            try:
                server.add_insecure_port(f"{host}:{port}")
                print(f"Server starting on {host}:{port}")
                
                # Update config with the port
                config = Config()
                config.update("port", port)
                
                break
            except:
                port += 1
        
        if port >= 65535:
            print("No available ports found.")
            return
            
        server.start()
        print("Server started. Use Ctrl+C to stop.")
        try:
            while True:
                time.sleep(60*60*24)  # Sleep for a day (or until interrupted)
        except KeyboardInterrupt:
            print("Stopping server...")
    finally:
        server.stop(0)  # Stop server with 0 seconds grace period

if __name__ == "__main__":
    config = Config()
    # Get host from config, or use default
    try:
        host = config.get("host")
    except:
        host = "[::]"  # Default to all interfaces
        
    # Get port from config, or use default
    try:
        port = config.get("port")
    except:
        port = 50051   # Default gRPC port
    
    serve(host, port)