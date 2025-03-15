import sys
import grpc
import chat_pb2 as chat
import chat_pb2_grpc as rpc

def add_replica(leader_address, new_replica_address):
    """Adds a new replica to the cluster.
    
    Args:
        leader_address (str): Address of the leader server
        new_replica_address (str): Address of the new replica
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Connect to leader
        channel = grpc.insecure_channel(leader_address)
        stub = rpc.ReplicaServiceStub(channel)
        
        # Send add replica request
        response = stub.AddReplica(chat.AddReplicaRequest(
            address=new_replica_address
        ))
        
        print(f"Response: {response.message}")
        return response.success
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 add_replica.py <leader_address> <new_replica_address>")
        print("Example: python3 add_replica.py localhost:50051 localhost:50054")
        sys.exit(1)
        
    leader_address = sys.argv[1]
    new_replica_address = sys.argv[2]
    
    add_replica(leader_address, new_replica_address)