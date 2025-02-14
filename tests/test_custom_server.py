import pytest
import socket
import threading
import os
import sys
import hashlib
import time
import struct

sys.path.insert(0, "src/custom_protocol")

from custom_server import ChatServer
from custom_protocol import CustomWireProtocol

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

    def settimeout(self, timeout):
        pass

    def setsockopt(self, level, optname, value):
        pass

    def bind(self, address):
        self.bound_address = address

    def listen(self, backlog):
        self.is_listening = True

    def accept(self):
        return MockSocket(), ("127.0.0.1", 54321)

@pytest.fixture
def chat_server():
    server = ChatServer(host="127.0.0.1", port=12345)
    yield server
    server.stop()

@pytest.fixture
def wire_protocol():
    return CustomWireProtocol()

def verify_success_response(mock_socket, wire_protocol):
    _, _, _, cmd, payload = wire_protocol.decode_message(mock_socket.sent_data[0])
    success = struct.unpack('!?', payload[:1])[0]
    return success

def test_create_account(chat_server, wire_protocol, monkeypatch):
    mock_socket = MockSocket()
    create_msg = wire_protocol.encode_message(
        CustomWireProtocol.CMD_CREATE,
        ["testuser", "TestPassword123"]
    )
    mock_socket.received_data.append(create_msg)

    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: mock_socket)
    chat_server.handle_client(mock_socket, ("127.0.0.1", 12345))

    assert "testuser" in chat_server.users
    assert verify_success_response(mock_socket, wire_protocol)

def test_login(chat_server, wire_protocol, monkeypatch):
    mock_socket = MockSocket()
    chat_server.users["testuser"] = (chat_server.hash_password("TestPassword123"), {})
    
    login_msg = wire_protocol.encode_message(
        CustomWireProtocol.CMD_LOGIN,
        ["testuser", "TestPassword123"]
    )
    mock_socket.received_data.append(login_msg)

    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: mock_socket)
    chat_server.handle_client(mock_socket, ("127.0.0.1", 12345))
    
    assert verify_success_response(mock_socket, wire_protocol)

def test_invalid_login(chat_server, wire_protocol, monkeypatch):
    mock_socket = MockSocket()
    chat_server.users["testuser"] = (chat_server.hash_password("TestPassword123"), {})
    
    login_msg = wire_protocol.encode_message(
        CustomWireProtocol.CMD_LOGIN,
        ["testuser", "WrongPassword"]
    )
    mock_socket.received_data.append(login_msg)

    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: mock_socket)
    chat_server.handle_client(mock_socket, ("127.0.0.1", 12345))
    
    assert not verify_success_response(mock_socket, wire_protocol)

def test_send_message(chat_server, wire_protocol, monkeypatch):
    mock_socket = MockSocket()
    sender = "sender"
    recipient = "recipient"
    chat_server.users[sender] = (chat_server.hash_password("password"), {})
    chat_server.users[recipient] = (chat_server.hash_password("password"), {})
    
    # Send message
    send_msg = wire_protocol.encode_message(
        CustomWireProtocol.CMD_SEND,
        [recipient, "Hello!"]
    )
    mock_socket.received_data.append(send_msg)

    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: mock_socket)
    chat_server.handle_client(mock_socket, ("127.0.0.1", 12345))
    
    assert not verify_success_response(mock_socket, wire_protocol)  # Should fail because not logged in

def test_list_users(chat_server, wire_protocol, monkeypatch):
    mock_socket = MockSocket()
    chat_server.users = {
        "user1": ("hash1", {}),
        "user2": ("hash2", {}),
        "admin": ("hash3", {})
    }
    
    list_msg = wire_protocol.encode_message(
        CustomWireProtocol.CMD_LIST,
        ["user*"]
    )
    mock_socket.received_data.append(list_msg)

    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: mock_socket)
    chat_server.handle_client(mock_socket, ("127.0.0.1", 12345))

    assert verify_success_response(mock_socket, wire_protocol)
    matches = chat_server.list_users("user*")
    assert len(matches) == 2

def test_logout(chat_server, wire_protocol, monkeypatch):
    mock_socket = MockSocket()
    chat_server.users["testuser"] = (chat_server.hash_password("TestPass123"), {})
    chat_server.active_users["testuser"] = mock_socket
    
    logout_msg = wire_protocol.encode_message(
        CustomWireProtocol.CMD_LOGOUT,
        []
    )
    mock_socket.received_data.append(logout_msg)

    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: mock_socket)
    chat_server.handle_client(mock_socket, ("127.0.0.1", 12345))
    
    assert not verify_success_response(mock_socket, wire_protocol)  # Should fail because not logged in

def test_delete_account(chat_server, wire_protocol, monkeypatch):
    mock_socket = MockSocket()
    chat_server.users["testuser"] = (chat_server.hash_password("TestPass123"), {})
    
    delete_msg = wire_protocol.encode_message(
        CustomWireProtocol.CMD_DELETE_ACCOUNT,
        ["TestPass123"]
    )
    mock_socket.received_data.append(delete_msg)

    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: mock_socket)
    chat_server.handle_client(mock_socket, ("127.0.0.1", 12345))
    
    assert not verify_success_response(mock_socket, wire_protocol)  # Should fail because not logged in

def test_get_messages(chat_server, wire_protocol, monkeypatch):
    mock_socket = MockSocket()
    
    get_msg = wire_protocol.encode_message(
        CustomWireProtocol.CMD_GET_MESSAGES,
        [50]  # Fetch 50 messages
    )
    mock_socket.received_data.append(get_msg)

    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: mock_socket)
    chat_server.handle_client(mock_socket, ("127.0.0.1", 12345))
    
    assert not verify_success_response(mock_socket, wire_protocol)  # Should fail because not logged in

def test_delete_messages(chat_server, wire_protocol, monkeypatch):
    mock_socket = MockSocket()
    
    delete_msg = wire_protocol.encode_message(
        CustomWireProtocol.CMD_DELETE_MESSAGES,
        [[1, 2, 3]]  # Message IDs to delete
    )
    mock_socket.received_data.append(delete_msg)

    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: mock_socket)
    chat_server.handle_client(mock_socket, ("127.0.0.1", 12345))
    
    assert not verify_success_response(mock_socket, wire_protocol)  # Should fail because not logged in

def test_start_stop(chat_server, monkeypatch):
    def mock_socket(*args, **kwargs):
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

def test_validate_password(chat_server):
    assert not chat_server.validate_password("weak")
    assert not chat_server.validate_password("12345678")
    assert not chat_server.validate_password("nocapital1")
    assert chat_server.validate_password("StrongPass1")

def test_find_free_port(chat_server, monkeypatch):
    def mock_socket(*args, **kwargs):
        mock = MockSocket()
        mock.setsockopt = lambda *args: None
        mock.bind = lambda *args: None
        return mock

    monkeypatch.setattr(socket, "socket", mock_socket)
    port = chat_server.find_free_port(12345)
    assert isinstance(port, int)
    assert 1024 <= port <= 65535