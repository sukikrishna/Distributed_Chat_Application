import pytest
import grpc
import threading
import os
import sys
import hashlib
import time
from unittest.mock import MagicMock, patch

sys.path.insert(0, "src/grpc_protocol")

import chat_pb2 as chat
import chat_pb2_grpc as rpc
from grpc_server import ChatServer, serve

class MockContext:
    """Mock gRPC context for testing."""
    def __init__(self, peer="127.0.0.1:12345"):
        self._peer = peer
        self.is_active_value = True
        self.cancelled = False
        
    def peer(self):
        return self._peer
        
    def is_active(self):
        return self.is_active_value
        
    def cancel(self):
        self.cancelled = True

class MockRequestIterator:
    """Mock request iterator for testing stream functionality."""
    def __init__(self, requests):
        self.requests = requests
        self.index = 0
        
    def __iter__(self):
        return self
        
    def __next__(self):
        if self.index < len(self.requests):
            request = self.requests[self.index]
            self.index += 1
            return request
        raise StopIteration

@pytest.fixture
def chat_server():
    """Fixture to create a ChatServer instance."""
    server = ChatServer()
    yield server

def test_hash_password(chat_server):
    """Tests that password hashing works correctly."""
    password = "TestPassword123"
    hashed = chat_server.hash_password(password)
    # Verify it's a SHA-256 hash (64 hex characters)
    assert len(hashed) == 64
    # Verify it's deterministic
    assert hashed == chat_server.hash_password(password)

def test_validate_password(chat_server):
    """Tests password validation rules."""
    # Too short
    assert chat_server.validate_password("Short1") is False
    # No number
    assert chat_server.validate_password("NoNumberHere") is False
    # No uppercase
    assert chat_server.validate_password("nouppercase123") is False
    # Valid password
    assert chat_server.validate_password("ValidPassword123") is True

def test_create_account(chat_server):
    """Tests account creation functionality."""
    context = MockContext()
    request = chat.CreateAccount(username="testuser", password="TestPassword123")
    
    # Create a new account
    response = chat_server.SendCreateAccount(request, context)
    assert response.error is False
    assert "testuser" in chat_server.users
    
    # Attempt to create a duplicate account
    response = chat_server.SendCreateAccount(request, context)
    assert response.error is True
    assert "already exists" in response.message
    
    # Test with invalid password
    request = chat.CreateAccount(username="newuser", password="weak")
    response = chat_server.SendCreateAccount(request, context)
    assert response.error is True
    assert "Password must be" in response.message

def test_login(chat_server):
    """Tests login functionality."""
    context = MockContext()
    
    # Create test account
    chat_server.users["testuser"] = (chat_server.hash_password("TestPassword123"), {})
    
    # Test successful login
    request = chat.Login(username="testuser", password="TestPassword123")
    response = chat_server.SendLogin(request, context)
    assert response.error is False
    assert "testuser" in chat_server.active_users
    
    # Test login with wrong password
    request = chat.Login(username="testuser", password="WrongPassword123")
    response = chat_server.SendLogin(request, context)
    assert response.error is True
    assert "Invalid password" in response.message
    
    # Test login with non-existent user
    request = chat.Login(username="nonexistent", password="TestPassword123")
    response = chat_server.SendLogin(request, context)
    assert response.error is True
    assert "User not found" in response.message

def test_logout(chat_server):
    """Tests logout functionality."""
    context = MockContext()
    
    # Setup: create user and log in
    chat_server.users["testuser"] = (chat_server.hash_password("TestPassword123"), {})
    chat_server.active_users["testuser"] = True
    
    # Test successful logout
    request = chat.Logout(username="testuser")
    response = chat_server.SendLogout(request, context)
    assert response.error is False
    assert "testuser" not in chat_server.active_users
    
    # Test logout when not logged in
    request = chat.Logout(username="testuser")
    response = chat_server.SendLogout(request, context)
    assert response.error is True
    assert "Not logged in" in response.message

def test_delete_account(chat_server):
    """Tests account deletion functionality."""
    context = MockContext()
    
    # Setup: create user
    password = "TestPassword123"
    hashed_password = chat_server.hash_password(password)
    chat_server.users["testuser"] = (hashed_password, {})
    chat_server.active_users["testuser"] = True
    
    # Test with wrong password
    request = chat.DeleteAccount(username="testuser", password="WrongPassword")
    response = chat_server.SendDeleteAccount(request, context)
    assert response.error is True
    assert "Invalid password" in response.message
    
    # Test successful deletion
    request = chat.DeleteAccount(username="testuser", password=password)
    response = chat_server.SendDeleteAccount(request, context)
    assert response.error is False
    assert "testuser" not in chat_server.users
    assert "testuser" not in chat_server.active_users

