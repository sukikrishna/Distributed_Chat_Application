#!/usr/bin/env python3
"""
Launcher script for the fault-tolerant chat server.
This script starts a single server instance with the specified configuration.
"""
import os
import sys
import argparse
import grpc
import socket
import json
import logging
from concurrent import futures
import time

# Add the parent directory to sys.path to ensure we find our local modules
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)
sys.path.insert(0, os.path.dirname(parent_dir))  # For config

# Import our modules
# from fault_tolerant.replicated_server import ReplicatedChatServer
# sys.path.append(os.path.join(parent_dir, "gRPC_protocol"))
# import chat_pb2 as chat
# import chat_pb2_grpc as rpc

# Import our modules
from replicated_server import ReplicatedChatServer
import chat_extended_pb2 as chat
import chat_extended_pb2_grpc as rpc

def setup_logging(server_id):
    """Configure logging for the server."""
    log_dir = os.path.join(os.path.dirname(parent_dir), "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, f"server_{server_id}.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

def load_cluster_config(config_path=None):
    """Load cluster configuration from a JSON file."""
    if not config_path:
        config_path = os.path.join(os.path.dirname(parent_dir), "config", "cluster_config.json")
    
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        # Create default configuration
        config = {
            "servers": [
                {"id": "server1", "host": "127.0.0.1", "port": 50051, "is_master": True},
                {"id": "server2", "host": "127.0.0.1", "port": 50052, "is_master": False},
                {"id": "server3", "host": "127.0.0.1", "port": 50053, "is_master": False}
            ]
        }
        
        # Create config directory if it doesn't exist
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        # Save default configuration
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
            
        return config

def start_server(server_id, host, port, replica_addresses=None, is_master=False, persistence_dir=None):
    """Start a server with the specified configuration."""
    # Configure logging
    setup_logging(server_id)
    
    # Create gRPC server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    
    # Create server instance
    service = ReplicatedChatServer(
        server_id=server_id,
        host=host,
        port=port,
        replica_addresses=replica_addresses,
        persistence_dir=persistence_dir,
        is_master=is_master
    )
    
    # Register service
    rpc.add_ChatServerServicer_to_server(service, server)
    
    # Start listening
    server_address = f"{host}:{port}"
    server.add_insecure_port(server_address)
    server.start()
    
    logging.info(f"Server {server_id} started at {server_address}")
    logging.info(f"Role: {'MASTER' if is_master else 'REPLICA'}")
    if replica_addresses:
        logging.info(f"Connected to replicas: {replica_addresses}")
    
    try:
        while True:
            time.sleep(3600)  # Sleep for an hour (or until interrupted)
    except KeyboardInterrupt:
        logging.info(f"Server {server_id} shutting down...")
        server.stop(5)  # 5 seconds grace period for existing RPCs

def main():
    parser = argparse.ArgumentParser(description="Start a fault-tolerant chat server instance")
    parser.add_argument("--server-id", type=str, help="Server identifier")
    parser.add_argument("--host", type=str, help="Host address to bind to")
    parser.add_argument("--port", type=int, help="Port to bind to")
    parser.add_argument("--is-master", action="store_true", help="Start as master server")
    parser.add_argument("--config", type=str, help="Path to cluster configuration file")
    parser.add_argument("--data-dir", type=str, help="Path to data directory for persistence")
    parser.add_argument("--join", type=str, help="Master server address to join (e.g., host:port)")
    
    args = parser.parse_args()
    
    # Load cluster configuration
    cluster_config = load_cluster_config(args.config)
    
    # Determine which server to start
    if args.server_id:
        # Start specific server by ID
        server_info = None
        for server in cluster_config["servers"]:
            if server["id"] == args.server_id:
                server_info = server
                break
                
        if not server_info:
            logging.error(f"Server with ID {args.server_id} not found in configuration")
            return 1
            
        # Override configuration with command-line arguments
        host = args.host or server_info.get("host")
        port = args.port or server_info.get("port")
        is_master = args.is_master if args.is_master is not None else server_info.get("is_master", False)
    else:
        # Use command-line arguments
        if not args.host or not args.port:
            logging.error("Host and port must be specified if server-id is not provided")
            return 1
            
        host = args.host
        port = args.port
        is_master = args.is_master
        args.server_id = f"server_{port}"  # Generate server ID
    
    # Get replica addresses
    replica_addresses = []
    for server in cluster_config["servers"]:
        address = f"{server['host']}:{server['port']}"
        if server["id"] != args.server_id:  # Don't include self
            replica_addresses.append(address)
    
    # Start server
    data_dir = args.data_dir or os.path.join(os.path.dirname(parent_dir), "data", args.server_id)
    
    # If joining an existing cluster
    if args.join:
        is_master = False  # Joining servers always start as replicas
        logging.info(f"Joining existing cluster through master at {args.join}")
        
        # Connect to master to join the cluster
        try:
            channel = grpc.insecure_channel(args.join)
            stub = rpc.ChatServerStub(channel)
            
            # Send join request
            request = chat.JoinRequest(
                server_id=args.server_id,
                address=f"{host}:{port}"
            )
            
            response = stub.JoinCluster(request)
            if response.error:
                logging.error(f"Failed to join cluster: {response.message}")
                return 1
                
            logging.info(f"Successfully joined cluster: {response.message}")
        except Exception as e:
            logging.error(f"Error joining cluster: {e}")
            return 1
    
    # Start the server
    start_server(
        server_id=args.server_id,
        host=host,
        port=port,
        replica_addresses=replica_addresses,
        is_master=is_master,
        persistence_dir=data_dir
    )
    
    return 0

if __name__ == "__main__":
    sys.exit(main())