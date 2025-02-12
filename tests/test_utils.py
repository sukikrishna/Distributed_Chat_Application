import pytest
import time
import sys
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, "src/json_protocol")
from json_client import ChatClient

sys.path.insert(0, "src")
from utils import MessageFrame

@pytest.fixture
def root():
    return tk.Tk()

@pytest.fixture
def message_data():
    return {
        "id": 1,
        "timestamp": time.time(),
        "from": "user1",
        "content": "Hello, World!"
    }

def test_message_frame_initialization(root, message_data):
    # Test initialization of MessageFrame
    frame = MessageFrame(root, message_data)
    
    # Check if the frame is initialized with the correct message_id
    assert frame.message_id == message_data["id"]
    
    # Check if the select_var is initialized
    assert isinstance(frame.select_var, tk.BooleanVar)
    
    # Check if the header frame is created and packed
    header_frame = frame.winfo_children()[0]
    assert isinstance(header_frame, ttk.Frame)
    
    # Check if the select checkbox is created and packed
    select_cb = header_frame.winfo_children()[0]
    assert isinstance(select_cb, ttk.Checkbutton)
    
    # Check if the sender label is created and packed
    sender_label = header_frame.winfo_children()[1]
    assert isinstance(sender_label, ttk.Label)
    assert sender_label["text"].startswith(f"From: {message_data['from']} at")
    
    # Check if the content label is created and packed
    content_label = frame.winfo_children()[1]
    assert isinstance(content_label, ttk.Label)
    assert content_label["text"] == message_data["content"]
