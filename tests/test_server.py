import pytest
from server import ChatServer
import threading

@pytest.fixture(scope="module", autouse=True)
def setup_server():
    """Starts the server in a background thread for testing."""
    server = ChatServer(use_json=True)  # Test both protocols
    threading.Thread(target=server.start, daemon=True).start()

@pytest.fixture
def mock_database(monkeypatch):
    """Mocks the database layer to isolate tests."""
    class MockDatabase:
        def create_account(self, username, password):
            return username != "existing_user"

        def login(self, username, password):
            return password == "valid_password"

        def send_message(self, sender, recipient, message):
            if message == "fail":
                raise Exception("Message Send Failure")
            return True

        def read_messages(self, username):
            return [("alice", "Hello!")] if username != "empty_user" else []

    monkeypatch.setattr("server.Database", MockDatabase)
    return MockDatabase()

def test_send_message(mock_database):
    """Tests sending messages, including failures and successful sends."""
    assert mock_database.send_message("alice", "bob", "Hello!")
    
    with pytest.raises(Exception, match="Message Send Failure"):
        mock_database.send_message("alice", "bob", "fail")

def test_read_messages(mock_database):
    """Tests reading received messages, including empty inbox scenarios."""
    assert mock_database.read_messages("bob") == [("alice", "Hello!")]
    assert mock_database.read_messages("empty_user") == []
