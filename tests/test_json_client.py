import pytest
import socket
import json
import sys
import tkinter as tk
from tkinter import messagebox
from unittest.mock import MagicMock, patch

sys.path.insert(0, "src/json_protocol")
from json_client import ChatClient

@pytest.fixture
def chat_client():
    """Fixture to create a ChatClient instance with a mocked socket."""
    with patch('socket.socket') as mock_socket:
        client = ChatClient("127.0.0.1", 12345)
        client.socket = MagicMock()
        yield client

def test_chat_client_initialization(chat_client):
    """Test the initialization of the ChatClient class."""
    assert chat_client.host == "127.0.0.1"
    assert chat_client.port == 12345
    assert chat_client.username is None
    assert chat_client.running is True

def test_setup_gui(chat_client):
    """Test the setup_gui method."""
    chat_client.setup_gui()
    assert hasattr(chat_client, 'notebook')
    assert hasattr(chat_client, 'auth_frame')
    assert hasattr(chat_client, 'chat_frame')
    assert hasattr(chat_client, 'accounts_frame')

def test_setup_auth_frame(chat_client):
    """Test the setup_auth_frame method."""
    chat_client.setup_auth_frame()
    assert hasattr(chat_client, 'username_entry')
    assert hasattr(chat_client, 'password_entry')

def test_setup_chat_frame(chat_client):
    """Test the setup_chat_frame method."""
    chat_client.setup_chat_frame()
    assert hasattr(chat_client, 'messages_canvas')
    assert hasattr(chat_client, 'messages_frame')
    assert hasattr(chat_client, 'msg_count')

def test_setup_accounts_frame(chat_client):
    """Test the setup_accounts_frame method."""
    chat_client.setup_accounts_frame()
    assert hasattr(chat_client, 'accounts_list')
    assert hasattr(chat_client, 'search_var')
    assert hasattr(chat_client, 'recipient_var')

def test_create_account(chat_client):
    """Test the create_account method."""
    chat_client.username_entry = MagicMock()
    chat_client.username_entry.get.return_value = "testuser"
    chat_client.password_entry = MagicMock()
    chat_client.password_entry.get.return_value = "testpass"
    chat_client.send_command = MagicMock()
    chat_client.create_account()
    chat_client.send_command.assert_called_with({
        "cmd": "create",
        "username": "testuser",
        "password": "testpass"
    })

def test_login(chat_client):
    """Test the login method."""
    chat_client.username_entry = MagicMock()
    chat_client.username_entry.get.return_value = "testuser"
    chat_client.password_entry = MagicMock()
    chat_client.password_entry.get.return_value = "testpass"
    chat_client.send_command = MagicMock()
    chat_client.login()
    chat_client.send_command.assert_called_with({
        "cmd": "login",
        "username": "testuser",
        "password": "testpass"
    })

def test_send_message(chat_client):
    """Test the send_message method."""
    chat_client.username = "testuser"
    chat_client.recipient_var = MagicMock()
    chat_client.recipient_var.get.return_value = "recipient"
    chat_client.message_text = MagicMock()
    chat_client.message_text.get.return_value = "Hello"
    chat_client.send_command = MagicMock()
    chat_client.send_message()
    chat_client.send_command.assert_called_with({
        "cmd": "send",
        "to": "recipient",
        "content": "Hello"
    })

def test_delete_message(chat_client):
    """Test the delete_message method."""
    chat_client.send_command = MagicMock()
    chat_client.messages_frame = MagicMock()
    chat_client.messages_frame.winfo_children.return_value = [MagicMock()]
    with patch('tkinter.messagebox.askyesno', return_value=True):
        chat_client.delete_message(1)
    chat_client.send_command.assert_called_with({
        "cmd": "delete_messages",
        "message_ids": [1]
    })


def test_refresh_messages(chat_client):
    """Test the refresh_messages method."""
    chat_client.msg_count = MagicMock()
    chat_client.msg_count.get.return_value = "10"
    chat_client.send_command = MagicMock()
    chat_client.refresh_messages()
    chat_client.send_command.assert_called_with({
        "cmd": "get_messages",
        "count": 10
    })

def test_refresh_unread_messages(chat_client):
    """Test the refresh_unread_messages method."""
    chat_client.msg_count = MagicMock()
    chat_client.msg_count.get.return_value = "10"
    chat_client.send_command = MagicMock()
    chat_client.refresh_unread_messages()
    chat_client.send_command.assert_called_with({
        "cmd": "get_undelivered",
        "count": 10
    })

def test_search_accounts(chat_client):
    """Test the search_accounts method."""
    chat_client.search_var = MagicMock()
    chat_client.search_var.get.return_value = "test"
    chat_client.send_command = MagicMock()
    chat_client.search_accounts()
    chat_client.send_command.assert_called_with({
        "cmd": "list",
        "pattern": "test*"
    })

def test_delete_account(chat_client):
    """Test the delete_account method."""
    chat_client.username = "testuser"
    chat_client.delete_password = MagicMock()
    chat_client.delete_password.get.return_value = "testpass"
    chat_client.send_command = MagicMock()
    with patch('tkinter.messagebox.askyesno', return_value=True):
        chat_client.delete_account()
    chat_client.send_command.assert_called_with({
        "cmd": "delete_account",
        "password": "testpass"
    })

def test_logout(chat_client):
    """Test the logout method."""
    chat_client.username = "testuser"
    chat_client.send_command = MagicMock()
    chat_client.logout()
    chat_client.send_command.assert_called_with({"cmd": "logout"})

def test_run(chat_client):
    """Test the run method."""
    chat_client.root = MagicMock()
    chat_client.run()
    chat_client.root.after.assert_called()
    chat_client.root.mainloop.assert_called_once()