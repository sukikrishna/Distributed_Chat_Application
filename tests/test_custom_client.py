import pytest
import tkinter as tk
from unittest.mock import MagicMock, patch
import socket
import threading
import json
import sys

sys.path.insert(0, "src/custom_protocol")

from custom_server import ChatServer
from custom_client import ChatClient
from custom_protocol import CustomWireProtocol

class MockSocket:
    def __init__(self):
        self.sent_data = []
        self.received_data = []
        self.connected = True
        self.closed = False

    def connect(self, addr):
        self.connected = True

    def send(self, data):
        if not self.connected:
            raise ConnectionError()
        self.sent_data.append(data)

    def recv(self, size):
        if not self.connected:
            return b''
        return self.received_data.pop(0) if self.received_data else b''

    def close(self):
        self.closed = True
        self.connected = False

@pytest.fixture
def mock_socket():
    return MockSocket()

@pytest.fixture
def wire_protocol():
    return CustomWireProtocol()

@pytest.fixture
def chat_client(monkeypatch, mock_socket):
    def mock_socket_constructor(*args, **kwargs):
        return mock_socket
    
    monkeypatch.setattr(socket, "socket", mock_socket_constructor)
    
    # Mock tkinter
    monkeypatch.setattr(tk, "Tk", MagicMock)
    monkeypatch.setattr(tk, "Frame", MagicMock)
    monkeypatch.setattr(tk, "Label", MagicMock)
    monkeypatch.setattr(tk, "Entry", MagicMock)
    monkeypatch.setattr(tk, "Button", MagicMock)
    monkeypatch.setattr(tk, "Text", MagicMock)
    monkeypatch.setattr(tk, "Scrollbar", MagicMock)
    
    client = ChatClient("localhost", 12345)
    return client

def test_create_account(chat_client, mock_socket, wire_protocol):
    # Set up mock user input
    chat_client.username_entry.get = MagicMock(return_value="testuser")
    chat_client.password_entry.get = MagicMock(return_value="TestPass123")

    # Mock server response
    success_response = wire_protocol.encode_message(
        CustomWireProtocol.CMD_CREATE,
        [True, "Account created successfully"]
    )
    mock_socket.received_data.append(success_response)

    # Trigger account creation
    chat_client.create_account()

    # Verify sent message
    _, cmd, payload = wire_protocol.decode_message(mock_socket.sent_data[0])
    assert cmd == CustomWireProtocol.CMD_CREATE

def test_login(chat_client, mock_socket, wire_protocol):
    # Set up mock user input
    chat_client.username_entry.get = MagicMock(return_value="testuser")
    chat_client.password_entry.get = MagicMock(return_value="TestPass123")

    # Mock server response
    success_response = wire_protocol.encode_message(
        CustomWireProtocol.CMD_LOGIN,
        [True, "testuser", 0]
    )
    mock_socket.received_data.append(success_response)

    # Trigger login
    chat_client.login()

    # Verify sent message
    _, cmd, payload = wire_protocol.decode_message(mock_socket.sent_data[0])
    assert cmd == CustomWireProtocol.CMD_LOGIN

def test_send_message(chat_client, mock_socket, wire_protocol):
    chat_client.username = "testuser"  # Set logged in state
    chat_client.recipient_var.set("recipient")
    chat_client.message_text.get = MagicMock(return_value="Hello, World!")

    # Mock server response
    success_response = wire_protocol.encode_message(
        CustomWireProtocol.CMD_SEND,
        [True, "Message sent"]
    )
    mock_socket.received_data.append(success_response)

    # Send message
    chat_client.send_message()

    # Verify sent message
    _, cmd, payload = wire_protocol.decode_message(mock_socket.sent_data[0])
    assert cmd == CustomWireProtocol.CMD_SEND

def test_search_accounts(chat_client, mock_socket, wire_protocol):
    chat_client.search_var.get = MagicMock(return_value="test")

    # Mock server response
    users_response = wire_protocol.encode_message(
        CustomWireProtocol.CMD_LIST,
        [True, "", "testuser1", "online", "testuser2", "offline"]
    )
    mock_socket.received_data.append(users_response)

    # Search accounts
    chat_client.search_accounts()

    # Verify sent message
    _, cmd, payload = wire_protocol.decode_message(mock_socket.sent_data[0])
    assert cmd == CustomWireProtocol.CMD_LIST

def test_logout(chat_client, mock_socket, wire_protocol):
    chat_client.username = "testuser"

    # Mock server response
    success_response = wire_protocol.encode_message(
        CustomWireProtocol.CMD_LOGOUT,
        [True, "Logged out successfully"]
    )
    mock_socket.received_data.append(success_response)

    # Trigger logout
    chat_client.logout()

    # Verify sent message
    _, cmd, payload = wire_protocol.decode_message(mock_socket.sent_data[0])
    assert cmd == CustomWireProtocol.CMD_LOGOUT

def test_delete_account(chat_client, mock_socket, wire_protocol):
    chat_client.username = "testuser"
    chat_client.delete_password.get = MagicMock(return_value="TestPass123")

    # Mock server response
    success_response = wire_protocol.encode_message(
        CustomWireProtocol.CMD_DELETE_ACCOUNT,
        [True, "Account deleted"]
    )
    mock_socket.received_data.append(success_response)

    # Delete account
    chat_client.delete_account()

    # Verify sent message
    _, cmd, payload = wire_protocol.decode_message(mock_socket.sent_data[0])
    assert cmd == CustomWireProtocol.CMD_DELETE_ACCOUNT

def test_refresh_messages(chat_client, mock_socket, wire_protocol):
    chat_client.username = "testuser"
    chat_client.msg_count.get = MagicMock(return_value="50")

    # Mock server response
    messages_response = wire_protocol.encode_message(
        CustomWireProtocol.CMD_GET_MESSAGES,
        [True, "", struct.pack('!I', 1), "sender", "Hello!", struct.pack('!I', int(time.time()))]
    )
    mock_socket.received_data.append(messages_response)

    # Refresh messages
    chat_client.refresh_messages()

    # Verify sent message
    _, cmd, payload = wire_protocol.decode_message(mock_socket.sent_data[0])
    assert cmd == CustomWireProtocol.CMD_GET_MESSAGES

def test_connection_lost(chat_client, mock_socket):
    # Simulate connection loss
    mock_socket.connected = False
    chat_client.running = True
    
    # Mock messagebox
    with patch('tkinter.messagebox.showerror') as mock_error:
        chat_client.on_connection_lost()
        
    assert not chat_client.running
    mock_error.assert_called_once()

def test_on_closing(chat_client, mock_socket, wire_protocol):
    chat_client.username = "testuser"
    chat_client.running = True

    # Trigger closing
    chat_client.on_closing()

    assert not chat_client.running
    assert mock_socket.closed