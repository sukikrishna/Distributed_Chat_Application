#custom_protocol

from dataclasses import dataclass
from enum import Enum
import socket
import threading
import hashlib
import time
import json
from typing import Dict, List, Tuple

class MessageType(Enum):
    CREATE = 1
    LOGIN = 2
    LIST = 3
    PRIVATE = 4
    GROUP = 5
    DELETE = 6
    DELETE_ACCOUNT = 7
    LOGOUT = 8
    UPDATE_SETTINGS = 9

@dataclass
class ChatMessage:
    id: int
    sender: str
    content: str
    timestamp: float
    recipient: str
    is_group: bool = False
    read: bool = False

class ChatServer:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.accounts = {}  # username: (hash, online, settings)
        self.messages = {}  # username: [messages]
        self.connections = {}  # username: socket
        self.groups = {}  # group_id: [users]
        self.msg_id = 0

    def _hash(self, password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    def handle_client(self, client):
        username = None
        try:
            while True:
                data = client.recv(1024).decode().split(":", 1)
                if not data or len(data) < 2:
                    break

                cmd, payload = data
                if cmd == "CREATE":
                    username, password = payload.split(":")
                    if username in self.accounts:
                        client.send("ERROR:Username taken".encode())
                    else:
                        self.accounts[username] = (self._hash(password), False, {'msgs_per_fetch': 10})
                        self.messages[username] = []
                        client.send("OK:Account created".encode())

                elif cmd == "LOGIN":
                    username, password = payload.split(":")
                    if username not in self.accounts or self.accounts[username][0] != self._hash(password):
                        client.send("ERROR:Invalid credentials".encode())
                        continue

                    self.accounts[username] = (self.accounts[username][0], True, self.accounts[username][2])
                    self.connections[username] = client
                    unread = len([m for m in self.messages[username] if not m.read])
                    client.send(f"OK:{unread}".encode())

                elif cmd == "LIST":
                    pattern = payload
                    accounts = []
                    for user, (_, online, _) in self.accounts.items():
                        if pattern in user:
                            status = "online" if online else "offline"
                            unread = len([m for m in self.messages[user] if not m.read])
                            accounts.append(f"{user}:{status}:{unread}")
                    client.send(f"OK:{','.join(accounts)}".encode())

                elif cmd == "PRIVATE":
                    sender, recipient, msg = payload.split(":", 2)
                    if recipient not in self.accounts:
                        client.send("ERROR:Recipient not found".encode())
                        continue

                    self.msg_id += 1
                    message = ChatMessage(
                        id=self.msg_id,
                        sender=sender,
                        content=msg,
                        timestamp=time.time(),
                        recipient=recipient
                    )

                    self.messages[recipient].append(message)
                    if recipient in self.connections:
                        timestamp = time.strftime("%H:%M:%S")
                        self.connections[recipient].send(f"MSG:{timestamp}:{sender}:{msg}".encode())
                    client.send("OK:Message sent".encode())

                elif cmd == "GROUP":
                    sender, group_id, msg = payload.split(":", 2)
                    if group_id not in self.groups:
                        self.groups[group_id] = set()
                    self.groups[group_id].add(sender)

                    self.msg_id += 1
                    message = ChatMessage(
                        id=self.msg_id,
                        sender=sender,
                        content=msg,
                        timestamp=time.time(),
                        recipient=group_id,
                        is_group=True
                    )

                    timestamp = time.strftime("%H:%M:%S")
                    formatted = f"MSG:{timestamp}:{sender} (Group):{msg}"
                    for member in self.groups[group_id]:
                        if member != sender:
                            self.messages[member].append(message)
                            if member in self.connections:
                                self.connections[member].send(formatted.encode())
                    client.send("OK:Sent".encode())

                elif cmd == "DELETE_ACCOUNT":
                    username, password = payload.split(":")
                    if username not in self.accounts or self.accounts[username][0] != self._hash(password):
                        client.send("ERROR:Invalid credentials".encode())
                    else:
                        del self.accounts[username]
                        del self.messages[username]
                        client.send("OK:Account deleted".encode())
                        break

                elif cmd == "LOGOUT":
                    username = payload
                    if username in self.accounts:
                        self.accounts[username] = (self.accounts[username][0], False, self.accounts[username][2])
                        if username in self.connections:
                            del self.connections[username]
                        client.send("OK:Logged out".encode())
                        break

        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            if username and username in self.accounts:
                self.accounts[username] = (self.accounts[username][0], False, self.accounts[username][2])
                if username in self.connections:
                    del self.connections[username]
            client.close()

    def start(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.host, self.port))
        server.listen()

        while True:
            client, _ = server.accept()
            threading.Thread(target=self.handle_client, args=(client,), daemon=True).start()

if __name__ == "__main__":
    server = ChatServer("127.0.0.1", 50030)
    server.start()