# chat_gui.py

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json
import argparse
import configparser
from typing import Union, Optional
from t_custom_protocol import CustomProtocolClient
from json_protocol import JsonProtocolClient

class ChatGUI:
    def __init__(self, protocol_type: str = "json", config_file: Optional[str] = None):
        self.root = tk.Tk()
        self.root.title("Chat Application")
        self.root.geometry("800x600")
        
        # Initialize connection parameters
        self.host = "localhost"
        self.port = 54321
        
        # Load config if provided
        if config_file:
            self.load_config(config_file)
            
        # Initialize client based on protocol type
        if protocol_type.lower() == "json":
            self.client = JsonProtocolClient(self.host, self.port)
        else:
            self.client = CustomProtocolClient(self.host, self.port)
            
        self.setup_gui()
        self.connect_to_server()
        
    def load_config(self, config_file: str):
        """Load connection settings from config file"""
        config = configparser.ConfigParser()
        config.read(config_file)
        
        if 'Connection' in config:
            self.host = config['Connection'].get('host', self.host)
            self.port = config['Connection'].getint('port', self.port)
            
    def setup_gui(self):
        """Set up the GUI components"""
        # Create main container
        self.main_container = ttk.Frame(self.root, padding="10")
        self.main_container.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Create notebook for different sections
        self.notebook = ttk.Notebook(self.main_container)
        self.notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Login/Register tab
        self.auth_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.auth_frame, text="Login/Register")
        
        # Chat tab
        self.chat_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.chat_frame, text="Chat")
        
        # Setup authentication frame
        self.setup_auth_frame()
        
        # Setup chat frame
        self.setup_chat_frame()
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.main_container.columnconfigure(0, weight=1)
        self.main_container.rowconfigure(0, weight=1)
        
    def setup_auth_frame(self):
        """Set up the authentication frame"""
        # Username field
        ttk.Label(self.auth_frame, text="Username:").grid(row=0, column=0, pady=5)
        self.username_var = tk.StringVar()
        self.username_entry = ttk.Entry(self.auth_frame, textvariable=self.username_var)
        self.username_entry.grid(row=0, column=1, pady=5)
        
        # Password field
        ttk.Label(self.auth_frame, text="Password:").grid(row=1, column=0, pady=5)
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(self.auth_frame, textvariable=self.password_var, show="*")
        self.password_entry.grid(row=1, column=1, pady=5)
        
        # Buttons
        ttk.Button(self.auth_frame, text="Login", command=self.login).grid(row=2, column=0, pady=10)
        ttk.Button(self.auth_frame, text="Register", command=self.register).grid(row=2, column=1, pady=10)
        
    def setup_chat_frame(self):
        """Set up the chat frame"""
        # Message display area
        self.message_area = scrolledtext.ScrolledText(self.chat_frame, wrap=tk.WORD, height=20)
        self.message_area.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        # Recipient field
        ttk.Label(self.chat_frame, text="To:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.recipient_var = tk.StringVar()
        self.recipient_entry = ttk.Entry(self.chat_frame, textvariable=self.recipient_var)
        self.recipient_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # Message input field
        self.message_input = scrolledtext.ScrolledText(self.chat_frame, wrap=tk.WORD, height=3)
        self.message_input.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        # Send button
        ttk.Button(self.chat_frame, text="Send", command=self.send_message).grid(row=3, column=1, sticky=tk.E, pady=5)
        
        # Refresh button
        ttk.Button(self.chat_frame, text="Refresh Messages", command=self.refresh_messages).grid(row=3, column=0, sticky=tk.W, pady=5)
        
        # Configure grid weights for chat frame
        self.chat_frame.columnconfigure(1, weight=1)
        self.chat_frame.rowconfigure(0, weight=1)
        
    def connect_to_server(self):
        """Connect to the chat server"""
        if not self.client.connect():
            messagebox.showerror("Connection Error", "Failed to connect to server")
            self.root.quit()
            
    def login(self):
        """Handle login attempt"""
        username = self.username_var.get()
        password = self.password_var.get()
        
        response = self.client.login(username, password)
        if isinstance(response, dict):  # JSON protocol
            success = response["type"] == "success"
            message = response["payload"]["message"]
        else:  # Custom protocol
            success = "Login successful" in response
            message = response
            
        if success:
            messagebox.showinfo("Success", message)
            self.notebook.select(1)  # Switch to chat tab
            self.refresh_messages()
        else:
            messagebox.showerror("Error", message)
            
    def register(self):
        """Handle registration attempt"""
        username = self.username_var.get()
        password = self.password_var.get()
        
        response = self.client.create_account(username, password)
        if isinstance(response, dict):  # JSON protocol
            success = response["type"] == "success"
            message = response["payload"]["message"]
        else:  # Custom protocol
            success = "created successfully" in response
            message = response
            
        if success:
            messagebox.showinfo("Success", message)
        else:
            messagebox.showerror("Error", message)
            
    def send_message(self):
        """Send a message to another user"""
        recipient = self.recipient_var.get()
        message = self.message_input.get("1.0", tk.END).strip()
        
        if not recipient or not message:
            messagebox.showwarning("Warning", "Please enter both recipient and message")
            return
            
        if isinstance(self.client, JsonProtocolClient):
            response = self.client.send_chat_message(recipient, message)
            success = response["type"] == "success"
            message = response["payload"]["message"]
        else:
            response = self.client.send_message(recipient, message)
            success = "sent successfully" in response
            message = response
            
        if success:
            self.message_input.delete("1.0", tk.END)
            self.refresh_messages()
        else:
            messagebox.showerror("Error", message)
            
    def refresh_messages(self):
        """Fetch and display new messages"""
        response = self.client.read_messages()
        
        if isinstance(response, dict):  # JSON protocol
            if response["type"] == "success":
                messages = response["payload"]["messages"]
                for msg in messages:
                    self.display_message(msg["sender"], msg["message"])
        else:  # Custom protocol
            # Parse the custom protocol response
            if isinstance(response, str):
                messages = response.split("\n")
                for msg in messages:
                    if msg:
                        sender, content = msg.split(": ", 1)
                        self.display_message(sender, content)
                        
    def display_message(self, sender: str, message: str):
        """Display a message in the message area"""
        self.message_area.insert(tk.END, f"{sender}: {message}\n")
        self.message_area.see(tk.END)
        
    def run(self):
        """Start the GUI application"""
        self.root.mainloop()
        
if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Chat Client")
    parser.add_argument("--protocol", choices=["json", "custom"], default="json",
                      help="Protocol to use (json or custom)")
    parser.add_argument("--config", type=str, help="Path to config file")
    args = parser.parse_args()
    
    # Start the GUI
    gui = ChatGUI(protocol_type=args.protocol, config_file=args.config)
    gui.run()