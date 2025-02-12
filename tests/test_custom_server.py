import pytest
import socket
import threading
import time
from unittest.mock import Mock, patch
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.custom_protocol.custom_server import ChatServer
from src.custom_protocol.custom_protocol import CustomWireProtocol

class MockSocket:
    def __init__(self):
        self.received_data = []
        self.sent_data = []
        self.bound_address = None
        self.is_listening = False
        self.is_closed = False

    def send(self, data):
        if self.is_closed:
            raise ConnectionError("Socket is closed")
        self.sent_data.append(data)

    def recv(self, buffer_size):
        if self.is_closed:
            return b""
        return self.received_data.pop(0) if self.received_data else b""

    def close(self):
        self.is_closed = True

    def settimeout(self, timeout): pass
    def setsockopt(self, level, optname, value): pass
    def bind(self, address): self.bound_address = address
    def listen(self, backlog): self.is_listening = True
    def accept(self): return MockSocket(), ("127.0.0.1", 54321)

@pytest.fixture
def server():
    server = ChatServer("127.0.0.1", 0)
    yield server
    server.stop()

def test_server_initialization(server):
    assert server.host == "127.0.0.1"
    assert isinstance(server.protocol, CustomWireProtocol)
    assert server.users == {}
    assert server.running == False

def test_password_validation(server):
    assert server.validate_password("Weak") == False
    assert server.validate_password("StrongPassword1") == True

def test_handle_client_create_account(server):
    mock_socket = MockSocket()
    protocol = CustomWireProtocol()
    
    create_msg = protocol.encode_message(
        CustomWireProtocol.CMD_CREATE,
        ["testuser", "Password123"]
    )
    mock_socket.received_data.append(create_msg)
    
    server.handle_client(mock_socket, ("127.0.0.1", 12345))
    assert "testuser" in server.users

def test_handle_client_login(server):
    mock_socket = MockSocket()
    protocol = CustomWireProtocol()
    
    # Create account first
    server.users["testuser"] = (server.hash_password("Password123"), {})
    
    login_msg = protocol.encode_message(
        CustomWireProtocol.CMD_LOGIN,
        ["testuser", "Password123"]
    )
    mock_socket.received_data.append(login_msg)
    
    server.handle_client(mock_socket, ("127.0.0.1", 12345))
    assert "testuser" in server.active_users

def test_handle_client_send_message(server):
    mock_socket = MockSocket()
    protocol = CustomWireProtocol()
    
    server.users["sender"] = (server.hash_password("Password123"), {})
    server.users["receiver"] = (server.hash_password("Password123"), {})
    
    # Login first
    login_msg = protocol.encode_message(
        CustomWireProtocol.CMD_LOGIN,
        ["sender", "Password123"]
    )
    send_msg = protocol.encode_message(
        CustomWireProtocol.CMD_SEND,
        ["receiver", "Hello!"]
    )
    
    mock_socket.received_data.extend([login_msg, send_msg])
    server.handle_client(mock_socket, ("127.0.0.1", 12345))
    
    assert len(server.messages["receiver"]) == 1