import pytest
import grpc
import sys
import os
import time
import tkinter as tk
from tkinter import messagebox
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, "src/grpc_protocol")
import chat_pb2 as chat
import chat_pb2_grpc as rpc
from grpc_client import ChatClient

class MockStub:
    """Mock for the gRPC stub to simulate server interactions."""
    def __init__(self):
        self.SendCreateAccount = MagicMock()
        self.SendLogin = MagicMock()
        self.SendMessage = MagicMock()
        self.SendDeleteMessages = MagicMock()
        self.SendGetMessages = MagicMock()
        self.SendGetUndelivered = MagicMock()
        self.SendListAccounts = MagicMock()
        self.SendDeleteAccount = MagicMock()
        self.SendLogout = MagicMock()
        self.ChatStream = MagicMock()

@pytest.fixture
def chat_client():
    """Fixture to create a ChatClient instance with mocked gRPC connections."""
    with patch('tkinter.Tk'), \
         patch('grpc.insecure_channel') as mock_channel, \
         patch('grpc.channel_ready_future') as mock_future:
        
        # Mock the channel's readiness
        mock_future.return_value = MagicMock()
        
        # Create client and inject a mock stub
        client = ChatClient("127.0.0.1", 12345)
        client.stub = MockStub()
        client.root = MagicMock()
        client.running = True
        
        # Mock the UI elements
        client.username_entry = MagicMock()
        client.password_entry = MagicMock()
        client.recipient_var = MagicMock()
        client.message_text = MagicMock()
        client.msg_count = MagicMock()
        client.delete_password = MagicMock()
        client.search_var = MagicMock()
        client.messages_frame = MagicMock()
        client.accounts_list = MagicMock()
        client.notebook = MagicMock()
        client.status_var = MagicMock()
        client.user_count_var = MagicMock()
        client.online_count_var = MagicMock()
        
        # Mock messagebox to prevent UI dialogs
        with patch('tkinter.messagebox.showinfo'), \
             patch('tkinter.messagebox.showerror'), \
             patch('tkinter.messagebox.showwarning'), \
             patch('tkinter.messagebox.askyesno', return_value=True):
            
            yield client

def test_chat_client_initialization(chat_client):
    """Test the initialization of the ChatClient class."""
    assert chat_client.host == "127.0.0.1"
    assert chat_client.port == 12345
    assert chat_client.username is None
    assert chat_client.running is True

def test_create_account(chat_client):
    """Test the create_account method."""
    # Setup return value for the stub method
    chat_client.stub.SendCreateAccount.return_value = chat.Reply(
        error=False, 
        message="Account created successfully"
    )
    
    # Setup mock values
    chat_client.username_entry.get.return_value = "testuser"
    chat_client.password_entry.get.return_value = "TestPassword123"
    
    # Call the method
    chat_client.create_account()
    
    # Verify the stub was called with correct parameters
    chat_client.stub.SendCreateAccount.assert_called_once()
    args = chat_client.stub.SendCreateAccount.call_args[0][0]
    assert args.username == "testuser"
    assert args.password == "TestPassword123"

def test_create_account_empty_fields(chat_client):
    """Test create_account with empty fields."""
    chat_client.username_entry.get.return_value = ""
    chat_client.password_entry.get.return_value = ""
    
    with patch('tkinter.messagebox.showwarning') as mock_warning:
        chat_client.create_account()
        mock_warning.assert_called_once()
        assert "enter username and password" in mock_warning.call_args[0][1].lower()
    
    # Verify stub was not called
    chat_client.stub.SendCreateAccount.assert_not_called()

def test_login(chat_client):
    """Test the login method."""
    # Setup return value for the stub method
    chat_client.stub.SendLogin.return_value = chat.Reply(
        error=False, 
        message="Login successful. You have 2 unread messages."
    )
    
    # Setup mock values
    chat_client.username_entry.get.return_value = "testuser"
    chat_client.password_entry.get.return_value = "TestPassword123"
    
    # Call the method
    chat_client.login()
    
    # Verify the stub was called with correct parameters
    chat_client.stub.SendLogin.assert_called_once()
    args = chat_client.stub.SendLogin.call_args[0][0]
    assert args.username == "testuser"
    assert args.password == "TestPassword123"
    
    # Verify client state was updated
    assert chat_client.username == "testuser"
    chat_client.status_var.set.assert_called_once()
    chat_client.notebook.select.assert_called_once()

