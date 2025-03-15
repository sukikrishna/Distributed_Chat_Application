import grpc
import hashlib
import re
import os
import fnmatch
import time
import logging
import threading
import sys
import pickle
import json
import socket
import random
from concurrent import futures
from collections import defaultdict
import chat_pb2 as chat
import chat_pb2_grpc as rpc

# Add the parent directory to sys.path to ensure we find our local modules
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from config import Config


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

class ReplicatedChatServer(rpc.ChatServerServicer):
    def __init__(self, server_id, replica_addresses=None):
        #Clear log file on server restart
        open(LOG_FILE, "w").close()

        self.config = Config()
        self.server_id = server_id
        self.data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"../../data/server_{server_id}")
        os.makedirs(self.data_dir, exist_ok=True)
        
        # State for replication
        self.is_leader = False
        self.leader_id = None
        self.term = 0
        self.voted_for = None
        self.replica_addresses = replica_addresses or []
        self.replica_stubs = {}
        self.election_timeout = random.uniform(150, 300) / 1000  # 150-300ms
        self.last_heartbeat = time.time()
        
        # Load persisted data or initialize
        self.load_state()
        
        # Other server state
        self.lock = threading.Lock()
        self.active_streams = {}  # username -> list of stream contexts
        
        # Start leader election and heartbeat threads
        threading.Thread(target=self.election_timer, daemon=True).start()
        threading.Thread(target=self.persist_state_periodically, daemon=True).start()
        
        # Connect to other replicas
        self.connect_to_replicas()

    def load_state(self):
        try:
            # Load users
            users_file = os.path.join(self.data_dir, "users.pkl")
            if os.path.exists(users_file):
                with open(users_file, "rb") as f:
                    self.users = pickle.load(f)
            else:
                self.users = {}
                
            # Load messages
            messages_file = os.path.join(self.data_dir, "messages.pkl")
            if os.path.exists(messages_file):
                with open(messages_file, "rb") as f:
                    self.messages = pickle.load(f)
            else:
                self.messages = defaultdict(list)
                
            # Load message counter
            counter_file = os.path.join(self.data_dir, "counter.txt")
            if os.path.exists(counter_file):
                with open(counter_file, "r") as f:
                    self.message_id_counter = int(f.read().strip())
            else:
                self.message_id_counter = 0

            # Load raft state
            raft_file = os.path.join(self.data_dir, "raft_state.json")
            if os.path.exists(raft_file) and os.path.getsize(raft_file) > 0:
                with open(raft_file, "r") as f:
                    raft_state = json.load(f)
                    self.term = raft_state.get("term", 0)
                    self.voted_for = raft_state.get("voted_for")
            else:
                self.term = 0
                self.voted_for = None

            # Initialize active users
            self.active_users = {}
                
            logging.info(f"Server {self.server_id} loaded persisted state")
        except Exception as e:
            logging.error(f"Error loading persisted state: {e}")
            self.users = {}
            self.messages = defaultdict(list)
            self.message_id_counter = 0
            self.active_users = {}
            self.term = 0
            self.voted_for = None
    
    def persist_state(self):
        try:
            # Save users
            with open(os.path.join(self.data_dir, "users.pkl"), "wb") as f:
                pickle.dump(self.users, f)
                
            # Save messages
            with open(os.path.join(self.data_dir, "messages.pkl"), "wb") as f:
                pickle.dump(self.messages, f)
                
            # Save counter
            with open(os.path.join(self.data_dir, "counter.txt"), "w") as f:
                f.write(str(self.message_id_counter))
                
            # Save raft state
            with open(os.path.join(self.data_dir, "raft_state.json"), "w") as f:
                json.dump({
                    "term": self.term,
                    "voted_for": self.voted_for
                }, f)
                
            logging.info(f"Server {self.server_id} persisted state")
        except Exception as e:
            logging.error(f"Error persisting state: {e}")
    
    def persist_state_periodically(self):
        while True:
            time.sleep(5)  # Persist every 5 seconds
            with self.lock:
                self.persist_state()
    
    def connect_to_replicas(self):
        for addr in self.replica_addresses:
            if addr:  # Skip empty addresses
                channel = grpc.insecure_channel(addr)
                self.replica_stubs[addr] = rpc.ReplicaServiceStub(channel)
        logging.info(f"Connected to {len(self.replica_stubs)} replicas")
    
    def election_timer(self):
        # Wait 10 seconds on startup to allow all replicas to spin up
        time.sleep(10)
        while True:
            time.sleep(0.05)  # Check every 50ms
            
            if self.is_leader:
                self.send_heartbeats()
                continue
                
            # Check if election timeout has elapsed
            if time.time() - self.last_heartbeat > self.election_timeout:
                self.start_election()

    def start_election(self):
        with self.lock:
            self.term += 1
            self.voted_for = self.server_id
            self.leader_id = None
            self.persist_state()  # Persist the new term and vote
            
            logging.info(f"Starting election for term {self.term}")
            votes_received = 1  # Vote for self

            # Request votes from all replicas with a timeout
            for addr, stub in self.replica_stubs.items():
                try:
                    response = stub.RequestVote(
                        chat.VoteRequest(term=self.term, candidate_id=self.server_id),
                        timeout=1  # 1 second timeout
                    )
                    logging.info(f"Received vote from {addr}: {response.vote_granted}")
                    if response.vote_granted:
                        votes_received += 1
                except Exception as e:
                    logging.error(f"Error requesting vote from {addr}: {e}")

            logging.info(f"Total votes received: {votes_received}")

            # Check if we have a majority (including self)
            if votes_received > (len(self.replica_stubs) + 1) / 2:
                self.is_leader = True
                self.leader_id = self.server_id
                # Log and print which server won the election
                win_message = f"Server {self.server_id} won election for term {self.term} and is now leader."
                logging.info(win_message)
                print(win_message)
                self.send_heartbeats()
            else:
                logging.info(f"Lost election for term {self.term}")
                # Delay before the next election attempt to avoid rapid cycling
                time.sleep(0.5)
                self.reset_election_timer()

    
    def reset_election_timer(self):
        self.last_heartbeat = time.time()
        self.election_timeout = random.uniform(150, 300) / 1000  # 150-300ms
    
    def send_heartbeats(self):
        if not self.is_leader:
            return
            
        for addr, stub in self.replica_stubs.items():
            try:
                response = stub.AppendEntries(chat.AppendEntriesRequest(
                    term=self.term,
                    leader_id=self.server_id
                ))
                
                if response.term > self.term:
                    with self.lock:
                        self.term = response.term
                        self.is_leader = False
                        self.voted_for = None
                        self.persist_state()
                        self.reset_election_timer()
                        break
            except Exception as e:
                logging.error(f"Error sending heartbeat to {addr}: {e}")
                
        # Schedule next heartbeat in 50ms
        threading.Timer(0.05, self.send_heartbeats).start()
    
    def replicate_operation(self, operation_type, data):
        """Replicates an operation to all replicas"""
        if not self.is_leader:
            return False
            
        success_count = 1  # Count self
        
        for addr, stub in self.replica_stubs.items():
            try:
                response = stub.ReplicateOperation(chat.ReplicateRequest(
                    term=self.term,
                    leader_id=self.server_id,
                    operation_type=operation_type,
                    operation_data=json.dumps(data)
                ))
                
                if response.success:
                    success_count += 1
            except Exception as e:
                logging.error(f"Error replicating to {addr}: {e}")
        
        # Operation is successful if majority of replicas acknowledge
        return success_count > (len(self.replica_stubs) + 1) / 2
    
    def apply_operation(self, operation_type, data):
        """Applies an operation locally"""
        try:
            data_dict = json.loads(data) if isinstance(data, str) else data
            
            if operation_type == "CREATE_USER":
                username = data_dict["username"]
                password_hash = data_dict["password_hash"]
                self.users[username] = (password_hash, {})
                self.messages[username] = []
                
            elif operation_type == "DELETE_USER":
                username = data_dict["username"]
                if username in self.users:
                    del self.users[username]
                if username in self.messages:
                    del self.messages[username]
                if username in self.active_users:
                    del self.active_users[username]
                    
            elif operation_type == "SEND_MESSAGE":
                message = data_dict
                self.message_id_counter = max(self.message_id_counter, message["id"] + 1)
                self.messages[message["to"]].append(message)
                
            elif operation_type == "DELETE_MESSAGES":
                username = data_dict["username"]
                msg_ids = data_dict["message_ids"]
                if username in self.messages:
                    self.messages[username] = [
                        m for m in self.messages[username] if m["id"] not in msg_ids
                    ]
                    
            elif operation_type == "MARK_READ":
                username = data_dict["username"]
                msg_ids = data_dict["message_ids"]
                if username in self.messages:
                    for msg in self.messages[username]:
                        if msg["id"] in msg_ids:
                            msg["read"] = True
                            if "stream_notified" in msg:
                                del msg["stream_notified"]
            
            # Persist the changes
            self.persist_state()
            return True
        except Exception as e:
            logging.error(f"Error applying operation {operation_type}: {e}")
            return False

    # gRPC methods for replica communication
    def RequestVote(self, request, context):
        with self.lock:
            logging.info(f"Received RequestVote from {request.candidate_id} for term {request.term}")
            if request.term < self.term:
                logging.info(f"Rejecting vote for {request.candidate_id} because term {request.term} < {self.term}")
                return chat.VoteResponse(term=self.term, vote_granted=False)
                    
            if request.term > self.term:
                self.term = request.term
                self.is_leader = False
                self.voted_for = None
                self.persist_state()
                    
            if (self.voted_for is None or self.voted_for == request.candidate_id) and request.term >= self.term:
                self.voted_for = request.candidate_id
                self.term = request.term
                self.persist_state()
                self.reset_election_timer()
                logging.info(f"Granting vote to {request.candidate_id} for term {self.term}")
                return chat.VoteResponse(term=self.term, vote_granted=True)
                
            logging.info(f"Not granting vote to {request.candidate_id}")
            return chat.VoteResponse(term=self.term, vote_granted=False)

    
    def AppendEntries(self, request, context):
        with self.lock:
            if request.term < self.term:
                return chat.AppendEntriesResponse(term=self.term, success=False)
                
            # Valid heartbeat from current leader
            self.reset_election_timer()
            
            if request.term > self.term:
                self.term = request.term
                self.is_leader = False
                self.voted_for = None
                self.persist_state()
                
            self.leader_id = request.leader_id
            
            return chat.AppendEntriesResponse(term=self.term, success=True)
    
    def ReplicateOperation(self, request, context):
        with self.lock:
            if request.term < self.term:
                return chat.ReplicateResponse(term=self.term, success=False)
                
            # Update term if needed
            if request.term > self.term:
                self.term = request.term
                self.is_leader = False
                self.voted_for = None
                self.persist_state()
                
            # Reset election timeout
            self.reset_election_timer()
            self.leader_id = request.leader_id
            
            # Apply the operation
            success = self.apply_operation(request.operation_type, request.operation_data)
            
            return chat.ReplicateResponse(term=self.term, success=success)
    
    def AddReplica(self, request, context):
        with self.lock:
            if not self.is_leader:
                return chat.AddReplicaResponse(success=False, message="Not the leader")
                
            # Add the new replica
            replica_address = request.address
            if replica_address not in self.replica_addresses:
                self.replica_addresses.append(replica_address)
                channel = grpc.insecure_channel(replica_address)
                self.replica_stubs[replica_address] = rpc.ReplicaServiceStub(channel)
                logging.info(f"Added new replica at {replica_address}")
                
                # Transfer state
                try:
                    state_data = {
                        "users": self.users,
                        "messages": dict(self.messages),
                        "message_id_counter": self.message_id_counter,
                        "term": self.term
                    }
                    
                    serialized_state = pickle.dumps(state_data)
                    chunks = []
                    
                    # Split into 1MB chunks
                    chunk_size = 1024 * 1024
                    for i in range(0, len(serialized_state), chunk_size):
                        chunks.append(serialized_state[i:i+chunk_size])
                    
                    # Send initial chunk count
                    self.replica_stubs[replica_address].InitStateTransfer(
                        chat.StateTransferInit(chunk_count=len(chunks))
                    )
                    
                    # Send each chunk
                    for i, chunk in enumerate(chunks):
                        self.replica_stubs[replica_address].TransferState(
                            chat.StateChunk(
                                chunk_index=i,
                                data=chunk
                            )
                        )
                        
                    return chat.AddReplicaResponse(success=True, message="Replica added and state transferred")
                except Exception as e:
                    logging.error(f"Error transferring state to new replica: {e}")
                    return chat.AddReplicaResponse(success=False, message=f"Error: {str(e)}")
            else:
                return chat.AddReplicaResponse(success=False, message="Replica already exists")
    
    def InitStateTransfer(self, request, context):
        self.state_chunks = [None] * request.chunk_count
        self.chunks_received = 0
        return chat.StateTransferResponse(success=True)
    
    def TransferState(self, request, context):
        if not hasattr(self, 'state_chunks'):
            return chat.StateTransferResponse(success=False)
            
        self.state_chunks[request.chunk_index] = request.data
        self.chunks_received += 1
        
        # Check if all chunks received
        if self.chunks_received == len(self.state_chunks):
            try:
                # Combine chunks and deserialize
                serialized_state = b''.join(self.state_chunks)
                state_data = pickle.loads(serialized_state)
                
                with self.lock:
                    self.users = state_data["users"]
                    self.messages = defaultdict(list)
                    for username, msgs in state_data["messages"].items():
                        self.messages[username] = msgs
                    self.message_id_counter = state_data["message_id_counter"]
                    self.term = state_data["term"]
                    self.persist_state()
                    
                logging.info("State transfer completed successfully")
                del self.state_chunks
                del self.chunks_received
            except Exception as e:
                logging.error(f"Error applying transferred state: {e}")
                return chat.StateTransferResponse(success=False)
                
        return chat.StateTransferResponse(success=True)

    def hash_password(self, password):
        """No change to hash_password"""
        return hashlib.sha256(password.encode()).hexdigest()

    def validate_password(self, password):
        """No change to validate_password"""
        if len(password) < 8:
            return False
        if not re.search(r"\d", password):
            return False
        if not re.search(r"[A-Z]", password):
            return False
        return True

    def get_unread_count(self, username):
        """No change to get_unread_count"""
        return len([msg for msg in self.messages[username] if not msg["read"]])

    def ChatStream(self, request_iterator, context):
        """No change to ChatStream"""
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

    def SendCreateAccount(self, request, context):
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
                password_hash = self.hash_password(password)
                
                # If leader, replicate then apply
                if self.is_leader:
                    data = {
                        "username": username,
                        "password_hash": password_hash
                    }
                    
                    if self.replicate_operation("CREATE_USER", data):
                        self.apply_operation("CREATE_USER", data)
                        logging.info(f"New account created: {username} from {client_address}")
                        return chat.Reply(error=False, message="Account created successfully")
                    else:
                        return chat.Reply(error=True, message="Failed to replicate operation")
                else:
                    # Forward to leader if known
                    if self.leader_id is not None and self.leader_id != self.server_id:
                        for addr, stub in self.replica_stubs.items():
                            try:
                                response = stub.SendCreateAccount(request)
                                return response
                            except Exception as e:
                                continue
                    
                    return chat.Reply(error=True, message="Operation failed - no leader available")

    def SendLogin(self, request, context):
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
                
                # Include unread count in the reply message
                reply_message = f"Login successful. You have {unread_count} unread messages."
                return chat.Reply(error=False, message=reply_message)

    def SendLogout(self, request, context):
        """No change to SendLogout"""
        username = request.username
        client_address = context.peer()
        
        with self.lock:
            if username in self.active_users:
                if username in self.active_streams:  
                    del self.active_streams[username]  
                del self.active_users[username] 
                logging.info(f"User '{username}' logged out from {client_address}")
                return chat.Reply(error=False, message="Logged out successfully")
            else:
                logging.warning(f"Failed logout attempt from {client_address}: User not logged in")
                return chat.Reply(error=True, message="Not logged in")

    def SendDeleteAccount(self, request, context):
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
                # If leader, replicate then apply
                if self.is_leader:
                    data = {"username": username}
                    
                    if self.replicate_operation("DELETE_USER", data):
                        self.apply_operation("DELETE_USER", data)
                        logging.info(f"Account deleted: {username} from {client_address}")
                        return chat.Reply(error=False, message="Account deleted")
                    else:
                        return chat.Reply(error=True, message="Failed to replicate operation")
                else:
                    # Forward to leader if known
                    if self.leader_id is not None and self.leader_id != self.server_id:
                        for addr, stub in self.replica_stubs.items():
                            try:
                                response = stub.SendDeleteAccount(request)
                                return response
                            except Exception as e:
                                continue
                    
                    return chat.Reply(error=True, message="Operation failed - no leader available")

    def SendMessage(self, request, context):
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
                
                # If leader, replicate then apply
                if self.is_leader:
                    if self.replicate_operation("SEND_MESSAGE", message):
                        self.message_id_counter += 1
                        self.messages[recipient].append(message)
                        self.persist_state()
                        
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
                    else:
                        return chat.Reply(error=True, message="Failed to replicate message")
                else:
                    # Forward to leader if known
                    if self.leader_id is not None and self.leader_id != self.server_id:
                        for addr, stub in self.replica_stubs.items():
                            try:
                                response = stub.SendMessage(request)
                                return response
                            except Exception as e:
                                continue
                    
                    return chat.Reply(error=True, message="Operation failed - no leader available")

    def notify_user_async(self, username, message, stream_context):
        """No change to notify_user_async"""
        try:
            # In a real implementation, we would use the stream_context to send the message
            # However, gRPC streams are bidirectional but not random-access
            # The client will receive the message in the next poll of ChatStream
            pass
        except Exception as e:
            logging.error(f"Error notifying user {username}: {e}")

    def SendGetMessages(self, request, context):
        """No change to SendGetMessages"""
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
            
            if unread_sorted:
                # When marking messages as read, replicate the operation if leader
                msg_ids = [msg["id"] for msg in unread_sorted]
                
                if self.is_leader:
                    data = {
                        "username": username,
                        "message_ids": msg_ids
                    }
                    
                    # Replicate the read status
                    self.replicate_operation("MARK_READ", data)
                    
                # Finalize read status and clean flags  
                for msg in unread_sorted:  
                    msg["read"] = True  
                    if "stream_notified" in msg:  
                        del msg["stream_notified"]  # Clean notification flag  
                
                self.persist_state()  # Make sure read status is persisted
                                
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
        username = request.username
        msg_ids = list(request.message_ids)
        client_address = context.peer()
        
        with self.lock:
            if username not in self.active_users:
                logging.warning(f"Failed delete_messages request from {client_address}: User not logged in")
                return chat.Reply(error=True, message="Not logged in")
            else:
                # If leader, replicate then apply
                if self.is_leader:
                    data = {
                        "username": username,
                        "message_ids": msg_ids
                    }
                    
                    if self.replicate_operation("DELETE_MESSAGES", data):
                        # Keep only messages that are not in the list of IDs to delete
                        self.messages[username] = [
                            m for m in self.messages[username] if m["id"] not in msg_ids
                        ]
                        self.persist_state()
                        
                        logging.info(f"User '{username}' deleted {len(msg_ids)} messages")
                        return chat.Reply(error=False, message=f"{len(msg_ids)} messages deleted")
                    else:
                        return chat.Reply(error=True, message="Failed to replicate operation")
                else:
                    # Forward to leader if known
                    if self.leader_id is not None and self.leader_id != self.server_id:
                        for addr, stub in self.replica_stubs.items():
                            try:
                                response = stub.SendDeleteMessages(request)
                                return response
                            except Exception as e:
                                continue
                    
                    return chat.Reply(error=True, message="Operation failed - no leader available")

    def SendListAccounts(self, request, context):
        """No change to SendListAccounts"""
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

    def get_messages(self, username):
        """No change to get_messages"""
        messages = self.messages[username]
        read_messages = [m for m in messages if m["read"]]
        return sorted(read_messages, key=lambda x: x["timestamp"], reverse=True)

    def get_unread_messages(self, username, count):
        """No change to get_unread_messages"""
        messages = self.messages[username]
        unread_messages = [m for m in messages if not m["read"]]
        return sorted(unread_messages, key=lambda x: x["timestamp"], reverse=True)[:count]
    


