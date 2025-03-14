
import time

import tkinter as tk
from tkinter import ttk, messagebox

class MessageFrame(ttk.Frame):
    """Represents a message frame in the chat GUI."""

    def __init__(self, parent, message_data, on_select=None):
        """Initializes the message frame.

        Args:
            parent (tk.Widget): Parent widget.
            message_data (dict): Dictionary containing message details.
            on_select (function, optional): Callback function when the message is selected.
        """
        super().__init__(parent)
        
        self.configure(relief='raised', borderwidth=1, padding=5)
        self.message_id = message_data["id"]
        
        header_frame = ttk.Frame(self)
        header_frame.pack(fill='x', expand=True)
        
        self.select_var = tk.BooleanVar()
        select_cb = ttk.Checkbutton(header_frame, variable=self.select_var)
        select_cb.pack(side='left', padx=(0, 5))
        
        time_str = time.strftime('%Y-%m-%d %H:%M:%S', 
                               time.localtime(message_data["timestamp"]))
        sender_label = ttk.Label(
            header_frame, 
            text=f"From: {message_data['from']} at {time_str}",
            style='Bold.TLabel'
        )
        sender_label.pack(side='left')
    
        content = ttk.Label(
            self,
            text=message_data["content"],
            wraplength=400
        )
        content.pack(fill='x', pady=(5, 0))