def test_send_message(chat_server):
    """Tests message sending functionality."""
    context = MockContext()
    
    # Setup: create sender and recipient users
    chat_server.users["sender"] = (chat_server.hash_password("TestPassword123"), {})
    chat_server.users["recipient"] = (chat_server.hash_password("TestPassword123"), {})
    chat_server.active_users["sender"] = True
    
    # Test successful message sending
    request = chat.Message(
        username="sender", 
        to="recipient", 
        content="Hello, world!"
    )
    
    response = chat_server.SendMessage(request, context)
    assert response.error is False
    assert len(chat_server.messages["recipient"]) == 1
    assert chat_server.messages["recipient"][0]["content"] == "Hello, world!"
    assert chat_server.messages["recipient"][0]["from"] == "sender"
    assert chat_server.messages["recipient"][0]["read"] is False
    
    # Test sending message when not logged in
    del chat_server.active_users["sender"]
    response = chat_server.SendMessage(request, context)
    assert response.error is True
    assert "Not logged in" in response.message
    
    # Test sending message to non-existent recipient
    chat_server.active_users["sender"] = True
    request = chat.Message(username="sender", to="nonexistent", content="Hello")
    response = chat_server.SendMessage(request, context)
    assert response.error is True
    assert "Recipient not found" in response.message

def test_chat_stream(chat_server):
    """Tests the chat stream functionality."""
    context = MockContext()
    
    # Setup: Create users and messages
    chat_server.users["testuser"] = (chat_server.hash_password("TestPassword123"), {})
    chat_server.active_users["testuser"] = True
    
    # Add unread messages for the user
    chat_server.messages["testuser"] = [
        {
            "id": 1,
            "from": "sender",
            "to": "testuser",
            "content": "Hello",
            "timestamp": time.time(),
            "read": False,
            "delivered_while_offline": True
        }
    ]
    
    # Create a request iterator with the username
    requests = [chat.Id(username="testuser")]
    request_iterator = MockRequestIterator(requests)
    
    # Mock notifying users
    chat_server.notify_user_async = MagicMock()
    
    # Call ChatStream and get the generator
    stream_generator = chat_server.ChatStream(request_iterator, context)
    
    # Process a limited number of messages from the generator
    # We don't want to run an infinite loop, so we'll limit it
    messages = []
    try:
        # Use next() to get the first message or raise StopIteration
        message = next(stream_generator)
        messages.append(message)
    except StopIteration:
        pass
    
    # Check that we got messages from the stream
    assert len(messages) == 1
    assert messages[0].content == "Hello"
    assert messages[0].username == "sender"
    assert messages[0].to == "testuser"

def test_get_messages(chat_server):
    """Tests retrieving read messages for a user."""
    context = MockContext()
    
    # Setup: create user and add messages
    chat_server.users["testuser"] = (chat_server.hash_password("TestPassword123"), {})
    chat_server.active_users["testuser"] = True
    
    chat_server.messages["testuser"] = [
        {"id": 1, "from": "sender", "to": "testuser", "content": "Hello", 
         "timestamp": 1, "read": True, "delivered_while_offline": False},
        {"id": 2, "from": "sender", "to": "testuser", "content": "World", 
         "timestamp": 2, "read": True, "delivered_while_offline": False},
        {"id": 3, "from": "sender", "to": "testuser", "content": "Unread", 
         "timestamp": 3, "read": False, "delivered_while_offline": False}
    ]
    
    # Test getting messages
    request = chat.GetMessages(username="testuser", count=10)
    response = chat_server.SendGetMessages(request, context)
    
    assert response.error is False
    assert len(response.messages) == 2  # Only read messages
    
    # Check most recent message is first
    assert response.messages[0].content == "World"
    assert response.messages[0].id == 2
    assert response.messages[1].content == "Hello"
    assert response.messages[1].id == 1
    
    # Test when not logged in
    del chat_server.active_users["testuser"]
    response = chat_server.SendGetMessages(request, context)
    assert response.error is True