def test_login_empty_fields(chat_client):
    """Test login with empty fields."""
    chat_client.username_entry.get.return_value = ""
    chat_client.password_entry.get.return_value = ""
    
    with patch('tkinter.messagebox.showwarning') as mock_warning:
        chat_client.login()
        mock_warning.assert_called_once()
        assert "enter username and password" in mock_warning.call_args[0][1].lower()
    
    # Verify stub was not called
    chat_client.stub.SendLogin.assert_not_called()

def test_login_error(chat_client):
    """Test login with server error response."""
    # Setup error return value
    chat_client.stub.SendLogin.return_value = chat.Reply(
        error=True, 
        message="Invalid password"
    )
    
    # Setup mock values
    chat_client.username_entry.get.return_value = "testuser"
    chat_client.password_entry.get.return_value = "WrongPassword"
    
    with patch('tkinter.messagebox.showerror') as mock_error:
        chat_client.login()
        mock_error.assert_called_once()
        assert "Invalid password" in mock_error.call_args[0][1]
    
    # Verify username was not set
    assert chat_client.username is None

def test_send_message(chat_client):
    """Test the send_message method."""
    # Setup client state
    chat_client.username = "testuser"
    
    # Setup return value for the stub method
    chat_client.stub.SendMessage.return_value = chat.Reply(
        error=False, 
        message="Message sent"
    )
    
    # Setup mock values
    chat_client.recipient_var.get.return_value = "recipient"
    chat_client.message_text.get.return_value = "Hello, world!"
    
    # Call the method
    chat_client.send_message()
    
    # Verify the stub was called with correct parameters
    chat_client.stub.SendMessage.assert_called_once()
    args = chat_client.stub.SendMessage.call_args[0][0]
    assert args.username == "testuser"
    assert args.to == "recipient"
    assert args.content == "Hello, world!"
    
    # Verify text field was cleared
    chat_client.message_text.delete.assert_called_once()

def test_send_message_not_logged_in(chat_client):
    """Test send_message when not logged in."""
    # Setup client state
    chat_client.username = None
    
    with patch('tkinter.messagebox.showwarning') as mock_warning:
        chat_client.send_message()
        mock_warning.assert_called_once()
        assert "login first" in mock_warning.call_args[0][1].lower()
    
    # Verify stub was not called
    chat_client.stub.SendMessage.assert_not_called()

def test_send_message_empty_fields(chat_client):
    """Test send_message with empty fields."""
    # Setup client state
    chat_client.username = "testuser"
    
    # Setup mock values for empty fields
    chat_client.recipient_var.get.return_value = ""
    chat_client.message_text.get.return_value = ""
    
    with patch('tkinter.messagebox.showwarning') as mock_warning:
        chat_client.send_message()
        mock_warning.assert_called_once()
        assert "enter recipient and message" in mock_warning.call_args[0][1].lower()
    
    # Verify stub was not called
    chat_client.stub.SendMessage.assert_not_called()

def test_refresh_messages(chat_client):
    """Test the refresh_messages method."""
    # Setup client state
    chat_client.username = "testuser"
    
    # Setup mock values
    chat_client.msg_count.get.return_value = "10"
    
    # Setup mock messages
    mock_messages = [
        chat.Message(id=1, username="sender", to="testuser", content="Hello", timestamp=1, read=True),
        chat.Message(id=2, username="sender", to="testuser", content="World", timestamp=2, read=True)
    ]
    
    # Setup return value for the stub method
    chat_client.stub.SendGetMessages.return_value = chat.MessageList(
        error=False,
        messages=mock_messages
    )
    
    # Call the method
    chat_client.refresh_messages()
    
    # Verify the stub was called with correct parameters
    chat_client.stub.SendGetMessages.assert_called_once()
    args = chat_client.stub.SendGetMessages.call_args[0][0]
    assert args.username == "testuser"
    assert args.count == 10
    
    # Verify messages were cleared and processed
    chat_client.clear_messages.assert_called_once()

