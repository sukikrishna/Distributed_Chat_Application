import socket
import selectors
import threading
import hashlib
import time
import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Set, Optional

class MessageType(Enum):
    CREATE_ACCOUNT = 1
    LOGIN = 2
    LIST_ACCOUNTS = 3
    PRIVATE_MESSAGE = 4
    GROUP_MESSAGE = 5
    JOIN_GROUP = 6
    LEAVE_GROUP = 7
    DELETE_CHAT = 8
    GET_HISTORY = 9

@dataclass
class ChatMessage:
    id: int
    sender: str
    content: str
    timestamp: float
    is_group: bool
    chat_id: str  # group_id for group messages, recipient for private messages

class ChatServer:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.accounts = {}  # username -> (password_hash, online_status)
        self.user_sockets = {}  # username -> socket
        self.message_history = {}  # chat_id -> [ChatMessage]
        self.group_members = {}  # group_id -> set(usernames)
        self.next_message_id = 1
        self.message_lock = threading.Lock()

    def _hash_password(self, password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    def start(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((self.host, self.port))
        server_socket.listen(5)
        print(f"Server started on {self.host}:{self.port}")

        while True:
            client_socket, address = server_socket.accept()
            threading.Thread(target=self.handle_client, args=(client_socket,), daemon=True).start()

    def handle_client(self, client_socket: socket.socket):
        username = None
        try:
            while True:
                message = client_socket.recv(1024).decode()
                if not message:
                    break

                parts = message.split(":", 2)
                command = parts[0]

                if command == "CREATE":
                    username, password = parts[1:]
                    if username in self.accounts:
                        client_socket.send("ERROR:Username already exists".encode())
                    else:
                        self.accounts[username] = (self._hash_password(password), False)
                        client_socket.send("SUCCESS:Account created".encode())

                elif command == "LOGIN":
                    username, password = parts[1:]
                    if username not in self.accounts:
                        client_socket.send("ERROR:Account not found".encode())
                        continue
                    
                    stored_hash, _ = self.accounts[username]
                    if stored_hash != self._hash_password(password):
                        client_socket.send("ERROR:Invalid password".encode())
                        continue

                    self.accounts[username] = (stored_hash, True)
                    self.user_sockets[username] = client_socket
                    client_socket.send("SUCCESS:Logged in".encode())

                elif command == "PRIVATE_MESSAGE":
                    if not username:
                        continue
                    recipient, content = parts[1:]
                    self.handle_private_message(username, recipient, content)

                elif command == "GROUP_MESSAGE":
                    if not username:
                        continue
                    group_id, content = parts[1:]
                    self.handle_group_message(username, group_id, content)

                elif command == "JOIN_GROUP":
                    if not username:
                        continue
                    group_id = parts[1]
                    if group_id not in self.group_members:
                        self.group_members[group_id] = set()
                    self.group_members[group_id].add(username)
                    self.broadcast_group_message(group_id, f"System: {username} joined the group")

                elif command == "GET_HISTORY":
                    if not username:
                        continue
                    chat_id = parts[1]
                    self.send_chat_history(username, chat_id)

                elif command == "DELETE_CHAT":
                    if not username:
                        continue
                    chat_id = parts[1]
                    if chat_id in self.message_history:
                        del self.message_history[chat_id]
                    if chat_id in self.group_members:
                        del self.group_members[chat_id]

        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            if username:
                if username in self.user_sockets:
                    del self.user_sockets[username]
                if username in self.accounts:
                    stored_hash, _ = self.accounts[username]
                    self.accounts[username] = (stored_hash, False)
            client_socket.close()

    def handle_private_message(self, sender: str, recipient: str, content: str):
        chat_id = f"private_{min(sender, recipient)}_{max(sender, recipient)}"
        
        with self.message_lock:
            message = ChatMessage(
                id=self.next_message_id,
                sender=sender,
                content=content,
                timestamp=time.time(),
                is_group=False,
                chat_id=chat_id
            )
            self.next_message_id += 1
            
            if chat_id not in self.message_history:
                self.message_history[chat_id] = []
            self.message_history[chat_id].append(message)

        self.send_message_to_user(recipient, self.format_message(message))
        self.send_message_to_user(sender, self.format_message(message))

    def handle_group_message(self, sender: str, group_id: str, content: str):
        if group_id not in self.group_members:
            return

        with self.message_lock:
            message = ChatMessage(
                id=self.next_message_id,
                sender=sender,
                content=content,
                timestamp=time.time(),
                is_group=True,
                chat_id=group_id
            )
            self.next_message_id += 1
            
            if group_id not in self.message_history:
                self.message_history[group_id] = []
            self.message_history[group_id].append(message)

        self.broadcast_group_message(group_id, self.format_message(message))

    def format_message(self, message: ChatMessage) -> str:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(message.timestamp))
        return f"{message.id}:{timestamp}:{message.sender}:{message.content}"

    def send_message_to_user(self, username: str, message: str):
        if username in self.user_sockets:
            try:
                self.user_sockets[username].send(f"MESSAGE:{message}".encode())
            except:
                if username in self.user_sockets:
                    del self.user_sockets[username]

    def broadcast_group_message(self, group_id: str, message: str):
        if group_id not in self.group_members:
            return
        for username in self.group_members[group_id]:
            self.send_message_to_user(username, message)

    def send_chat_history(self, username: str, chat_id: str):
        if chat_id not in self.message_history:
            return
        history = [self.format_message(msg) for msg in self.message_history[chat_id]]
        if username in self.user_sockets:
            try:
                self.user_sockets[username].send(f"HISTORY:{chat_id}:{json.dumps(history)}".encode())
            except:
                if username in self.user_sockets:
                    del self.user_sockets[username]

if __name__ == "__main__":
    server = ChatServer("127.0.0.1", 50012)
    server.start()