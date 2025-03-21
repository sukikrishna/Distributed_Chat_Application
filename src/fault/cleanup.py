#!/usr/bin/env python3
import os
import sys
import socket
import time
import subprocess
import argparse
import signal

def check_port(port):
    """Check if a port is in use.
    
    Args:
        port (int): Port number to check
        
    Returns:
        bool: True if port is in use, False otherwise
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    result = sock.connect_ex(('127.0.0.1', port))
    sock.close()
    return result == 0

def get_process_using_port(port):
    """Get the PID of the process using a port.
    
    Args:
        port (int): Port number to check
        
    Returns:
        int: PID of process using port, or None if not found
    """
    try:
        # Try Linux/macOS command
        output = subprocess.check_output(f"lsof -i :{port} -t", shell=True)
        return output.decode().strip()
    except subprocess.CalledProcessError:
        try:
            # Try Windows command
            output = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True)
            lines = output.decode().strip().split('\n')
            if lines:
                # Extract PID from last column
                return lines[0].strip().split()[-1]
        except:
            pass
    return None

def kill_process(pid):
    """Kill a process by PID.
    
    Args:
        pid (int): Process ID to kill
        
    Returns:
        bool: True if process was killed, False otherwise
    """
    try:
        if sys.platform.startswith('win'):
            subprocess.check_call(f"taskkill /F /PID {pid}", shell=True)
        else:
            os.kill(int(pid), signal.SIGKILL)
        return True
    except:
        return False

def remove_config_files():
    """Remove replication configuration files."""
    try:
        if os.path.exists("replication_config.json"):
            os.remove("replication_config.json")
            print("Removed replication_config.json")
    except Exception as e:
        print(f"Error removing config files: {e}")

def cleanup_ports(ports):
    """Clean up processes using specified ports.
    
    Args:
        ports (list): List of port numbers to clean up
    """
    print("Checking and cleaning up ports...")
    
    for port in ports:
        if check_port(port):
            print(f"Port {port} is in use")
            pid = get_process_using_port(port)
            if pid:
                print(f"Process {pid} is using port {port}")
                if kill_process(pid):
                    print(f"Killed process {pid}")
                else:
                    print(f"Failed to kill process {pid}")
            else:
                print(f"No process found using port {port}")
        else:
            print(f"Port {port} is not in use")

def kill_matching_processes(pattern):
    """Kill processes matching a pattern.
    
    Args:
        pattern (str): Pattern to match process names
    """
    try:
        if sys.platform.startswith('win'):
            # Windows
            output = subprocess.check_output(f'tasklist /FI "IMAGENAME eq {pattern}" /FO CSV', shell=True)
            lines = output.decode().strip().split('\n')[1:]  # Skip header
            for line in lines:
                if not line:
                    continue
                parts = line.strip('"').split('","')
                if len(parts) >= 2:
                    pid = parts[1]
                    print(f"Killing process {pid} ({parts[0]})")
                    kill_process(pid)
        else:
            # Linux/macOS
            output = subprocess.check_output(f"ps aux | grep {pattern}", shell=True)
            lines = output.decode().strip().split('\n')
            for line in lines:
                if "grep" in line:
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    pid = parts[1]
                    print(f"Killing process {pid} ({line[:60]}...)")
                    kill_process(pid)
    except Exception as e:
        print(f"Error killing processes: {e}")

def clean_all():
    """Clean up all related processes and files."""
    # Kill Python processes related to our server
    kill_matching_processes("python.*start_server.py")
    kill_matching_processes("python.*replicated_server.py")
    
    # Clean up specific ports
    cleanup_ports([50000, 50001, 50002, 50003])
    
    # Remove config files
    remove_config_files()
    
    # Wait a bit for sockets to close
    print("Waiting for sockets to close...")
    time.sleep(5)
    
    # Verify ports are free
    for port in [50000, 50001, 50002, 50003]:
        status = "in use" if check_port(port) else "free"
        print(f"Port {port} is now {status}")

def main():
    parser = argparse.ArgumentParser(description="Clean up server processes and ports")
    parser.add_argument("--port", type=int, help="Specific port to clean up")
    parser.add_argument("--all", action="store_true", help="Clean everything")
    
    args = parser.parse_args()
    
    if args.port:
        cleanup_ports([args.port])
    elif args.all:
        clean_all()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()