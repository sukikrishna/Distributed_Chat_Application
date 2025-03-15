#!/usr/bin/env python3
"""
Script to launch a full cluster of chat servers for development/testing.
This script will start multiple server instances with the specified configuration.
"""
import os
import sys
import json
import argparse
import subprocess
import time
import signal
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Get the directory of this script
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
root_dir = os.path.dirname(parent_dir)

def load_or_create_config(config_path=None):
    """Load or create cluster configuration."""
    if not config_path:
        config_path = os.path.join(root_dir, "config", "cluster_config.json")
    
    config_dir = os.path.dirname(config_path)
    os.makedirs(config_dir, exist_ok=True)
    
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    else:
        # Create default configuration
        config = {
            "servers": [
                {"id": "server1", "host": "127.0.0.1", "port": 50051, "is_master": True},
                {"id": "server2", "host": "127.0.0.1", "port": 50052, "is_master": False},
                {"id": "server3", "host": "127.0.0.1", "port": 50053, "is_master": False}
            ]
        }
        
        # Save default configuration
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
            
        return config

def start_server(server_info, config_path, python_path="python3"):
    """Start a server process."""
    server_script = os.path.join(current_dir, "server_launcher.py")
    cmd = [
        python_path,
        server_script,
        "--server-id", server_info["id"],
        "--host", server_info["host"],
        "--port", str(server_info["port"]),
        "--config", config_path
    ]
    
    if server_info.get("is_master", False):
        cmd.append("--is-master")
    
    # Create a log directory if it doesn't exist
    log_dir = os.path.join(root_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    # Log file for this server
    log_file = os.path.join(log_dir, f"server_{server_info['id']}.log")
    
    # Start the server process
    with open(log_file, 'a') as log:
        process = subprocess.Popen(
            cmd, 
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True
        )
    
    return process

def start_client(config_path, python_path="python3"):
    """Start a client process."""
    client_script = os.path.join(current_dir, "fault_tolerant_client.py")
    cmd = [
        python_path,
        client_script,
        "--config", config_path
    ]
    
    # Start the client process
    return subprocess.Popen(cmd)

def main():
    parser = argparse.ArgumentParser(description="Start a cluster of chat servers")
    parser.add_argument("--config", type=str, help="Path to cluster configuration file")
    parser.add_argument("--python", type=str, default="python3", help="Python executable to use")
    parser.add_argument("--client", action="store_true", help="Also start a client")
    parser.add_argument("--no-master", action="store_true", help="Don't start the master server")
    parser.add_argument("--only-master", action="store_true", help="Only start the master server")
    parser.add_argument("--specific-server", type=str, help="Start a specific server by ID")
    
    args = parser.parse_args()
    
    # Load configuration
    config_path = args.config or os.path.join(root_dir, "config", "cluster_config.json")
    config = load_or_create_config(config_path)
    
    # Track started processes
    processes = []
    
    try:
        # Start servers based on configuration and command line arguments
        for server in config["servers"]:
            # Skip servers based on arguments
            if args.specific_server and server["id"] != args.specific_server:
                continue
                
            if args.no_master and server.get("is_master", False):
                continue
                
            if args.only_master and not server.get("is_master", False):
                continue
            
            logging.info(f"Starting server {server['id']} ({server['host']}:{server['port']})")
            process = start_server(server, config_path, args.python)
            processes.append((server["id"], process))
            
            # Short delay to avoid port conflicts
            time.sleep(1)
        
        # Start client if requested
        if args.client:
            logging.info("Starting client")
            client_process = start_client(config_path, args.python)
            processes.append(("client", client_process))
        
        # Keep running until interrupted
        logging.info("All processes started. Press Ctrl+C to stop.")
        
        # Wait for processes to complete (which won't happen unless they crash)
        for name, process in processes:
            process.wait()
            
    except KeyboardInterrupt:
        logging.info("Received interrupt signal. Shutting down...")
    finally:
        # Clean up processes
        for name, process in processes:
            try:
                logging.info(f"Stopping {name}...")
                process.terminate()
                
                # Give process time to terminate gracefully
                for _ in range(5):  # 5 seconds timeout
                    if process.poll() is not None:
                        break
                    time.sleep(1)
                    
                if process.poll() is None:
                    logging.warning(f"{name} did not terminate gracefully, killing...")
                    process.kill()
            except Exception as e:
                logging.error(f"Error stopping {name}: {e}")
    
    logging.info("All processes stopped.")
    return 0

if __name__ == "__main__":
    sys.exit(main())