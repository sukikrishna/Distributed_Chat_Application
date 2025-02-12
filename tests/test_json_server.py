import pytest
import socket
import json
import threading
import os
import sys
import hashlib
import time

sys.path.insert(0, "src/json_protocol")

from json_server import ChatServer

class MockSocket:
    """A mock socket class to simulate client-server communication.

    Attributes:
        received_data (list): Simulated received data.
        sent_data (list): Stores sent messages.
        bound_address (tuple): Stores bound address details.
        is_listening (bool): Tracks if the server is in listening mode.
        is_closed (bool): Indicates if the socket is closed.
    """

    def __init__(self):
        """Initializes the mock socket."""
        self.received_data = []
        self.sent_data = []
        self.bound_address = None
        self.is_listening = False
        self.is_closed = False

    def send(self, data):
        """Simulates sending data over a socket.

        Args:
            data (bytes): Data to send.
        """
        if self.is_closed:
            raise ConnectionError("Socket is closed")
        self.sent_data.append(data)

    def recv(self, buffer_size):
        """Simulates receiving data from a socket.

        Args:
            buffer_size (int): Buffer size for received data.

        Returns:
            bytes: The received data or an empty byte string if none.
        """
        if self.is_closed:
            return b""
        return self.received_data.pop(0) if self.received_data else b""

    def close(self):
        """Simulates closing a socket."""
        self.is_closed = True

    def settimeout(self, timeout):
        """Simulates setting a timeout for the socket."""
        pass

    def setsockopt(self, level, optname, value):
        """Simulates setting socket options."""
        pass

    def bind(self, address):
        """Simulates binding a socket to an address.

        Args:
            address (tuple): The (host, port) pair.
        """
        self.bound_address = address

    def listen(self, backlog):
        """Simulates enabling the socket to accept connections.

        Args:
            backlog (int): Number of unaccepted connections before refusing new ones.
        """
        self.is_listening = True

    def accept(self):
        """Simulates accepting a new client connection.

        Returns:
            tuple: A new MockSocket instance and a mock client address.
        """
        return MockSocket(), ("127.0.0.1", 54321)

@pytest.fixture
def chat_server():
    """Fixture to create a ChatServer instance.

    Yields:
        ChatServer: An instance of the chat server.
    """
    server = ChatServer(host="127.0.0.1", port=12345)
    yield server
    server.stop()

def test_handle_client(chat_server, monkeypatch):
    """Tests handling a client connection with valid user creation."""
    mock_socket = MockSocket()
    mock_socket.received_data.append(json.dumps({
        "version": "1.0",
        "cmd": "create",
        "username": "testuser",
        "password": "TestPassword123"
    }).encode())

    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: mock_socket)
    monkeypatch.setattr(threading, "Thread", lambda target, args, daemon: target(*args))

    chat_server.handle_client(mock_socket, ("127.0.0.1", 12345))

    assert "testuser" in chat_server.users
    assert len(mock_socket.sent_data) > 0
    response = json.loads(mock_socket.sent_data[0].decode())
    assert response["success"] is True

def test_start(chat_server, monkeypatch):
    """Tests that ChatServer starts and can be stopped properly."""
    
    def mock_socket(*args, **kwargs):
        """Mocked socket to prevent real network operations."""
        mock = MockSocket()
        mock.setsockopt = lambda *args: None
        mock.bind = lambda *args: None
        mock.listen = lambda backlog: None
        return mock

    monkeypatch.setattr(socket, "socket", mock_socket)

    server_thread = threading.Thread(target=chat_server.start, daemon=True)
    server_thread.start()
    time.sleep(1)

    assert chat_server.running is True

    chat_server.stop()
    server_thread.join(timeout=1)
    assert chat_server.running is False

def test_stop(chat_server):
    """Tests stopping the chat server."""
    chat_server.running = True
    chat_server.stop()
    assert chat_server.running is False

def test_get_messages(chat_server):
    """Tests retrieving read messages for a user."""
    chat_server.messages["user1"] = [
        {"read": True, "timestamp": 1, "content": "Hello"},
        {"read": True, "timestamp": 2, "content": "World"}
    ]
    messages = chat_server.get_messages("user1")
    assert len(messages) == 2
    assert messages[0]["content"] == "World"

