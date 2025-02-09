import socket
from threading import Thread

class Server:
    Clients = []

    # Create a TCP socket over IPv4. Accept at max 5 connections.
    def __init__(self, HOST, PORT):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind((HOST, PORT))
        self.socket.listen(5)
        print("Server waiting for connection...")

    # Listen for connections on the main thread. When a connection
    # is received, create a new thread to handle it and add the client
    # to the list of clients.
    def listen(self):
        while True:
            client_socket, address = self.socket.accept()
            print(f"Connection from: {address}")

            # The first message will be the username
            client_name = client_socket.recv(1024).decode().strip()
            client = {"client_name": client_name, "client_socket": client_socket}

            # Broadcast that the new client has connected
            self.broadcast_message(client_name, f"{client_name} has joined the chat!")

            Server.Clients.append(client)
            Thread(target=self.handle_new_client, args=(client,), daemon=True).start()

    def handle_new_client(self, client):
        client_name = client["client_name"]
        client_socket = client["client_socket"]
        
        while True:
            try:
                # Listen for messages and broadcast them to all clients.
                client_message = client_socket.recv(1024).decode().strip()
                
                # If the client disconnects or says "bye", remove them from the list and close the socket.
                if not client_message or client_message == f"{client_name}: bye":
                    self.broadcast_message(client_name, f"{client_name} has left the chat!")
                    Server.Clients.remove(client)
                    client_socket.close()
                    break
                
                # Send the message to all other clients
                self.broadcast_message(client_name, client_message)
            except ConnectionResetError:
                # Handle abrupt disconnection
                self.broadcast_message(client_name, f"{client_name} has unexpectedly disconnected.")
                Server.Clients.remove(client)
                client_socket.close()
                break

    # Loop through the clients and send the message down each socket.
    # Skip the socket if it's the same client.
    def broadcast_message(self, sender_name, message):
        for client in self.Clients:
            if client["client_name"] != sender_name:
                try:
                    client["client_socket"].send(message.encode())
                except BrokenPipeError:
                    # Handle clients that have disconnected but haven't been removed yet
                    Server.Clients.remove(client)

if __name__ == "__main__":
    server = Server("127.0.0.1", 7633)
    server.listen()
