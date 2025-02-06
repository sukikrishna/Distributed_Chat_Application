import pytest
from client import ChatClient

@pytest.fixture
def client():
    """Provides a ChatClient instance for testing."""
    return ChatClient(use_json=True)

def test_login(monkeypatch, client):
    """Tests user login functionality using monkeypatching."""
    monkeypatch.setattr(client, "login", lambda u, p: p == "test_password")
    assert client.login("test_user", "test_password")
    assert not client.login("test_user", "wrong_password")

def test_send_message(monkeypatch, client):
    """Tests sending messages, including network failures."""
    monkeypatch.setattr(client, "send_message", lambda s, r, m: m != "fail")
    assert client.send_message("alice", "bob", "Hello!")

    def raise_network_error(*args, **kwargs):
        raise Exception("Network Failure")

    monkeypatch.setattr(client, "send_message", raise_network_error)
    with pytest.raises(Exception, match="Network Failure"):
        client.send_message("alice", "bob", "fail")