def test_get_unread_messages(chat_server):
    """Tests retrieving unread messages for a user."""
    chat_server.messages["user1"] = [
        {"read": False, "timestamp": 1, "content": "Hello"},
        {"read": True, "timestamp": 2, "content": "World"}
    ]
    unread_messages = chat_server.get_unread_messages("user1", 1)
    assert len(unread_messages) == 1
    assert unread_messages[0]["content"] == "Hello"

    @pytest.fixture
    def chat_server():
        """Fixture to create a ChatServer instance."""
        server = ChatServer(host="127.0.0.1", port=12345)
        yield server
        server.stop()

def test_validate_password(chat_server):
    """Tests password validation rules."""
    assert chat_server.validate_password("Weak") is False
    assert chat_server.validate_password("StrongPassword1") is True

def test_get_unread_count(chat_server):
    """Tests unread message count retrieval."""
    chat_server.messages["user1"] = [{"read": False}, {"read": True}, {"read": False}]
    assert chat_server.get_unread_count("user1") == 2

def test_handle_invalid_json(chat_server, monkeypatch):
    """Tests handling of invalid JSON input."""
    mock_socket = MockSocket()
    mock_socket.received_data.append(b"{invalid json}")

    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: mock_socket)

    chat_server.handle_client(mock_socket, ("127.0.0.1", 12345))

    response = json.loads(mock_socket.sent_data[0].decode())
    assert response["success"] is False
    assert response["error"] == "Invalid JSON format"

def test_handle_invalid_command(chat_server, monkeypatch):
    """Tests server response to unknown commands."""
    mock_socket = MockSocket()
    mock_socket.received_data.append(json.dumps({"version": "1.0", "cmd": "invalid_command"}).encode())

    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: mock_socket)

    chat_server.handle_client(mock_socket, ("127.0.0.1", 12345))

    response = json.loads(mock_socket.sent_data[0].decode())
    assert response["success"] is False
    assert response["message"] == "Invalid command"


def test_server_start_listen(chat_server, monkeypatch):
    """Test that the server starts and listens correctly."""
    mock_socket = MockSocket()
    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: mock_socket)

    server_thread = threading.Thread(target=chat_server.start, daemon=True)
    server_thread.start()
    time.sleep(1)

    assert chat_server.running is True
    assert mock_socket.is_listening is True  # Ensure server is actually listening

    chat_server.stop()
    server_thread.join(timeout=1)
    assert chat_server.running is False

def test_send_message_invalid_user(chat_server):
    """Test sending a message to a non-existent user."""
    chat_server.users["valid_user"] = ("hashed_pw", {})

    mock_socket = MockSocket()
    chat_server.active_users["valid_user"] = mock_socket

    msg = {"version": "1.0", "cmd": "send", "to": "fake_user", "content": "Hello"}
    mock_socket.received_data.append(json.dumps(msg).encode())

    chat_server.handle_client(mock_socket, ("127.0.0.1", 12345))

    response = json.loads(mock_socket.sent_data[0].decode())
    assert response["success"] is False
    assert response["message"] == "Not logged in"

def test_find_free_port(chat_server, monkeypatch):
    """Tests finding an available port for the server."""
    
    def mock_socket(*args, **kwargs):
        mock = MockSocket()
        mock.setsockopt = lambda *args: None
        mock.bind = lambda *args: None
        return mock

    monkeypatch.setattr(socket, "socket", mock_socket)
    port = chat_server.find_free_port(12345)
    assert isinstance(port, int)

def test_broadcast_user_list(chat_server):
    """Tests broadcasting the updated user list."""
    chat_server.users = {"user1": ("hash1", {}), "user2": ("hash2", {})}
    chat_server.active_users = {"user1": MockSocket()}
    users_list = chat_server.broadcast_user_list()
    assert len(users_list) == 2
    assert users_list[0]["username"] == "user1"
    assert users_list[0]["status"] == "online"
