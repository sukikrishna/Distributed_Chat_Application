import pytest
from database import Database

@pytest.fixture
def mock_database(monkeypatch):
    """Mocks the database instance for testing."""
    class MockDatabase:
        def create_account(self, username, password):
            return username != "existing_user"

        def login(self, username, password):
            return password == "valid_password"

        def send_message(self, sender, recipient, message):
            if message == "fail":
                raise Exception("Database Error")
            return True

        def read_messages(self, username):
            return [("alice", "Hello!")] if username != "empty_user" else []

    monkeypatch.setattr("database.Database", MockDatabase)
    return MockDatabase()

def test_create_account(mock_database):
    """Tests account creation with database interaction."""
    assert mock_database.create_account("new_user", "password123")
    assert not mock_database.create_account("existing_user", "password123")

def test_read_messages(mock_database):
    """Tests reading received messages from the database."""
    assert mock_database.read_messages("bob") == [("alice", "Hello!")]
    assert mock_database.read_messages("empty_user") == []