def test_refresh_messages_not_logged_in(chat_client):
    """Test refresh_messages when not logged in."""
    # Setup client state
    chat_client.username = None
    
    with patch('tkinter.messagebox.showwarning') as mock_warning:
        chat_client.refresh_messages()
        mock_warning.assert_called_once()
        assert "login first" in mock_warning.call_args[0][1].lower()
    
    # Verify stub was not called
    chat_client.stub.SendGetMessages.assert_not_called()

def test_refresh_unread_messages(chat_client):
    """Test the refresh_unread_messages method."""
    # Setup client state
    chat_client.username = "testuser"
    
    # Setup mock values
    chat_client.msg_count.get.return_value = "10"
    
    # Setup mock messages
    mock_messages = [
        chat.Message(id=1, username="sender", to="testuser", content="Hello", timestamp=1, read=False),
        chat.Message(id=2, username="sender", to="testuser", content="World", timestamp=2, read=False)
    ]
    
    # Setup return value for the stub method
    chat_client.stub.SendGetUndelivered.return_value = chat.MessageList(
        error=False,
        messages=mock_messages
    )
    
    # Call the method
    chat_client.refresh_unread_messages()
    
    # Verify the stub was called with correct parameters
    chat_client.stub.SendGetUndelivered.assert_called_once()
    args = chat_client.stub.SendGetUndelivered.call_args[0][0]
    assert args.username == "testuser"
    assert args.count == 10
    
    # Verify messages were cleared and processed
    chat_client.clear_messages.assert_called_once()

def test_search_accounts(chat_client):
    """Test the search_accounts method."""
    # Setup return value for the stub method
    mock_users = [
        chat.User(username="user1", status="online"),
        chat.User(username="user2", status="offline")
    ]
    
    chat_client.stub.SendListAccounts.return_value = chat.UserList(
        error=False,
        message="Found 2 users",
        users=mock_users
    )
    
    # Setup mock values
    chat_client.search_var.get.return_value = "user"
    
    # Call the method
    chat_client.search_accounts()
    
    # Verify the stub was called with correct parameters
    chat_client.stub.SendListAccounts.assert_called_once()
    args = chat_client.stub.SendListAccounts.call_args[0][0]
    assert args.wildcard == "user*"
    
    # Verify that user list was updated
    chat_client.accounts_list.delete.assert_called_once()
    assert chat_client.accounts_list.insert.call_count == 2
    
    # Verify user count updates
    chat_client.user_count_var.set.assert_called_once_with("Users found: 2")
    chat_client.online_count_var.set.assert_called_once_with("Online users: 1")

def test_on_user_select(chat_client):
    """Test the on_user_select method."""
    # Setup mock selection
    chat_client.accounts_list.selection.return_value = ["item1"]
    chat_client.accounts_list.item.return_value = {"values": ["testuser", "online"]}
    
    # Create a mock event
    event = MagicMock()
    
    # Call the method
    chat_client.on_user_select(event)
    
    # Verify recipient was set
    chat_client.recipient_var.set.assert_called_once_with("testuser")
    
    # Verify notebook was switched to chat tab
    chat_client.notebook.select.assert_called_once()

def test_delete_account(chat_client):
    """Test the delete_account method."""
    # Setup client state
    chat_client.username = "testuser"
    
    # Setup return value for the stub method
    chat_client.stub.SendDeleteAccount.return_value = chat.Reply(
        error=False, 
        message="Account deleted"
    )
    
    # Setup mock values
    chat_client.delete_password.get.return_value = "TestPassword123"
    
    with patch('tkinter.messagebox.askyesno', return_value=True):
        chat_client.delete_account()
    
    # Verify the stub was called with correct parameters
    chat_client.stub.SendDeleteAccount.assert_called_once()
    args = chat_client.stub.SendDeleteAccount.call_args[0][0]
    assert args.username == "testuser"
    assert args.password == "TestPassword123"
    
    # Verify client state was updated
    assert chat_client.username is None
    chat_client.status_var.set.assert_called_once()
    chat_client.notebook.select.assert_called_once()
    chat_client.clear_messages.assert_called_once()

def test_delete_account_not_logged_in(chat_client):
    """Test delete_account when not logged in."""
    # Setup client state
    chat_client.username = None
    
    with patch('tkinter.messagebox.showwarning') as mock_warning:
        chat_client.delete_account()
        mock_warning.assert_called_once()
        assert "login first" in mock_warning.call_args[0][1].lower()
    
    # Verify stub was not called
    chat_client.stub.SendDeleteAccount.assert_not_called()

