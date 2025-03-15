#!/usr/bin/env python3
"""
Script to generate the Python code from the protocol buffer definition.
"""
import os
import sys
import subprocess
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

def main():
    # Get the directory of this script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Path to the protocol buffer definition file
    proto_file = os.path.join(current_dir, "chat_extended.proto")
    
    # Make sure the proto file exists
    if not os.path.exists(proto_file):
        logging.error(f"Protocol buffer file not found at {proto_file}")
        return 1
    
    logging.info(f"Generating gRPC code from {proto_file}")
    
    try:
        # Run the protoc compiler with the grpc plugin
        cmd = [
            sys.executable, 
            "-m", 
            "grpc_tools.protoc",
            "-I.",
            f"--python_out=.",
            f"--grpc_python_out=.",
            "chat_extended.proto"
        ]
        
        # Change to the directory where the proto file is located
        os.chdir(current_dir)
        
        # Run the command
        result = subprocess.run(cmd, check=True)
        
        if result.returncode == 0:
            logging.info("Successfully generated gRPC code")
            pb2_file = os.path.join(current_dir, "chat_extended_pb2.py")
            grpc_file = os.path.join(current_dir, "chat_extended_pb2_grpc.py")
            
            logging.info(f"Generated files:")
            logging.info(f"- {pb2_file}")
            logging.info(f"- {grpc_file}")
            
            # Fix imports in the generated files
            fix_imports(pb2_file)
            fix_imports(grpc_file)
            
            return 0
        else:
            logging.error(f"Protocol compiler failed with exit code {result.returncode}")
            return 1
            
    except subprocess.CalledProcessError as e:
        logging.error(f"Error running protoc: {e}")
        logging.error("Make sure you have the grpcio-tools package installed:")
        logging.error("pip install grpcio-tools")
        return 1
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return 1

def fix_imports(file_path):
    """Fix imports in generated files to use relative imports."""
    if not os.path.exists(file_path):
        logging.error(f"File not found: {file_path}")
        return
    
    # Read the file
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Fix imports
    if '_pb2_grpc.py' in file_path:
        # Fix import in the gRPC file
        content = content.replace(
            "import chat_extended_pb2 as chat__extended__pb2",
            "import chat_extended_pb2 as chat__extended__pb2"
        )
    
    # Write the file back
    with open(file_path, 'w') as f:
        f.write(content)
    
    logging.info(f"Fixed imports in {file_path}")

if __name__ == "__main__":
    sys.exit(main())