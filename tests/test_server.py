import pytest
from server import ChatServer
from client import ChatClient
import threading

def start_server():
    """Starts the chat server in a separate thread."""
    server = ChatServer(use_json=True)  # Set to False for Custom Binary Protocol
    threading.Thread(target=server.start, daemon=True).start()

@pytest.fixture(scope="module", autouse=True)
def setup_server():
    """Pytest fixture to set up the chat server before tests run."""
    start_server()

@pytest.fixture(scope="module")
def client():
    """Provides a ChatClient instance for testing.
    
    Returns:
        ChatClient: A client instance connected to the server.
    """
    return ChatClient(use_json=True)

def test_create_account(monkeypatch, client):
    """Tests account creation functionality using monkeypatching.
    
    Args:
        monkeypatch (pytest.MonkeyPatch): Pytest fixture for modifying behavior.
        client (ChatClient): The client instance used for testing.
    """
    monkeypatch.setattr(client, "create_account", lambda u, p: u != "existing_user")
    assert client.create_account("new_user", "password123")
    assert not client.create_account("existing_user", "password123")  # Duplicate username

def test_login(monkeypatch, client):
    """Tests user login functionality using monkeypatching.
    
    Args:
        monkeypatch (pytest.MonkeyPatch): Pytest fixture for modifying behavior.
        client (ChatClient): The client instance used for testing.
    """
    monkeypatch.setattr(client, "login", lambda u, p: p == "test_password")
    assert client.login("test_user", "test_password")
    assert not client.login("test_user", "wrong_password")  # Invalid credentials

def test_send_message(monkeypatch, client):
    """Tests sending a message using monkeypatching, including network failure scenarios.
    
    Args:
        monkeypatch (pytest.MonkeyPatch): Pytest fixture for modifying behavior.
        client (ChatClient): The client instance used for testing.
    """
    monkeypatch.setattr(client, "send_message", lambda s, r, m: m != "fail")
    assert client.send_message("test_user", "receiver", "Hello!")
    
    monkeypatch.setattr(client, "send_message", lambda s, r, m: (_ for _ in ()).throw(Exception("Network Failure")))
    with pytest.raises(Exception, match="Network Failure"):
        client.send_message("test_user", "receiver", "fail")

def test_read_messages(monkeypatch, client):
    """Tests reading received messages using monkeypatching, including empty inbox scenarios.
    
    Args:
        monkeypatch (pytest.MonkeyPatch): Pytest fixture for modifying behavior.
        client (ChatClient): The client instance used for testing.
    """
    monkeypatch.setattr(client, "read_messages", lambda u: [("sender", "Hello!")] if u != "empty_user" else [])
    messages = client.read_messages("receiver")
    assert isinstance(messages, list) and len(messages) > 0
    
    messages = client.read_messages("empty_user")
    assert messages == []
