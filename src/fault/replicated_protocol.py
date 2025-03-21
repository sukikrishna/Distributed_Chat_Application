import socket
import struct
import json
import time
import threading
from queue import Queue, Empty
import logging

class ReplicationProtocol:
    """Protocol for server-to-server communication in the replicated system.
    
    This implements the inter-server communication protocol for synchronizing
    state between servers, leader election, and fault tolerance.
    
    Attributes:
        CMD_SYNC (int): Command for state synchronization
        CMD_HEARTBEAT (int): Command for heartbeat messages
        CMD_LEADER_ELECTION (int): Command for leader election
        CMD_ADD_SERVER (int): Command to add new server to replication set
        CMD_STATE_TRANSFER (int): Command for full state transfer to new/recovering servers
    """
    
    # Command constants
    CMD_SYNC = 100           # Synchronize an operation across servers
    CMD_HEARTBEAT = 101      # Leader -> follower heartbeat
    CMD_LEADER_ELECTION = 102  # Initiate leader election
    CMD_ADD_SERVER = 103     # Add a new server to replication set
    CMD_STATE_TRANSFER = 104  # Transfer complete state to a server
    
    def __init__(self, config, custom_protocol):
        """Initialize the replication protocol.
        
        Args:
            config (ReplicationConfig): Replication configuration
            custom_protocol (CustomWireProtocol): The wire protocol for command encoding
        """
        self.config = config
        self.custom_protocol = custom_protocol
        self.server_sockets = {}  # Map of server_id -> socket
        self.lock = threading.Lock()
        self.sync_queue = Queue()  # Queue for operations to be synchronized
        self.is_running = False
        self.logger = logging.getLogger('replication')
        self.last_heartbeat_lock = threading.Lock()
        self.last_heartbeat = time.time() 
        # Set up logging
        handler = logging.FileHandler(f'replication_{config.server_id}.log')
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
    
    def start(self):
        """Start the replication protocol threads."""
        self.is_running = True
        
        # Start synchronization thread if leader
        if self.config.is_leader():
            threading.Thread(target=self._sync_thread, daemon=True).start()
            threading.Thread(target=self._heartbeat_thread, daemon=True).start()
    
    def stop(self):
        """Stop the replication protocol."""
        self.is_running = False
        
        # Close all server connections
        with self.lock:
            for sock in self.server_sockets.values():
                try:
                    sock.close()
                except:
                    pass
            self.server_sockets = {}
    
    # In replicated_protocol.py - Improved _connect_to_server method
    def _connect_to_server(self, host, port):
        """Connect to another server in the replication set.
        
        Args:
            host (str): Server hostname or IP
            port (int): Server port
            
        Returns:
            socket.socket: Connected socket or None if connection failed
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)  # 5 second timeout
            sock.connect((host, port))
            
            # Enable TCP keepalive to detect broken connections
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            
            # Set additional TCP keepalive parameters if on Linux
            if hasattr(socket, 'TCP_KEEPIDLE'):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
            if hasattr(socket, 'TCP_KEEPINTVL'):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
            if hasattr(socket, 'TCP_KEEPCNT'):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
                
            return sock
        except Exception as e:
            self.logger.error(f"Failed to connect to server {host}:{port}: {e}")
            return None
    
    def _get_server_socket(self, server_id):
        """Get a socket connection to a specific server.
        
        Args:
            server_id (int): Server ID
            
        Returns:
            socket.socket: Connected socket or None if connection failed
        """
        with self.lock:
            # Return existing connection if available
            if server_id in self.server_sockets:
                return self.server_sockets[server_id]
            
            # Find server in config
            for server in self.config.config["servers"]:
                if server["id"] == server_id:
                    sock = self._connect_to_server(server["host"], server["port"])
                    if sock:
                        self.server_sockets[server_id] = sock
                    return sock
        
        return None
    
    # In replicated_protocol.py - Fixed _send_message method
    def _send_message(self, sock, cmd, payload):
        """Send a message to another server.
        
        Args:
            sock (socket.socket): Socket to send message on
            cmd (int): Command type
            payload (dict): Message payload
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            serialized_payload = json.dumps(payload).encode('utf-8')
            message = struct.pack('!BBHI', 1, 0, cmd, len(serialized_payload) + 8) + serialized_payload
            sock.sendall(message)
            return True
        except (BrokenPipeError, ConnectionResetError, socket.timeout) as e:
            self.logger.error(f"Send failed (cmd={cmd}): {e}")
            try:
                sock.close()
            except:
                pass
            return False
        except Exception as e:
            self.logger.error(f"Unexpected send error: {e}")
            return False
    
    # In replicated_protocol.py - Fixed _receive_message method
    def _receive_message(self, sock):
        """Receive a message from another server.
        
        Args:
            sock (socket.socket): Socket to receive message from
            
        Returns:
            tuple: (cmd, payload) or (None, None) if error
        """
        try:
            # Read header
            header = sock.recv(8)
            if not header or len(header) < 8:
                return None, None
            
            # Parse header
            ver_major, ver_minor, cmd = struct.unpack('!BBH', header[:4])
            total_length = struct.unpack('!I', header[4:8])[0]
            
            # Read payload
            payload_length = total_length - 8
            if payload_length <= 0:
                return cmd, {}
                
            payload_data = b''
            bytes_received = 0
            
            # Read payload in chunks to handle larger messages
            while bytes_received < payload_length:
                chunk = sock.recv(min(4096, payload_length - bytes_received))
                if not chunk:
                    raise Exception("Connection closed while receiving payload")
                payload_data += chunk
                bytes_received += len(chunk)
            
            # Parse payload
            if payload_data:
                payload = json.loads(payload_data.decode('utf-8'))
            else:
                payload = {}
            
            return cmd, payload
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to decode JSON: {e}")
            return None, None
        except Exception as e:
            self.logger.error(f"Failed to receive message: {e}")
            return None, None
    
    def _sync_thread(self):
        """Background thread for synchronizing operations with followers."""
        self.logger.info("Starting synchronization thread")
        time.sleep(2)  # Wait for all followers to finish setup
        
        while self.is_running:
            try:
                # Get next operation to synchronize
                operation = self.sync_queue.get(timeout=1)
                
                # Synchronize with all followers
                servers = self.config.get_servers()
                for server_id, (host, port) in enumerate(servers):
                    sock = self._get_server_socket(server_id)
                    if sock:
                        if not self._send_message(sock, self.CMD_SYNC, operation):
                            # Connection failed, remove from active sockets
                            with self.lock:
                                if server_id in self.server_sockets:
                                    del self.server_sockets[server_id]
            except Empty:
                # No operations to sync, just continue
                pass
            except Exception as e:
                self.logger.error(f"Error in sync thread: {e}")
    
    def _heartbeat_thread(self):
        """Background thread for sending heartbeats to followers."""
        self.logger.info("Starting heartbeat thread")
        # Dictionary to track consecutive heartbeat failures per server_id
        heartbeat_failures = {}
        
        while self.is_running and self.config.is_leader():
            for server in self.config.config["servers"]:
                if server["id"] == self.config.server_id:
                    continue  # Skip self
                
                server_id = server["id"]
                try:
                    # Always create a fresh connection for each heartbeat
                    sock = self._connect_to_server(server["host"], server["port"])
                    if sock:
                        payload = {
                            "leader_id": self.config.server_id,
                            "timestamp": time.time()
                        }
                        if self._send_message(sock, self.CMD_HEARTBEAT, payload):
                            self.logger.debug(f"Heartbeat sent to Server {server_id}")
                            heartbeat_failures[server_id] = 0  # Reset failure count on success
                        else:
                            self.logger.warning(f"Failed to send heartbeat to Server {server_id}")
                            heartbeat_failures[server_id] = heartbeat_failures.get(server_id, 0) + 1
                        sock.close()
                    else:
                        self.logger.warning(f"Could not connect to Server {server_id} for heartbeat")
                        heartbeat_failures[server_id] = heartbeat_failures.get(server_id, 0) + 1
                except Exception as e:
                    self.logger.error(f"Error sending heartbeat to Server {server_id}: {e}")
                    heartbeat_failures[server_id] = heartbeat_failures.get(server_id, 0) + 1
            
            # Check if any server has failed to respond for 3 consecutive heartbeats
            for server in list(self.config.config["servers"]):
                sid = server["id"]
                if sid == self.config.server_id:
                    continue
                if heartbeat_failures.get(sid, 0) >= 3:
                    self.logger.warning(f"Removing server {sid} from configuration due to repeated heartbeat failures")
                    self.config.remove_server(sid)
                    # Remove from the failure tracker as well
                    heartbeat_failures.pop(sid, None)
            
            time.sleep(1)  # Heartbeat interval


    def sync_operation(self, operation):
        """Synchronize an operation with all followers.
        
        Args:
            operation (dict): Operation to synchronize
        """
        if self.config.is_leader():
            self.sync_queue.put(operation)
    
    def handle_sync(self, client_socket):
        """Handle a synchronization message from the leader.
        
        Args:
            client_socket (socket.socket): Socket connection to the leader
            
        Returns:
            dict: Operation to apply
        """
        cmd, payload = self._receive_message(client_socket)
        if cmd == self.CMD_SYNC and payload:
            return payload
        return None
    
    # In replicated_server.py - Fixed initiate_leader_election method
    def initiate_leader_election(self):
        """Initiate leader election if the current leader is unresponsive."""
        self.logger.info("Initiating leader election")
        
        # Gather all server IDs from the current configuration.
        server_ids = [s["id"] for s in self.config.config["servers"]]
        if not server_ids:
            self.logger.error("No servers in configuration")
            return

        # According to our rule, the server with the highest ID should become leader.
        highest_id = max(server_ids)
        
        if self.config.server_id < highest_id:
            # This server is not the highest.
            # It should try to contact the highest-id server (its candidate for leader)
            highest_server = next((s for s in self.config.config["servers"] if s["id"] == highest_id), None)
            if highest_server:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(3)
                    sock.connect((highest_server["host"], highest_server["port"]))
                    payload = {
                        "proposer_id": self.config.server_id,
                        "timestamp": time.time()
                    }
                    serialized = json.dumps(payload).encode('utf-8')
                    message = struct.pack('!BBHI', 1, 0, self.CMD_LEADER_ELECTION, len(serialized) + 8) + serialized
                    sock.sendall(message)
                    sock.close()
                    self.logger.info(f"Not leader (ID {self.config.server_id}); contacted candidate leader {highest_id}")
                except Exception as e:
                    self.logger.error(f"Failed to contact potential leader {highest_id}: {e}")
            else:
                self.logger.error("Highest server not found in configuration")
        else:
            # This server has the highest ID and should become leader.
            if not self.config.is_leader():
                self.logger.info(f"Server {self.config.server_id} becoming leader")
                self.config.promote_to_leader()
                # Start leader threads (sync and heartbeat)
                self.start()
                # Inform all other servers of the new leadership.
                for server in self.config.config["servers"]:
                    if server["id"] != self.config.server_id:
                        try:
                            # Create a fresh connection to send the election announcement.
                            sock = self._connect_to_server(server["host"], server["port"])
                            if sock:
                                payload = {
                                    "new_leader_id": self.config.server_id,
                                    "timestamp": time.time()
                                }
                                self._send_message(sock, self.CMD_LEADER_ELECTION, payload)
                                sock.close()
                                self.logger.info(f"Informed Server {server['id']} of new leader {self.config.server_id}")
                        except Exception as e:
                            self.logger.error(f"Error notifying server {server['id']}: {e}")

    
    def start_heartbeat_monitor(self):
        """Start monitoring heartbeats from the leader."""
        def delayed_start():
            time.sleep(2)  # Give time for state transfer + socket init
            self._monitor_heartbeat()

        threading.Thread(target=delayed_start, daemon=True).start()
    
    def _monitor_heartbeat(self):
        while self.is_running and not self.config.is_leader():
            with self.last_heartbeat_lock:
                time_since = time.time() - self.last_heartbeat
            if time_since > 5:
                self.logger.warning("No heartbeat received in 5 seconds — initiating leader election")
                self.initiate_leader_election()
                break
            time.sleep(1)

    def handle_heartbeat(self, payload):
        """Update timestamp for received heartbeat."""
        with self.last_heartbeat_lock:
            self.last_heartbeat = time.time()

    def handle_leader_election(self, client_socket):
        """Handle a leader election message.
        
        Args:
            client_socket (socket.socket): Socket connection to the sender
            
        Returns:
            bool: True if this server should become leader
        """
        cmd, payload = self._receive_message(client_socket)
        if cmd == self.CMD_LEADER_ELECTION and payload:
            if "new_leader_id" in payload and payload["new_leader_id"] != self.config.server_id:
                # Another server became leader
                self.config.leader = False
                self.config.config["leader_id"] = payload["new_leader_id"]
                self.config.save_config()
                self.logger.info(f"Server {payload['new_leader_id']} is now the leader")
                return False
            
            # Check if we should become leader
            highest_id = self.config.server_id
            for server in self.config.config["servers"]:
                if server["id"] > highest_id:
                    highest_id = server["id"]
            
            if self.config.server_id == highest_id:
                # We should become leader
                self.config.promote_to_leader()
                self.logger.info(f"Server {self.config.server_id} promoted to leader")
                return True
        
        return False
    
    def request_state_transfer(self, target_server_id):
        """Request full state transfer from another server.
        
        Args:
            target_server_id (int): ID of the server to request state from
            
        Returns:
            dict: Full server state or None if transfer failed
        """
        sock = self._get_server_socket(target_server_id)
        if not sock:
            self.logger.error(f"Failed to connect to server {target_server_id} for state transfer")
            return None
        
        # Request state transfer
        payload = {
            "server_id": self.config.server_id,
            "timestamp": time.time()
        }
        if not self._send_message(sock, self.CMD_STATE_TRANSFER, payload):
            self.logger.error(f"Failed to send state transfer request to server {target_server_id}")
            return None
        
        # Receive state
        cmd, payload = self._receive_message(sock)
        if cmd == self.CMD_STATE_TRANSFER and payload:
            return payload
        
        self.logger.error(f"Failed to receive state from server {target_server_id}")
        return None
    
    def handle_state_transfer(self, client_socket, server_state):
        """Handle a state transfer request from another server.
        
        Args:
            client_socket (socket.socket): Socket connection to the requester
            server_state (dict): Current server state to send
            
        Returns:
            bool: True if successful, False otherwise
        """
        cmd, payload = self._receive_message(client_socket)
        if cmd == self.CMD_STATE_TRANSFER and payload:
            # Send current state
            return self._send_message(client_socket, self.CMD_STATE_TRANSFER, server_state)
        
        return False
    
    def add_server(self, server_id, host, port):
        """Add a new server to the replication set and notify other servers.
        
        Args:
            server_id (int): ID of the new server
            host (str): Server hostname or IP
            port (int): Server port
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.config.is_leader():
            self.logger.error("Only the leader can add new servers")
            return False
        
        # Add server to configuration if not already there
        found = False
        for server in self.config.config["servers"]:
            if server["id"] == server_id:
                # Update existing server info
                server["host"] = host
                server["port"] = port
                found = True
                break
        
        if not found:
            # Add new server to configuration
            self.config.config["servers"].append({
                "id": server_id,
                "host": host,
                "port": port
            })
        
        # Save configuration
        self.config.save_config()
        
        # Notify all existing servers except the new one
        for server in self.config.config["servers"]:
            if server["id"] != server_id and server["id"] != self.config.server_id:
                try:
                    sock = self._get_server_socket(server["id"])
                    if sock:
                        payload = {
                            "new_server_id": server_id,
                            "new_server_host": host,
                            "new_server_port": port,
                            "timestamp": time.time()
                        }
                        self._send_message(sock, self.CMD_ADD_SERVER, payload)
                except Exception as e:
                    self.logger.error(f"Failed to notify server {server['id']} about new server: {e}")
        
        return True
    
    def handle_add_server(self, client_socket):
        """Handle an add server message from the leader.
        
        Args:
            client_socket (socket.socket): Socket connection to the leader
            
        Returns:
            tuple: (server_id, host, port) of the new server or None if error
        """
        cmd, payload = self._receive_message(client_socket)
        if cmd == self.CMD_ADD_SERVER and payload:
            server_id = payload.get("new_server_id")
            host = payload.get("new_server_host")
            port = payload.get("new_server_port")
            
            if server_id is None or host is None or port is None:
                self.logger.error("Invalid add server message: missing required fields")
                return None
            
            # Update local configuration
            found = False
            for server in self.config.config["servers"]:
                if server["id"] == server_id:
                    # Update existing server info
                    server["host"] = host
                    server["port"] = port
                    found = True
                    break
            
            if not found:
                # Add new server to configuration
                self.config.config["servers"].append({
                    "id": server_id,
                    "host": host,
                    "port": port
                })
            
            # Save configuration
            self.config.save_config()
            
            # Send acknowledgment
            response = {"success": True}
            self._send_message(client_socket, self.CMD_ADD_SERVER, response)
            
            return server_id, host, port
        
        return None