def start_server(server_id, replica_addresses, host, port):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    chat_server = ReplicatedChatServer(server_id, replica_addresses)
    rpc.add_ChatServerServicer_to_server(chat_server, server)
    rpc.add_ReplicaServiceServicer_to_server(chat_server, server)
    
    # Attempt to bind to the specified port
    while port < 65535:
        bound_port = server.add_insecure_port(f"{host}:{port}")
        if bound_port == 0:
            print(f"Port {port} unavailable, trying next port.")
            port += 1
        else:
            print(f"Server {server_id} starting on {host}:{bound_port}")
            break

    if port >= 65535:
        print("No available ports found.")
        return
            
    server.start()
    print(f"Server {server_id} started. Use Ctrl+C to stop.")
    
    try:
        while True:
            time.sleep(60*60*24)  # Sleep for a day (or until interrupted)
    except KeyboardInterrupt:
        print("Stopping server...")
    finally:
        server.stop(0)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 start_server.py <server_id> [replica_addresses]")
        print("Example: python3 start_server.py 1 localhost:50052,localhost:50053")
        sys.exit(1)
        
    server_id = sys.argv[1]
    replica_addresses = []
    
    if len(sys.argv) > 2:
        replica_addresses = sys.argv[2].split(',')
    
    config = Config()
    
    # Get host from config, or use default
    try:
        host = config.get("host")
    except:
        host = "localhost"  # Change default to "localhost" for easier local connection

    # Get base port from config, or use default
    try:
        base_port = config.get("port")
    except:
        base_port = 50051   # Default gRPC port
    
    # Derive port from server_id for easy testing
    port = base_port + int(server_id)
    
    start_server(server_id, replica_addresses, host, port)