def test_delete_account_empty_password(chat_client):
    """Test delete_account with empty password."""
    # Setup client state
    chat_client.username = "testuser"
    
    # Setup mock values
    chat_client.delete_password.get.return_value = ""
    
    with patch('tkinter.messagebox.showwarning') as mock_warning:
        chat_client.delete_account()
        mock_warning.assert_called_once()
        assert "enter your password" in mock_warning.call_args[0][1].lower()
    
    # Verify stub was not called
    chat_client.stub.SendDeleteAccount.assert_not_called()

def test_delete_account_canceled(chat_client):
    """Test delete_account when user cancels."""
    # Setup client state
    chat_client.username = "testuser"
    
    # Setup mock values
    chat_client.delete_password.get.return_value = "TestPassword123"
    
    with patch('tkinter.messagebox.askyesno', return_value=False):
        chat_client.delete_account()
    
    # Verify stub was not called
    chat_client.stub.SendDeleteAccount.assert_not_called()

def test_logout(chat_client):
    """Test the logout method."""
    # Setup client state
    chat_client.username = "testuser"
    
    # Setup return value for the stub method
    chat_client.stub.SendLogout.return_value = chat.Reply(
        error=False, 
        message="Logged out successfully"
    )
    
    # Call the method
    chat_client.logout()
    
    # Verify the stub was called with correct parameters
    chat_client.stub.SendLogout.assert_called_once()
    args = chat_client.stub.SendLogout.call_args[0][0]
    assert args.username == "testuser"
    
    # Verify client state was updated
    assert chat_client.username is None
    chat_client.status_var.set.assert_called_once()
    chat_client.notebook.select.assert_called_once()
    chat_client.clear_messages.assert_called_once()

def test_logout_not_logged_in(chat_client):
    """Test logout when not logged in."""
    # Setup client state
    chat_client.username = None
    
    with patch('tkinter.messagebox.showwarning') as mock_warning:
        chat_client.logout()
        mock_warning.assert_called_once()
        assert "not logged in" in mock_warning.call_args[0][1].lower()
    
    # Verify stub was not called
    chat_client.stub.SendLogout.assert_not_called()

def test_delete_message(chat_client):
    """Test the delete_message method."""
    # Setup client state
    chat_client.username = "testuser"
    
    # Setup return value for the stub method
    chat_client.stub.SendDeleteMessages.return_value = chat.Reply(
        error=False, 
        message="Messages deleted"
    )
    
    # Mock MessageFrame for testing removal
    class MockMessageFrame:
        def __init__(self, message_id):
            self.message_id = message_id
            self.destroy = MagicMock()
    
    # Add mock message frames to messages_frame
    msg_frame1 = MockMessageFrame(1)
    msg_frame2 = MockMessageFrame(2)
    chat_client.messages_frame.winfo_children.return_value = [msg_frame1, msg_frame2]
    
    with patch('tkinter.messagebox.askyesno', return_value=True):
        chat_client.delete_message(1)
    
    # Verify the stub was called with correct parameters
    chat_client.stub.SendDeleteMessages.assert_called_once()
    args = chat_client.stub.SendDeleteMessages.call_args[0][0]
    assert args.username == "testuser"
    assert list(args.message_ids) == [1]
    
    # Verify message frame was destroyed
    msg_frame1.destroy.assert_called_once()
    msg_frame2.destroy.assert_not_called()

def test_delete_message_canceled(chat_client):
    """Test delete_message when user cancels."""
    # Setup client state
    chat_client.username = "testuser"
    
    with patch('tkinter.messagebox.askyesno', return_value=False):
        chat_client.delete_message(1)
    
    # Verify stub was not called
    chat_client.stub.SendDeleteMessages.assert_not_called()