def test_get_undelivered_messages(chat_server):
    """Tests retrieving unread messages for a user."""
    context = MockContext()
    
    # Setup: create user and add messages
    chat_server.users["testuser"] = (chat_server.hash_password("TestPassword123"), {})
    chat_server.active_users["testuser"] = True
    
    chat_server.messages["testuser"] = [
        {"id": 1, "from": "sender", "to": "testuser", "content": "Read", 
         "timestamp": 1, "read": True, "delivered_while_offline": False},
        {"id": 2, "from": "sender", "to": "testuser", "content": "Unread1", 
         "timestamp": 2, "read": False, "delivered_while_offline": True},
        {"id": 3, "from": "sender", "to": "testuser", "content": "Unread2", 
         "timestamp": 3, "read": False, "delivered_while_offline": False}
    ]
    
    # Test getting unread messages
    request = chat.GetUndelivered(username="testuser", count=10)
    response = chat_server.SendGetUndelivered(request, context)
    
    assert response.error is False
    assert len(response.messages) == 2  # Only unread messages
    
    # Check messages are sorted by timestamp (newest first)
    assert response.messages[0].content == "Unread2"
    assert response.messages[0].id == 3
    assert response.messages[1].content == "Unread1"
    assert response.messages[1].id == 2
    
    # Verify messages are marked as read
    assert chat_server.messages["testuser"][1]["read"] is True
    assert chat_server.messages["testuser"][2]["read"] is True
    
    # Test when not logged in
    del chat_server.active_users["testuser"]
    response = chat_server.SendGetUndelivered(request, context)
    assert response.error is True

def test_delete_messages(chat_server):
    """Tests deleting messages."""
    context = MockContext()
    
    # Setup: create user and add messages
    chat_server.users["testuser"] = (chat_server.hash_password("TestPassword123"), {})
    chat_server.active_users["testuser"] = True
    
    chat_server.messages["testuser"] = [
        {"id": 1, "from": "sender", "to": "testuser", "content": "Message1", 
         "timestamp": 1, "read": True, "delivered_while_offline": False},
        {"id": 2, "from": "sender", "to": "testuser", "content": "Message2", 
         "timestamp": 2, "read": True, "delivered_while_offline": False},
        {"id": 3, "from": "sender", "to": "testuser", "content": "Message3", 
         "timestamp": 3, "read": False, "delivered_while_offline": False}
    ]
    
    # Test deleting messages
    request = chat.DeleteMessages(username="testuser", message_ids=[1, 3])
    response = chat_server.SendDeleteMessages(request, context)
    
    assert response.error is False
    assert len(chat_server.messages["testuser"]) == 1
    assert chat_server.messages["testuser"][0]["id"] == 2
    
    # Test when not logged in
    del chat_server.active_users["testuser"]
    request = chat.DeleteMessages(username="testuser", message_ids=[2])
    response = chat_server.SendDeleteMessages(request, context)
    assert response.error is True

def test_list_accounts(chat_server):
    """Tests listing user accounts."""
    context = MockContext()
    
    # Setup: create users
    chat_server.users = {
        "user1": (chat_server.hash_password("TestPassword123"), {}),
        "user2": (chat_server.hash_password("TestPassword123"), {}),
        "admin": (chat_server.hash_password("TestPassword123"), {}),
        "tester": (chat_server.hash_password("TestPassword123"), {})
    }
    chat_server.active_users["user1"] = True
    
    # Test listing all users
    request = chat.ListAccounts(username="user1", wildcard="*")
    response = chat_server.SendListAccounts(request, context)
    
    assert response.error is False
    assert len(response.users) == 4
    
    # Verify online status
    user_statuses = {user.username: user.status for user in response.users}
    assert user_statuses["user1"] == "online"
    assert user_statuses["user2"] == "offline"
    
    # Test with wildcard pattern
    request = chat.ListAccounts(username="user1", wildcard="user*")
    response = chat_server.SendListAccounts(request, context)
    
    assert response.error is False
    assert len(response.users) == 2
    assert all(user.username.startswith("user") for user in response.users)

def test_get_unread_count(chat_server):
    """Tests unread message count retrieval."""
    chat_server.messages["user1"] = [
        {"id": 1, "read": False},
        {"id": 2, "read": True},
        {"id": 3, "read": False}
    ]
    assert chat_server.get_unread_count("user1") == 2

def test_serve():
    """Tests that the server can start and stop."""
    with patch('grpc.server') as mock_server, \
         patch('grpc.insecure_channel') as mock_channel:
        
        # Mock the server and its methods
        mock_server_instance = mock_server.return_value
        mock_server_instance.add_insecure_port.return_value = 12345
        
        # Start server in a thread so we can stop it
        server_thread = threading.Thread(target=serve, args=('localhost', 50051))
        server_thread.daemon = True
        server_thread.start()
        
        # Allow the server to start
        time.sleep(0.1)
        
        # Verify server was started
        assert mock_server.called
        assert mock_server_instance.start.called
        
        # Stop the thread
        server_thread.join(timeout=0.5)