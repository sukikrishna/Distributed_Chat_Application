import argparse
import subprocess
import os

# Define paths to the scripts
SRC_DIR = os.path.join(os.path.dirname(__file__), "src")

CUSTOM_CLIENT = os.path.join(SRC_DIR, "custom_protocol", "custom_client.py")
CUSTOM_SERVER = os.path.join(SRC_DIR, "custom_protocol", "custom_server.py")

JSON_CLIENT = os.path.join(SRC_DIR, "json_protocol", "json_client.py")
JSON_SERVER = os.path.join(SRC_DIR, "json_protocol", "json_server.py")


def main():
    """Parses command-line arguments and launches the appropriate chat client or server.

    The script allows users to select a wire protocol (`--json` or `--custom`), 
    specify whether to run as a client or server (`--mode`), and optionally set 
    an IP address (`--ip`) and port (`--port`).
    
    Raises:
        SystemExit: If the required `--ip` argument is missing in client mode.
    """
    parser = argparse.ArgumentParser(description="Run the appropriate chat application.")
    
    # Mutually exclusive group to enforce only one protocol selection
    protocol_group = parser.add_mutually_exclusive_group()
    protocol_group.add_argument("--custom", action="store_true", help="Use the custom wire protocol")
    protocol_group.add_argument("--json", action="store_true", help="Use the JSON wire protocol (default)")

    parser.add_argument("--mode", choices=["client", "server"], required=True, help="Specify mode: client or server")
    parser.add_argument("--ip", type=str, required=False, help="IP address for client (required for clients, optional for servers)")
    parser.add_argument("--port", type=int, help="Port number (optional, will be handled by client/server if omitted)")

    args = parser.parse_args()

    # Default to JSON if neither --custom nor --json is provided
    if not args.custom and not args.json:
        args.json = True

    # Require --ip for clients, but not for servers
    if args.mode == "client" and not args.ip:
        print("Error: --ip is required for client mode.")
        exit(1)

    # Determine the script to run
    if args.custom:
        script = CUSTOM_CLIENT if args.mode == "client" else CUSTOM_SERVER
    else:  # Default to JSON
        script = JSON_CLIENT if args.mode == "client" else JSON_SERVER

    # Construct command
    command = ["python3", script]

    # If running a client, require an IP and optionally add the port
    if args.mode == "client":
        command.append(args.ip)  # IP is mandatory for clients
        if args.port:
            command.append(str(args.port))  # Port is optional

    # If running a server, add port only if provided
    elif args.mode == "server" and args.port:
        command.append(str(args.port))

    subprocess.run(command)


if __name__ == "__main__":
    main()