def test_delete_selected_messages(chat_client):
    """Test the delete_selected_messages method."""
    # Setup client state
    chat_client.username = "testuser"
    
    # Setup return value for the stub method
    chat_client.stub.SendDeleteMessages.return_value = chat.Reply(
        error=False, 
        message="Messages deleted"
    )
    
    # Mock MessageFrames with selection variables
    class MockMessageFrame:
        def __init__(self, message_id, selected):
            self.message_id = message_id
            self.select_var = MagicMock()
            self.select_var.get.return_value = selected
            self.destroy = MagicMock()
    
    # Add mock message frames to messages_frame
    msg_frame1 = MockMessageFrame(1, True)  # Selected
    msg_frame2 = MockMessageFrame(2, False) # Not selected
    msg_frame3 = MockMessageFrame(3, True)  # Selected
    chat_client.messages_frame.winfo_children.return_value = [msg_frame1, msg_frame2, msg_frame3]
    
    with patch('tkinter.messagebox.askyesno', return_value=True):
        chat_client.delete_selected_messages()
    
    # Verify the stub was called with correct parameters
    chat_client.stub.SendDeleteMessages.assert_called_once()
    args = chat_client.stub.SendDeleteMessages.call_args[0][0]
    assert args.username == "testuser"
    assert sorted(list(args.message_ids)) == [1, 3]
    
    # Verify message frames were destroyed
    msg_frame1.destroy.assert_called_once()
    msg_frame2.destroy.assert_not_called()
    msg_frame3.destroy.assert_called_once()

def test_delete_selected_messages_none_selected(chat_client):
    """Test delete_selected_messages when no messages are selected."""
    # Setup client state
    chat_client.username = "testuser"
    
    # Mock MessageFrames with no selection
    class MockMessageFrame:
        def __init__(self, message_id):
            self.message_id = message_id
            self.select_var = MagicMock()
            self.select_var.get.return_value = False
    
    # Add mock message frames to messages_frame
    chat_client.messages_frame.winfo_children.return_value = [
        MockMessageFrame(1),
        MockMessageFrame(2)
    ]
    
    # Call the method (no mock for askyesno needed since it won't be called)
    chat_client.delete_selected_messages()
    
    # Verify stub was not called
    chat_client.stub.SendDeleteMessages.assert_not_called()

def test_clear_messages(chat_client):
    """Test the clear_messages method."""
    # Mock message frames
    msg_frame1 = MagicMock()
    msg_frame2 = MagicMock()
    chat_client.messages_frame.winfo_children.return_value = [msg_frame1, msg_frame2]
    
    # Call the method
    chat_client.clear_messages()
    
    # Verify all message frames were destroyed
    msg_frame1.destroy.assert_called_once()
    msg_frame2.destroy.assert_called_once()

def test_handle_incoming_message(chat_client):
    """Test handling incoming messages from the stream."""
    # Create a mock message
    message = chat.Message(
        id=1,
        username="sender",
        to="testuser",
        content="Hello, world!",
        timestamp=123456789,
        read=False,
        delivered_while_offline=False
    )
    
    # Call the method
    with patch('tkinter.messagebox.showinfo') as mock_info:
        chat_client.handle_incoming_message(message)
        mock_info.assert_called_once()
        assert "New message" in mock_info.call_args[0][0]
        assert "sender" in mock_info.call_args[0][1]

def test_on_closing(chat_client):
    """Test the on_closing method."""
    # Setup client state
    chat_client.username = "testuser"
    chat_client.running = True
    
    # Call the method
    chat_client.on_closing()
    
    # Verify client state was updated
    assert chat_client.running is False
    
    # Verify logout was called
    chat_client.logout.assert_called_once()
    
    # Verify channel was closed and window destroyed
    chat_client.channel.close.assert_called_once()
    chat_client.root.destroy.assert_called_once()

def test_on_connection_lost(chat_client):
    """Test the on_connection_lost method."""
    # Setup client state
    chat_client.running = True
    
    # Call the method
    with patch('tkinter.messagebox.showerror') as mock_error:
        chat_client.on_connection_lost()
        mock_error.assert_called_once()
        assert "Connection to server lost" in mock_error.call_args[0][1]
    
    # Verify client state was updated
    assert chat_client.running is False
    
    # Verify window was destroyed
    chat_client.root.destroy.assert_called_once()

def test_entry_request_iterator(chat_client):
    """Test the entry_request_iterator method."""
    # Setup client state
    chat_client.username = "testuser"
    chat_client.running = True
    
    # Get the iterator
    iterator = chat_client.entry_request_iterator()
    
    # Get the first item
    request = next(iterator)
    
    # Verify request properties
    assert request.username == "testuser"
    
    # Change client state to stop iteration
    chat_client.running = False
    
    # Make sure we don't get any more items
    with pytest.raises(StopIteration):
        # Sleep a bit to ensure iteration stops
        time.sleep(0.6)
        next(iterator)

