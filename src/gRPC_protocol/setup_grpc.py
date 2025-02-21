#!/usr/bin/env python3
"""
Setup script to generate protobuf/gRPC code
"""
import os
import sys
import subprocess

def main():
    # Determine the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Path to the protocol buffer file
    proto_file = os.path.join(script_dir, "chat.proto")
    
    if not os.path.exists(proto_file):
        print(f"Error: Protocol buffer file not found at {proto_file}")
        return 1
    
    print("Generating gRPC Python code from protocol buffer definition...")
    
    try:
        # Change to the directory where the proto file is located
        os.chdir(script_dir)
        
        # Run the protoc compiler with the gRPC plugin
        cmd = [
            sys.executable, 
            "-m", 
            "grpc_tools.protoc",
            "-I.",
            f"--python_out=.",
            f"--grpc_python_out=.",
            "chat.proto"
        ]
        
        result = subprocess.run(cmd, check=True)
        
        if result.returncode == 0:
            print("Successfully generated gRPC code.")
            print("\nGenerated files:")
            print(f"- {os.path.join(script_dir, 'chat_pb2.py')}")
            print(f"- {os.path.join(script_dir, 'chat_pb2_grpc.py')}")
            
            print("\nTo run the server:")
            print(f"python {os.path.join(script_dir, 'grpc_server.py')}")
            
            print("\nTo run a client (in another terminal):")
            print(f"python {os.path.join(script_dir, 'grpc_client.py')} localhost")
            
            return 0
        else:
            print(f"Error: Protocol compiler failed with exit code {result.returncode}")
            return 1
            
    except subprocess.CalledProcessError as e:
        print(f"Error running protoc: {e}")
        print("\nMake sure you have the grpcio-tools package installed:")
        print("pip install grpcio-tools")
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())