import pytest
from database import Database

db = Database(db_name='test_chat.db')

@pytest.fixture(scope="module")
def database():
    """Provides a test database instance with monkeypatching.
    
    Returns:
        Database: A mocked database instance.
    """
    return db

def test_create_account(monkeypatch, database):
    """Tests account creation, including duplicate usernames, using monkeypatching.
    
    Args:
        monkeypatch (pytest.MonkeyPatch): Pytest fixture for modifying behavior.
        database (Database): The database instance used for testing.
    """
    monkeypatch.setattr(database, "create_account", lambda u, p: u != "existing_user")
    assert database.create_account("new_user", "password123")
    assert not database.create_account("existing_user", "password123")  # Duplicate username

def test_login(monkeypatch, database):
    """Tests user login validation, including invalid credentials, using monkeypatching.
    
    Args:
        monkeypatch (pytest.MonkeyPatch): Pytest fixture for modifying behavior.
        database (Database): The database instance used for testing.
    """
    monkeypatch.setattr(database, "login", lambda u, p: p == "test_password")
    assert database.login("test_user", "test_password")
    assert not database.login("test_user", "wrong_password")  # Invalid credentials

def test_send_message(monkeypatch, database):
    """Tests sending a message and handling network failures using monkeypatching.
    
    Args:
        monkeypatch (pytest.MonkeyPatch): Pytest fixture for modifying behavior.
        database (Database): The database instance used for testing.
    """
    monkeypatch.setattr(database, "send_message", lambda s, r, m: m != "fail")
    assert database.send_message("test_user", "receiver", "Hello!")
    
    monkeypatch.setattr(database, "send_message", lambda s, r, m: (_ for _ in ()).throw(Exception("Network Failure")))
    with pytest.raises(Exception, match="Network Failure"):
        database.send_message("test_user", "receiver", "fail")

def test_read_messages(monkeypatch, database):
    """Tests reading stored messages, including handling empty inboxes, using monkeypatching.
    
    Args:
        monkeypatch (pytest.MonkeyPatch): Pytest fixture for modifying behavior.
        database (Database): The database instance used for testing.
    """
    monkeypatch.setattr(database, "read_messages", lambda u: [("sender", "Hello!")] if u != "empty_user" else [])
    messages = database.read_messages("receiver")
    assert isinstance(messages, list) and len(messages) > 0
    
    messages = database.read_messages("empty_user")
    assert messages == []
