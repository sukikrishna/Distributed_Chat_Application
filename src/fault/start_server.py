import signal
import subprocess
import sys
import os
import argparse
import socket
import time

processes = []

def signal_handler(sig, frame):
    print("\nShutting down all servers...")
    for p in processes:
        try:
            p.terminate()
        except Exception as e:
            print(f"Failed to terminate process: {e}")
    for p in processes:
        try:
            p.wait()
        except Exception:
            pass
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

# In start_server.py - Improved connection handling for joining servers
def start_server(server_id, port=None, join=False, leader=None):
    cmd = [sys.executable, "replicated_server.py", "--id", str(server_id)]
    if port:
        cmd.extend(["--port", str(port)])
    if join:
        cmd.append("--join")
        if leader:
            cmd.extend(["--leader", leader])
    print(f"Starting server {server_id}...")
    
    # Use environment variable to stagger server startup
    if server_id > 0:
        os.environ["STARTUP_DELAY"] = str(server_id * 2)
    else:
        os.environ["STARTUP_DELAY"] = "0"
        
    p = subprocess.Popen(cmd, env=os.environ)
    processes.append(p)
    
    # Wait a bit longer for the first server to initialize properly
    if server_id == 0:
        time.sleep(4)
    else:
        time.sleep(2)

def start_cluster(num_servers=3, base_port=50000):
    # Start server 0 (leader) first
    start_server(0, base_port)
    print(f"Started leader server on port {base_port}")
    time.sleep(10)  # Allow more time for leader startup
    
    # Start all followers
    for i in range(1, num_servers):
        port = base_port + i
        start_server(i, port)
        print(f"Started follower server {i} on port {port}")
        time.sleep(5)  # Longer gap between server starts

def main():
    parser = argparse.ArgumentParser(description="Start Chat Server Cluster")
    parser.add_argument("--servers", type=int, default=3, help="Number of servers to start")
    parser.add_argument("--base-port", type=int, default=50000, help="Base port for the first server")
    parser.add_argument("--single", action="store_true", help="Start a single server only")
    parser.add_argument("--id", type=int, help="Server ID (with --single)")
    parser.add_argument("--port", type=int, help="Server port (with --single)")
    parser.add_argument("--join", action="store_true", help="Join existing cluster (with --single)")
    parser.add_argument("--leader", type=str, help="Leader host:port to join (with --single and --join)")
    args = parser.parse_args()

    if not os.path.exists("replicated_server.py"):
        print("Error: replicated_server.py not found in current directory")
        return

    if args.single:
        if args.id is None:
            print("Error: Must specify --id with --single")
            return
        start_server(args.id, args.port, args.join, args.leader)
    else:
        start_cluster(args.servers, args.base_port)

    # Keep the main process alive to handle signal interrupts
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(None, None)

if __name__ == "__main__":
    main()