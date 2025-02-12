import pytest
import tkinter as tk
from tkinter import ttk
import time
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.utils import MessageFrame

@pytest.fixture(scope="function")
def root():
    root = tk.Tk()
    yield root
    root.destroy()

@pytest.fixture
def message_data():
    return {
        "id": "msg123",
        "from": "test_user",
        "content": "Hello, world!",
        "timestamp": time.time()
    }

def test_message_frame_creation(root, message_data):
    frame = MessageFrame(root, message_data)
    assert frame.message_id == message_data["id"]
    assert isinstance(frame.select_var, tk.BooleanVar)
    assert not frame.select_var.get()

def test_message_frame_content(root, message_data):
    frame = MessageFrame(root, message_data)
    labels = [widget for widget in frame.winfo_children() 
             if isinstance(widget, ttk.Label) or 
             isinstance(widget, ttk.Frame)]
    
    assert any(message_data["content"] in label.cget("text") 
              for label in labels if isinstance(label, ttk.Label))
    assert any(message_data["from"] in label.winfo_children()[1].cget("text") 
              for label in labels if isinstance(label, ttk.Frame))

def test_message_frame_timestamp_format(root, message_data):
    frame = MessageFrame(root, message_data)
    header_frame = frame.winfo_children()[0]
    sender_label = header_frame.winfo_children()[1]
    
    expected_time = time.strftime('%Y-%m-%d %H:%M:%S', 
                                time.localtime(message_data["timestamp"]))
    assert expected_time in sender_label.cget("text")

def test_message_frame_checkbox(root, message_data):
    frame = MessageFrame(root, message_data)
    header_frame = frame.winfo_children()[0]
    checkbox = header_frame.winfo_children()[0]
    
    assert isinstance(checkbox, ttk.Checkbutton)
    frame.select_var.set(True)
    assert frame.select_var.get()

def test_message_frame_wrap_length(root, message_data):
    frame = MessageFrame(root, message_data)
    content_label = [widget for widget in frame.winfo_children() 
                    if isinstance(widget, ttk.Label)][0]
    assert content_label.cget("wraplength") == 400