def test_start_message_stream(chat_client):
    """Test the start_message_stream method."""
    # Setup client state
    chat_client.username = "testuser"
    chat_client.running = True
    
    # Mock the stream responses
    mock_message = chat.Message(
        id=1,
        username="sender",
        to="testuser",
        content="Hello",
        timestamp=time.time(),
        read=False,
        delivered_while_offline=False
    )
    
    # Setup the ChatStream stub method to return an iterable of messages
    chat_client.stub.ChatStream.return_value = [mock_message]
    
    # Patch handle_incoming_message to check it's called
    with patch.object(chat_client, 'handle_incoming_message') as mock_handler:
        # Call the method in a thread so we can stop it
        thread = threading.Thread(target=chat_client.start_message_stream)
        thread.daemon = True
        thread.start()
        
        # Allow time for the message to be processed
        time.sleep(0.5)
        
        # Stop the thread
        chat_client.running = False
        thread.join(timeout=1)
        
        # Verify the message handler was called
        chat_client.root.after.assert_called()

def test_start_message_stream_error_handling(chat_client):
    """Test error handling in start_message_stream."""
    # Setup client state
    chat_client.username = "testuser"
    chat_client.running = True
    
    # Setup the ChatStream stub method to raise an exception
    chat_client.stub.ChatStream.side_effect = grpc.RpcError("Test error")
    
    # Call the method in a thread so we can stop it
    with patch('tkinter.messagebox.showerror') as mock_error:
        thread = threading.Thread(target=chat_client.start_message_stream)
        thread.daemon = True
        thread.start()
        
        # Allow time for the error to be processed
        time.sleep(0.5)
        
        # Stop the thread
        chat_client.running = False
        thread.join(timeout=1)
        
        # Verify error handling
        chat_client.root.after.assert_called()

def test_run(chat_client):
    """Test the run method."""
    # Call the method
    chat_client.run()
    
    # Verify periodic user updates are scheduled
    chat_client.root.after.assert_called()
    
    # Verify protocol handler is set
    chat_client.root.protocol.assert_called_once_with("WM_DELETE_WINDOW", chat_client.on_closing)
    
    # Verify search is initially performed
    chat_client.search_accounts.assert_called_once()
    
    # Verify mainloop is called
    chat_client.root.mainloop.assert_called_once()

def test_check_users_periodically(chat_client):
    """Test the check_users_periodically function in run method."""
    # Extract the function from run method by calling it and getting the first after callback
    chat_client.run()
    check_users_fn = chat_client.root.after.call_args[0][1]
    
    # Setup client state for testing
    chat_client.username = "testuser"
    chat_client.running = True
    
    # Reset mock to check new calls
    chat_client.search_accounts.reset_mock()
    chat_client.root.after.reset_mock()
    
    # Call the extracted function
    check_users_fn()
    
    # Verify it calls search_accounts
    chat_client.search_accounts.assert_called_once()
    
    # Verify it schedules itself again
    chat_client.root.after.assert_called_once_with(1000, check_users_fn)
    
    # Test when not logged in
    chat_client.username = None
    chat_client.search_accounts.reset_mock()
    chat_client.root.after.reset_mock()
    
    # Call the function
    check_users_fn()
    
    # Verify search_accounts was not called
    chat_client.search_accounts.assert_not_called()
    
    # Verify it doesn't schedule itself again
    chat_client.root.after.assert_not_called()

def test_main():
    """Test the main function."""
    # Mock command-line arguments
    test_args = ["grpc_client.py", "localhost", "--port", "50051"]
    
    with patch('sys.argv', test_args), \
         patch('argparse.ArgumentParser.parse_args') as mock_args, \
         patch('grpc_client.ChatClient') as mock_client:
        
        # Configure mock args
        mock_args.return_value = MagicMock(host="localhost", port=50051)
        
        # Mock client instance
        mock_client_instance = MagicMock()
        mock_client.return_value = mock_client_instance
        
        # Import main function
        from grpc_client import main
        
        # Call main
        main()
        
        # Verify ChatClient was created with correct parameters
        mock_client.assert_called_once_with("localhost", 50051)
        
        # Verify run was called
        mock_client_instance.run.assert_called_once()