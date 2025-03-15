#!/bin/bash
# Script to start all servers in the cluster

# Create necessary directories
mkdir -p data/server1 data/server2 data/server3 logs

# Start master server (server1)
echo "Starting master server (server1) on port 50051..."
python src/fault_tolerant/server_launcher.py --server-id server1 &
sleep 2

# Start replica servers (server2 and server3)
echo "Starting replica server (server2) on port 50052..."
python src/fault_tolerant/server_launcher.py --server-id server2 &
sleep 2

echo "Starting replica server (server3) on port 50053..."
python src/fault_tolerant/server_launcher.py --server-id server3 &

echo "All servers started. Use Ctrl+C to stop all servers."
wait