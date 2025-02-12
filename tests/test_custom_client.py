import pytest
import sys
import os
import socket
from unittest.mock import Mock, patch
import tkinter as tk

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.custom_protocol.custom_client import ChatClient
from src.custom_protocol.custom_protocol import CustomWireProtocol

class MockTk:
    def __init__(self):
        self.calls = []
    def title(self, *args): pass
    def geometry(self, *args): pass
    def destroy(self): pass
    def mainloop(self): pass
    def after(self, *args): pass
    def protocol(self, *args): pass

@pytest.fixture
def mock_socket():
    with patch('socket.socket') as mock:
        socket_instance = Mock()
        mock.return_value = socket_instance
        yield socket_instance

@pytest.fixture
def mock_tk():
    with patch('tkinter.Tk', return_value=MockTk()):
        yield

@pytest.fixture
def client(mock_socket, mock_tk):
    with patch('src.custom_protocol.custom_client.Config'):
        client = ChatClient("localhost", 12345)
        yield client

def test_client_initialization(mock_socket, mock_tk):
    with patch('src.custom_protocol.custom_client.Config'):
        client = ChatClient("localhost", 12345)
        assert client.host == "localhost"
        assert client.port == 12345
        assert client.protocol is not None
        mock_socket.connect.assert_called_once()

def test_login(client, mock_socket):
    client.username_entry = Mock()
    client.password_entry = Mock()
    client.username_entry.get.return_value = "testuser"
    client.password_entry.get.return_value = "password123"
    
    client.login()
    sent_data = mock_socket.send.call_args[0][0]
    _, cmd, _ = client.protocol.decode_message(sent_data)
    assert cmd == CustomWireProtocol.CMD_LOGIN

def test_send_message(client, mock_socket):
    client.username = "testuser"
    client.recipient_var = tk.StringVar(value="recipient")
    client.message_text = Mock()
    client.message_text.get.return_value = "Hello!"
    
    client.send_message()
    sent_data = mock_socket.send.call_args[0][0]
    _, cmd, _ = client.protocol.decode_message(sent_data)
    assert cmd == CustomWireProtocol.CMD_SEND

def test_search_accounts(client, mock_socket):
    client.search_var = tk.StringVar(value="test")
    client.search_accounts()
    sent_data = mock_socket.send.call_args[0][0]
    _, cmd, _ = client.protocol.decode_message(sent_data)
    assert cmd == CustomWireProtocol.CMD_LIST

def test_logout(client, mock_socket):
    client.username = "testuser"
    client.logout()
    sent_data = mock_socket.send.call_args[0][0]
    _, cmd, _ = client.protocol.decode_message(sent_data)
    assert cmd == CustomWireProtocol.CMD_LOGOUT