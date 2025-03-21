import json
import os
import socket

class ReplicationConfig:
    """Handles configuration for the replicated chat server system.
    
    Attributes:
        server_id (int): Unique identifier for this server
        leader (bool): Whether this server is the current leader
        servers (list): List of all server addresses in the format (host, port)
        config_file (str): Path to the replication configuration file
        data_dir (str): Directory to store server data and persistence files
    """
    
    def __init__(self, server_id=None):
        """Initialize the replication configuration.
        
        Args:
            server_id (int, optional): Unique identifier for this server. If None,
                                       a new ID will be assigned.
        """
        self.config_file = "replication_config.json"
        self.data_dir = "server_data"
        
        # Create data directory if it doesn't exist
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        
        # Default config values
        self.default_config = {
            "servers": [],
            "leader_id": 0
        }
        
        # Load existing config or initialize new one
        self.load_config()
        
        # Set server ID or get new one
        if server_id is None:
            if self.config["servers"]:
                self.server_id = max([s["id"] for s in self.config["servers"]]) + 1
            else:
                self.server_id = 0
        else:
            self.server_id = server_id
        
        # Leader status - initially False unless this is the specified leader
        self.leader = (self.server_id == self.config["leader_id"])
        
        # Get local host IP if not already in config
        self.host = self.get_local_ip()
    
    def load_config(self):
        """Load configuration from file."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    self.config = json.load(f)
            except Exception as e:
                print(f"Error reading config file: {e}")
                self.config = self.default_config.copy()
        else:
            self.config = self.default_config.copy()
    
    def save_config(self):
        """Save configuration to file."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Error writing config file: {e}")
    
    def get_local_ip(self):
        """Get the local machine's IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
    
    def get_servers(self):
        """Get a list of server addresses (host, port) excluding self."""
        return [(s["host"], s["port"]) for s in self.config["servers"] 
                if s["id"] != self.server_id]
    
    def get_all_servers(self):
        """Get a list of all server addresses (host, port) including self."""
        return [(s["host"], s["port"]) for s in self.config["servers"]]
    
    def is_leader(self):
        """Check if this server is the leader."""
        return self.leader
    
    def promote_to_leader(self):
        """Promote this server to leader."""
        self.leader = True
        self.config["leader_id"] = self.server_id
        self.save_config()
    
    def add_server(self, host, port):
        """Add a server to the replication set.
        
        Args:
            host (str): Server hostname or IP
            port (int): Server port
            
        Returns:
            int: ID of the added server
        """
        # Check if server already exists
        for server in self.config["servers"]:
            if server["host"] == host and server["port"] == port:
                return server["id"]
        
        # Add new server
        new_id = max([s["id"] for s in self.config["servers"]]) + 1 if self.config["servers"] else 0
        self.config["servers"].append({
            "id": new_id,
            "host": host,
            "port": port
        })
        self.save_config()
        return new_id
    
    def register_self(self, port):
        """Register this server in the configuration.
        
        Args:
            port (int): Port this server is running on
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Check if already registered
        for server in self.config["servers"]:
            if server["id"] == self.server_id:
                server["host"] = self.host
                server["port"] = port
                self.save_config()
                return True
        
        # Add new entry for this server
        self.config["servers"].append({
            "id": self.server_id,
            "host": self.host,
            "port": port
        })
        self.save_config()
        return True
    
    def remove_server(self, server_id):
        """Remove a server from the replication set.
        
        Args:
            server_id (int): ID of the server to remove
            
        Returns:
            bool: True if successful, False otherwise
        """
        for i, server in enumerate(self.config["servers"]):
            if server["id"] == server_id:
                del self.config["servers"][i]
                self.save_config()
                return True
        return False
    
    def get_data_file(self):
        """Get the path to this server's data file."""
        return os.path.join(self.data_dir, f"server_{self.server_id}.db")
    
    def __str__(self):
        return f"Server {self.server_id} ({'Leader' if self.leader else 'Follower'})"