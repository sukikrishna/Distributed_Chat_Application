# custom_protocol.py

from dataclasses import dataclass
from enum import Enum
import socket
import selectors
import types
import hashlib
import struct
from typing import Optional, List, Dict, Tuple
import threading
import queue
import time

class MessageType(Enum):
    CREATE_ACCOUNT = 1
    LOGIN = 2
    LIST_ACCOUNTS = 3
    SEND_MESSAGE = 4
    READ_MESSAGES = 5
    DELETE_MESSAGES = 6
    DELETE_ACCOUNT = 7
    LOGOUT = 8
    ERROR = 9
    SUCCESS = 10
    UPDATE_SETTINGS = 11

@dataclass
class Message:
    type: MessageType
    payload_length: int
    payload: bytes

@dataclass
class ChatMessage:
    id: int
    sender: str
    recipient: str
    content: str
    timestamp: float
    read: bool = False

class CustomProtocolServer:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.selector = selectors.DefaultSelector()
        self.accounts: Dict[str, Tuple[str, bool, dict]] = {}  # username -> (hashed_password, logged_in, settings)
        self.messages: Dict[str, List[ChatMessage]] = {}
        self.next_message_id = 1
        self.active_connections: Dict[str, socket.socket] = {}

    def _hash_password(self, password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    def pack_message(self, msg_type: MessageType, payload: bytes) -> bytes:
        return struct.pack('!BL', msg_type.value, len(payload)) + payload

    def unpack_message(self, data: bytes) -> Message:
        msg_type, payload_length = struct.unpack('!BL', data[:5])
        payload = data[5:5+payload_length]
        return Message(MessageType(msg_type), payload_length, payload)

    def handle_create_account(self, payload: bytes) -> bytes:
        username, password = payload.decode().split(':')
        if username in self.accounts:
            return self.pack_message(MessageType.ERROR, b"Username already exists")
        default_settings = {
            'messages_per_fetch': 10,
            'delete_messages_on_account_deletion': True
        }
        self.accounts[username] = (self._hash_password(password), False, default_settings)
        self.messages[username] = []
        return self.pack_message(MessageType.SUCCESS, b"Account created successfully")

    def handle_login(self, payload: bytes, client_socket: socket.socket) -> bytes:
        username, password = payload.decode().split(':')
        if username not in self.accounts:
            return self.pack_message(MessageType.ERROR, b"Username does not exist")
        stored_hash, logged_in, settings = self.accounts[username]
        if stored_hash != self._hash_password(password):
            return self.pack_message(MessageType.ERROR, b"Invalid password")
        if logged_in:
            return self.pack_message(MessageType.ERROR, b"Account already logged in")

        self.accounts[username] = (stored_hash, True, settings)
        self.active_connections[username] = client_socket
        unread_count = sum(1 for msg in self.messages[username] if not msg.read)
        return self.pack_message(MessageType.SUCCESS, f"Login successful. {unread_count} unread messages".encode())

    def handle_logout(self, payload: bytes) -> bytes:
        username = payload.decode()
        if username in self.accounts:
            stored_hash, _, settings = self.accounts[username]
            self.accounts[username] = (stored_hash, False, settings)
            if username in self.active_connections:
                del self.active_connections[username]
            return self.pack_message(MessageType.SUCCESS, b"Logged out successfully")
        return self.pack_message(MessageType.ERROR, b"User not found")

    def handle_list_accounts(self, payload: bytes) -> bytes:
        pattern = payload.decode()
        matching_accounts = []
        for username in self.accounts.keys():
            if pattern in username:
                _, logged_in, _ = self.accounts[username]
                status = "online" if logged_in else "offline"
                matching_accounts.append(f"{username}:{status}")
        return self.pack_message(MessageType.SUCCESS, ','.join(matching_accounts).encode())

    def handle_send_message(self, payload: bytes) -> bytes:
        sender, recipient, message = payload.decode().split(':', 2)
        if recipient not in self.accounts:
            return self.pack_message(MessageType.ERROR, b"Recipient does not exist")

        chat_message = ChatMessage(
            id=self.next_message_id,
            sender=sender,
            recipient=recipient,
            content=message,
            timestamp=time.time()
        )
        self.next_message_id += 1
        self.messages[recipient].append(chat_message)

        # If recipient is online, send immediate notification
        if recipient in self.active_connections:
            try:
                notification = self.pack_message(
                    MessageType.SUCCESS,
                    f"New message from {sender}".encode()
                )
                self.active_connections[recipient].send(notification)
            except:
                pass

        return self.pack_message(MessageType.SUCCESS, b"Message sent successfully")

    def handle_read_messages(self, payload: bytes) -> bytes:
        username, count = payload.decode().split(':')
        count = int(count)
        if username not in self.messages:
            return self.pack_message(MessageType.ERROR, b"User not found")

        unread_messages = [msg for msg in self.messages[username] if not msg.read][:count]
        for msg in unread_messages:
            msg.read = True

        messages_data = []
        for msg in unread_messages:
            messages_data.append(f"{msg.id}:{msg.sender}:{msg.timestamp}:{msg.content}")

        return self.pack_message(MessageType.SUCCESS, '\n'.join(messages_data).encode())

    def handle_delete_messages(self, payload: bytes) -> bytes:
        username, message_ids = payload.decode().split(':')
        if username not in self.messages:
            return self.pack_message(MessageType.ERROR, b"User not found")

        message_ids = set(int(id) for id in message_ids.split(','))
        self.messages[username] = [
            msg for msg in self.messages[username]
            if msg.id not in message_ids
        ]
        return self.pack_message(MessageType.SUCCESS, b"Messages deleted successfully")

    def handle_delete_account(self, payload: bytes) -> bytes:
        username, password = payload.decode().split(':')
        if username not in self.accounts:
            return self.pack_message(MessageType.ERROR, b"User not found")

        stored_hash, _, settings = self.accounts[username]
        if stored_hash != self._hash_password(password):
            return self.pack_message(MessageType.ERROR, b"Invalid password")

        del self.accounts[username]
        del self.messages[username]
        if username in self.active_connections:
            del self.active_connections[username]

        return self.pack_message(MessageType.SUCCESS, b"Account deleted successfully")

    def handle_update_settings(self, payload: bytes) -> bytes:
        username, settings_str = payload.decode().split(':', 1)
        if username not in self.accounts:
            return self.pack_message(MessageType.ERROR, b"User not found")

        stored_hash, logged_in, old_settings = self.accounts[username]
        new_settings = eval(settings_str)  # Be careful with eval in production!
        self.accounts[username] = (stored_hash, logged_in, {**old_settings, **new_settings})
        return self.pack_message(MessageType.SUCCESS, b"Settings updated successfully")

    def start(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind((self.host, self.port))
        server_socket.listen()
        server_socket.setblocking(False)
        self.selector.register(server_socket, selectors.EVENT_READ, data=None)

        print(f"Server started on {self.host}:{self.port}")

        try:
            while True:
                events = self.selector.select()
                for key, mask in events:
                    if key.data is None:
                        self.accept_connection(key.fileobj)
                    else:
                        self.service_connection(key, mask)
        except KeyboardInterrupt:
            print("Server shutting down...")
        finally:
            self.selector.close()

    def accept_connection(self, sock):
        conn, addr = sock.accept()
        print(f"Accepted connection from {addr}")
        conn.setblocking(False)
        data = types.SimpleNamespace(addr=addr, inb=b"", outb=b"")
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        self.selector.register(conn, events, data=data)

    def service_connection(self, key, mask):
        sock = key.fileobj
        data = key.data

        if mask & selectors.EVENT_READ:
            recv_data = sock.recv(1024)
            if recv_data:
                data.inb += recv_data
                while len(data.inb) >= 5:
                    try:
                        message = self.unpack_message(data.inb)
                        handlers = {
                            MessageType.CREATE_ACCOUNT: self.handle_create_account,
                            MessageType.LOGIN: lambda p: self.handle_login(p, sock),
                            MessageType.LOGOUT: self.handle_logout,
                            MessageType.LIST_ACCOUNTS: self.handle_list_accounts,
                            MessageType.SEND_MESSAGE: self.handle_send_message,
                            MessageType.READ_MESSAGES: self.handle_read_messages,
                            MessageType.DELETE_MESSAGES: self.handle_delete_messages,
                            MessageType.DELETE_ACCOUNT: self.handle_delete_account,
                            MessageType.UPDATE_SETTINGS: self.handle_update_settings
                        }
                        handler = handlers.get(message.type)
                        if handler:
                            response = handler(message.payload)
                            data.outb += response
                        data.inb = data.inb[5+message.payload_length:]
                    except Exception as e:
                        print(f"Error processing message: {e}")
                        break
            else:
                print(f"Closing connection to {data.addr}")
                self.selector.unregister(sock)
                sock.close()

        if mask & selectors.EVENT_WRITE:
            if data.outb:
                sent = sock.send(data.outb)
                data.outb = data.outb[sent:]

class CustomProtocolClient:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.receive_queue = queue.Queue()
        self.current_user = None
        self.settings = {
            'messages_per_fetch': 10,
            'delete_messages_on_account_deletion': True
        }

    def connect(self):
        try:
            self.socket.connect((self.host, self.port))
            self.receive_thread = threading.Thread(target=self._receive_messages)
            self.receive_thread.daemon = True
            self.receive_thread.start()
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False

    def pack_message(self, msg_type: MessageType, payload: bytes) -> bytes:
        return struct.pack('!BL', msg_type.value, len(payload)) + payload

    def unpack_message(self, data: bytes) -> Message:
        msg_type, payload_length = struct.unpack('!BL', data[:5])
        payload = data[5:5+payload_length]
        return Message(MessageType(msg_type), payload_length, payload)

    def _receive_messages(self):
        while True:
            try:
                header = self.socket.recv(5)
                if not header:
                    break
                msg_type, payload_length = struct.unpack('!BL', header)
                payload = self.socket.recv(payload_length)
                message = Message(MessageType(msg_type), payload_length, payload)
                self.receive_queue.put(message)
            except Exception as e:
                print(f"Error receiving message: {e}")
                break

    def create_account(self, username: str, password: str) -> str:
        payload = f"{username}:{password}".encode()
        self.socket.send(self.pack_message(MessageType.CREATE_ACCOUNT, payload))
        response = self.receive_queue.get()
        return response.payload.decode()

    def login(self, username: str, password: str) -> str:
        payload = f"{username}:{password}".encode()
        self.socket.send(self.pack_message(MessageType.LOGIN, payload))
        response = self.receive_queue.get()
        if response.type == MessageType.SUCCESS:
            self.current_user = username
        return response.payload.decode()

    def logout(self) -> str:
        if not self.current_user:
            return "Not logged in"
        payload = self.current_user.encode()
        self.socket.send(self.pack_message(MessageType.LOGOUT, payload))
        response = self.receive_queue.get()
        if response.type == MessageType.SUCCESS:
            self.current_user = None
        return response.payload.decode()

    def list_accounts(self, pattern: str = "") -> List[str]:
        self.socket.send(self.pack_message(MessageType.LIST_ACCOUNTS, pattern.encode()))
        response = self.receive_queue.get()
        return response.payload.decode().split(',') if response.payload else []

    def send_message(self, recipient: str, message: str) -> str:
        if not self.current_user:
            return "Not logged in"
        payload = f"{self.current_user}:{recipient}:{message}".encode()
        self.socket.send(self.pack_message(MessageType.SEND_MESSAGE, payload))
        response = self.receive_queue.get()
        return response.payload.decode()

    def read_messages(self, count: Optional[int] = None) -> List[ChatMessage]:
        if not self.current_user:
            return "Not logged in"
        if count is None:
            count = self.settings['messages_per_fetch']
        payload = f"{self.current_user}:{count}".encode()
        self.socket.send(self.pack_message(MessageType.READ_MESSAGES, payload))
        response = self.receive_queue.get()
        return response.payload.decode().split('\n') if response.payload else []

    # def delete_messages(self, message_ids: List[int]) -> str:
    #     if not self.current_user:
    #         return "Not logged in"
    #     payload = f"{self.current_user}:{','.join(map(str, message_ids))}".encode()
    #     self.socket.send(self.pack_message(MessageType.DELETE_MESSAGES, payload))
    #     response = self.receive_queue.get()
    #     return response.payload.decode
    
    # [Previous code remains the same until the CustomProtocolClient class...]

    def delete_messages(self, message_ids: List[int]) -> str:
        if not self.current_user:
            return "Not logged in"
        payload = f"{self.current_user}:{','.join(map(str, message_ids))}".encode()
        self.socket.send(self.pack_message(MessageType.DELETE_MESSAGES, payload))
        response = self.receive_queue.get()
        return response.payload.decode()

    def delete_account(self, password: str) -> str:
        if not self.current_user:
            return "Not logged in"
        payload = f"{self.current_user}:{password}".encode()
        self.socket.send(self.pack_message(MessageType.DELETE_ACCOUNT, payload))
        response = self.receive_queue.get()
        if response.type == MessageType.SUCCESS:
            self.current_user = None
        return response.payload.decode()

    def update_settings(self, new_settings: dict) -> str:
        if not self.current_user:
            return "Not logged in"
        self.settings.update(new_settings)
        payload = f"{self.current_user}:{str(new_settings)}".encode()
        self.socket.send(self.pack_message(MessageType.UPDATE_SETTINGS, payload))
        response = self.receive_queue.get()
        return response.payload.decode()

    def close(self):
        """Close the connection"""
        if self.current_user:
            self.logout()
        self.socket.close()

if __name__ == "__main__":
    # Example server usage
    server = CustomProtocolServer("localhost", 9999)
    server.start()