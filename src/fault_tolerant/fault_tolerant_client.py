#!/usr/bin/env python3
"""
Fault-tolerant chat client for connecting to the replicated chat server.
This client can automatically reconnect to an alternative server if the current one fails.
"""
import sys
import os
import grpc
import threading
import time
import json
import argparse
import logging
import tkinter as tk
from tkinter import ttk, messagebox

# Add the parent directory to sys.path to ensure we find our local modules
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)
sys.path.insert(0, os.path.dirname(parent_dir))  # For config

# Import our local modules
from config import Config
from util import MessageFrame

# Import gRPC modules
# sys.path.append(os.path.join(parent_dir, "gRPC_protocol"))
# import chat_pb2 as chat
# import chat_pb2_grpc as rpc

sys.path.append(os.path.join(current_dir))
import chat_extended_pb2 as chat
import chat_extended_pb2_grpc as rpc


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(parent_dir), "logs", "client.log")),
        logging.StreamHandler()
    ]
)

class FaultTolerantChatClient:
    """A fault-tolerant chat client with automatic server failover.
    
    This client can automatically reconnect to an alternative server if the current one fails.
    It maintains a list of possible servers and tries them in order until a working one is found.
    
    Attributes:
        root: The tkinter root window
        server_list: List of server addresses to try connecting to
        current_server_index: Index of the currently connected server
        retries: Number of connection retries before giving up
        retry_delay: Delay between retries in seconds
        username: Current username if logged in
        running: Flag indicating if the client is running
        lock: Lock for thread-safe operations
    """
    
    def __init__(self, server_list=None, config_path=None):
        """Initialize the chat client.
        
        Args:
            server_list: List of server addresses in host:port format
            config_path: Path to configuration file with server list
        """
        self.root = tk.Tk()
        self.root.title("Fault-Tolerant Chat Application")
        self.root.geometry("1000x800")
        
        # Load configuration
        self.config = Config()
        
        # Server connection settings
        if server_list:
            self.server_list = server_list
        elif config_path:
            self.load_server_list(config_path)
        else:
            # Default to localhost with different ports
            self.server_list = ["127.0.0.1:50051", "127.0.0.1:50052", "127.0.0.1:50053"]
        
        self.current_server_index = 0
        self.retries = 3
        self.retry_delay = 2
        
        # Client state
        self.username = None
        self.running = True
        self.lock = threading.Lock()
        
        # Set up client UI
        self.setup_gui()
        
        # Connect to the first available server
        self.connect_to_server()
        
    def load_server_list(self, config_path):
        """Load server list from a configuration file.
        
        Args:
            config_path: Path to the configuration file
        """
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                
            self.server_list = []
            for server in config.get("servers", []):
                host = server.get("host")
                port = server.get("port")
                if host and port:
                    self.server_list.append(f"{host}:{port}")
                    
            if not self.server_list:
                logging.warning("No servers found in configuration file")
                self.server_list = ["127.0.0.1:50051"]
                
        except Exception as e:
            logging.error(f"Error loading server list: {e}")
            # Default to localhost
            self.server_list = ["127.0.0.1:50051"]
            
    def connect_to_server(self):
        """Connect to the best available server from the server list.
        
        Returns:
            bool: True if connection was successful, False otherwise
        """
        # Try the current server first
        server_attempts = list(range(len(self.server_list)))
        server_attempts.insert(0, server_attempts.pop(self.current_server_index))
        
        for i in server_attempts:
            server_address = self.server_list[i]
            logging.info(f"Attempting to connect to {server_address}")
            
            for retry in range(self.retries):
                try:
                    channel = grpc.insecure_channel(server_address)
                    self.stub = rpc.ChatServerStub(channel)
                    
                    # Test connection with a short timeout
                    grpc.channel_ready_future(channel).result(timeout=5)
                    
                    # Connection successful
                    self.current_server_index = i
                    self.channel = channel
                    
                    self.status_var.set(f"Connected to {server_address}")
                    logging.info(f"Successfully connected to {server_address}")
                    return True
                    
                except Exception as e:
                    logging.warning(f"Connection to {server_address} failed (attempt {retry+1}/{self.retries}): {e}")
                    time.sleep(self.retry_delay)
        
        # All servers failed
        messagebox.showerror("Connection Error", "Could not connect to any server.")
        self.status_var.set("Disconnected")
        return False
            
    def setup_gui(self):
        """Set up the graphical user interface."""
        style = ttk.Style()
        style.configure('Bold.TLabel', font=('TkDefaultFont', 9, 'bold'))
        
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill='both', padx=5, pady=5)
        
        self.auth_frame = ttk.Frame(self.notebook)
        self.chat_frame = ttk.Frame(self.notebook)
        self.accounts_frame = ttk.Frame(self.notebook)
        
        self.notebook.add(self.auth_frame, text='Login/Register')
        self.notebook.add(self.accounts_frame, text='Users')
        self.notebook.add(self.chat_frame, text='Chat')
        
        self.setup_auth_frame()
        self.setup_accounts_frame()
        self.setup_chat_frame()
        
        self.status_var = tk.StringVar(value="Not connected")
        self.server_var = tk.StringVar(value="")
        
        status_frame = ttk.Frame(self.root)
        status_frame.pack(side='bottom', fill='x', padx=5, pady=2)
        
        ttk.Label(status_frame, textvariable=self.status_var).pack(side='left')
        ttk.Label(status_frame, text=" | ").pack(side='left', padx=5)
        ttk.Label(status_frame, textvariable=self.server_var).pack(side='left')
        
        # Add reconnect button
        ttk.Button(status_frame, text="Reconnect", 
                  command=self.reconnect).pack(side='right', padx=5)
                  
    def reconnect(self):
        """Attempt to reconnect to the server."""
        if self.connect_to_server():
            messagebox.showinfo("Connection", f"Connected to server at {self.server_list[self.current_server_index]}")
            
            # Restart stream if logged in
            if self.username:
                # If there's an existing stream thread, interrupt it
                if hasattr(self, 'stream_thread') and self.stream_thread.is_alive():
                    self.stream_thread_stop = True
                    time.sleep(1)  # Give the thread time to stop
                
                # Start a new stream thread
                self.stream_thread_stop = False
                self.stream_thread = threading.Thread(target=self._start_stream, daemon=True)
                self.stream_thread.start()
                
                # Refresh user list
                self.search_accounts()
        
    def setup_auth_frame(self):
        """Configure the login and registration UI components."""
        frame = ttk.LabelFrame(self.auth_frame, text="Authentication", padding=10)
        frame.pack(expand=True, fill='both', padx=10, pady=10)
        
        ttk.Label(frame, text="Username:").pack(pady=5)
        self.username_entry = ttk.Entry(frame)
        self.username_entry.pack(pady=5)
        
        ttk.Label(frame, text="Password:").pack(pady=5)
        self.password_entry = ttk.Entry(frame, show="*")
        self.password_entry.pack(pady=5)
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Login", command=self.login).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Create Account", 
                  command=self.create_account).pack(side='left', padx=5)
        
    def setup_chat_frame(self):
        """Configure the chat window layout and message display."""
        left_frame = ttk.Frame(self.chat_frame)
        left_frame.pack(side='left', fill='both', expand=True)
        
        self.messages_canvas = tk.Canvas(left_frame)
        scrollbar = ttk.Scrollbar(left_frame, orient="vertical", 
                                command=self.messages_canvas.yview)
        
        self.messages_frame = ttk.Frame(self.messages_canvas)
        self.messages_frame.bind(
            "<Configure>",
            lambda e: self.messages_canvas.configure(
                scrollregion=self.messages_canvas.bbox("all")
            )
        )
        
        self.messages_canvas.create_window((0, 0), window=self.messages_frame, 
                                        anchor="nw", width=600)
        
        self.messages_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.messages_canvas.pack(side="left", fill="both", expand=True)
        
        right_frame = ttk.Frame(self.chat_frame, padding=5)
        right_frame.pack(side='right', fill='y')
        
        controls = ttk.LabelFrame(right_frame, text="Message Controls", padding=5)
        controls.pack(fill='x', pady=5)
        
        ttk.Label(controls, text="Unread messages to fetch:").pack()
        self.msg_count = ttk.Entry(controls, width=5)
        try:
            message_fetch_limit = self.config.get("message_fetch_limit")
        except:
            message_fetch_limit = 10  # Default value
        self.msg_count.insert(0, message_fetch_limit)
        self.msg_count.pack()
        
        ttk.Button(controls, text="Unread Messages", 
                command=self.refresh_unread_messages).pack(fill='x', pady=(5, 25))
        ttk.Button(controls, text="Message History", 
                command=self.refresh_messages).pack(fill='x', pady=10)
    
        ttk.Button(controls, text="Delete Selected Messages", 
                  command=self.delete_selected_messages).pack(fill='x', pady=5)

        delete_frame = ttk.LabelFrame(right_frame, text="Settings", padding=5)
        delete_frame.pack(fill='x', padx=5, pady=5)

        ttk.Label(delete_frame, text="Confirm password:").pack(anchor='w', padx=5, pady=2)
        self.delete_password = ttk.Entry(delete_frame, show="*")
        self.delete_password.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(delete_frame, text="Delete Account",
                  command=self.delete_account).pack(fill='x', padx=5, pady=5)
        
        ttk.Button(delete_frame, text="Logout",
            command=self.logout).pack(fill='x', pady=(25, 5))

    def setup_accounts_frame(self):
        """Configure the user search and account list UI."""
        controls_frame = ttk.Frame(self.accounts_frame)
        controls_frame.pack(fill='x', padx=5, pady=5)
        
        search_frame = ttk.LabelFrame(controls_frame, text="Search", padding=5)
        search_frame.pack(fill='x')
        
        ttk.Label(search_frame, text="Username:").pack(side='left', padx=5)
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side='left', fill='x', expand=True, padx=5)
        
        ttk.Button(search_frame, text="Search", 
                command=self.search_accounts).pack(side='right', padx=5)

        tree_frame = ttk.Frame(self.accounts_frame)
        tree_frame.pack(expand=True, fill='both', padx=5, pady=5)

        self.accounts_list = ttk.Treeview(tree_frame, 
                                        columns=('username', 'status'),
                                        show='headings',
                                        height=15)
                                        
        yscroll = ttk.Scrollbar(tree_frame, orient='vertical', 
                            command=self.accounts_list.yview)
        xscroll = ttk.Scrollbar(tree_frame, orient='horizontal', 
                            command=self.accounts_list.xview)
        
        self.accounts_list.configure(yscrollcommand=yscroll.set, 
                                xscrollcommand=xscroll.set)

        self.accounts_list.heading('username', text='Username')
        self.accounts_list.heading('status', text='Status')
        self.accounts_list.column('username', width=150, minwidth=100)
        self.accounts_list.column('status', width=100, minwidth=70)

        self.accounts_list.grid(row=0, column=0, sticky='nsew')
        yscroll.grid(row=0, column=1, sticky='ns')
        xscroll.grid(row=1, column=0, sticky='ew')

        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self.accounts_list.bind('<Double-1>', self.on_user_select)
        
        send_frame = ttk.LabelFrame(self.accounts_frame, text="Send Message (double click on username to select)", padding=5)
        send_frame.pack(fill='x', padx=5, pady=5)
        
        to_frame = ttk.Frame(send_frame)
        to_frame.pack(fill='x', pady=0)
        
        ttk.Label(to_frame, text="To:").pack(side='left', padx=(0, 5))
        self.recipient_var = tk.StringVar()
        self.recipient_entry = ttk.Entry(to_frame, textvariable=self.recipient_var, state='readonly')
        self.recipient_entry.pack(side='left', fill='x', expand=True)
        
        ttk.Label(send_frame).pack()
        self.message_text = tk.Text(send_frame, height=4, width=250)
        self.message_text.pack()
        
        ttk.Button(send_frame, text="Send", 
                command=self.send_message).pack(fill='x', pady=5)

        status_frame = ttk.Frame(self.accounts_frame)
        status_frame.pack(fill='x', padx=5, pady=5)
        
        # Create container for user counts
        counts_frame = ttk.Frame(status_frame)
        counts_frame.pack(side='left', fill='x')
        
        self.user_count_var = tk.StringVar(value="Users found: 0")
        self.online_count_var = tk.StringVar(value="Online users: 0")
        
        ttk.Label(status_frame, textvariable=self.user_count_var).pack(side='left')
        ttk.Label(status_frame, text=" | ").pack(side='left', padx=5)
        ttk.Label(status_frame, textvariable=self.online_count_var).pack(side='left')

    def _entry_request_iterator(self):
        """Creates an iterator that continuously sends username identification.
        
        Yields:
            Id: Username identification for the chat stream.
        """
        self.stream_thread_stop = False
        while self.running and self.username and not self.stream_thread_stop:
            yield chat.Id(username=self.username)
            time.sleep(0.5)  # Throttle rate of messages

    def _start_stream(self):
        """Starts a bidirectional stream to receive messages from the server."""
        if not self.username:
            return
            
        try:
            # Store the RPC context
            stream_responses = self.stub.ChatStream(
                self._entry_request_iterator()
            )
            
            # Process incoming messages
            for message in stream_responses:
                if not self.running or self.stream_thread_stop:
                    break
                self.root.after(0, self.handle_incoming_message, message)
                    
        except grpc.RpcError as e:
            if self.running and not self.stream_thread_stop:  # Only show errors if we're still supposed to be running
                self.root.after(0, lambda: messagebox.showerror("Connection Error", f"Lost connection to server: {e}"))
                self.root.after(0, self.on_connection_lost)
        except Exception as e:
            if self.running and not self.stream_thread_stop:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Error in message stream: {e}"))
                
    def handle_incoming_message(self, message):
        """Handles a message received from the chat stream.
        
        Args:
            message (Message): The received message.
        """
        # Convert protobuf message to dict for consistency with existing code
        msg_dict = {
            "id": message.id,
            "from": message.username,
            "to": message.to,
            "content": message.content,
            "timestamp": message.timestamp,
            "read": message.read,
            "delivered_while_offline": message.delivered_while_offline
        }
        
        # Display notification
        messagebox.showinfo("New Message", f"New message from {message.username}")

    def create_account(self):
        """Sends a request to the server to create a new account."""
        username = self.username_entry.get()
        password = self.password_entry.get()
        
        if not username or not password:
            messagebox.showwarning("Warning", "Please enter username and password")
            return
        
        try:
            request = chat.CreateAccount(username=username, password=password)
            response = self.stub.SendCreateAccount(request)
            
            if response.error:
                messagebox.showerror("Error", response.message)
            else:
                messagebox.showinfo("Account Created", "Account created successfully! Please log in to continue.")
        except grpc.RpcError as e:
            if "UNAVAILABLE" in str(e) and self.reconnect():
                # If connection failed but we reconnected successfully, try again
                self.create_account()
            else:
                messagebox.showerror("Error", f"Failed to create account: {e}")

    def login(self):
        """Sends a login request to the server."""
        username = self.username_entry.get()
        password = self.password_entry.get()
        
        if not username or not password:
            messagebox.showwarning("Warning", "Please enter username and password")
            return
        
        try:
            request = chat.Login(username=username, password=password)
            response = self.stub.SendLogin(request)
            
            if response.error:
                messagebox.showerror("Error", response.message)
            else:
                self.username = username
                self.status_var.set(f"Logged in as: {self.username}")
                self.server_var.set(f"Server: {self.server_list[self.current_server_index]}")
                self.notebook.select(1)  # Switch to Users tab
                
                # Start message stream
                self.stream_thread_stop = False
                self.stream_thread = threading.Thread(target=self._start_stream, daemon=True)
                self.stream_thread.start()
                
                # Search for users
                self.search_accounts()
                
                # Extract unread count from message
                if "You have" in response.message and "unread messages" in response.message:
                    try:
                        unread_count = int(response.message.split("You have ")[1].split(" unread")[0])
                        if unread_count > 0:
                            messagebox.showinfo("Messages", f"You have {unread_count} unread messages")
                    except:
                        pass
        except grpc.RpcError as e:
            if "UNAVAILABLE" in str(e) and self.reconnect():
                # If connection failed but we reconnected successfully, try again
                self.login()
            else:
                messagebox.showerror("Error", f"Failed to login: {e}")

    def send_message(self):
        """Sends a message to the selected recipient."""
        if not self.username:
            messagebox.showwarning("Warning", "Please login first")
            return
            
        recipient = self.recipient_var.get()
        message = self.message_text.get("1.0", tk.END).strip()
        
        if not recipient or not message:
            messagebox.showwarning("Warning", "Please enter recipient and message")
            return
        
        try:    
            request = chat.Message(
                username=self.username,
                to=recipient,
                content=message
            )
            response = self.stub.SendMessage(request)
            
            if response.error:
                messagebox.showerror("Error", response.message)
            else:
                self.message_text.delete("1.0", tk.END)
                # messagebox.showinfo("Success", "Message sent")
        except grpc.RpcError as e:
            if "UNAVAILABLE" in str(e) and self.reconnect():
                # If connection failed but we reconnected successfully, try again
                self.send_message()
            else:
                messagebox.showerror("Error", f"Failed to send message: {e}")

    def delete_message(self, msg_id):
        """Deletes a specific message.

        Args:
            msg_id (int): ID of the message to delete.
        """
        if messagebox.askyesno("Confirm", "Delete this message?"):
            try:
                request = chat.DeleteMessages(username=self.username, message_ids=[msg_id])
                response = self.stub.SendDeleteMessages(request)
                
                if response.error:
                    messagebox.showerror("Error", response.message)
                else:
                    # Remove the message frame immediately
                    for widget in self.messages_frame.winfo_children():
                        if isinstance(widget, MessageFrame) and getattr(widget, 'message_id', None) == msg_id:
                            widget.destroy()
                            break
            except grpc.RpcError as e:
                if "UNAVAILABLE" in str(e) and self.reconnect():
                    # If connection failed but we reconnected successfully, try again
                    self.delete_message(msg_id)
                else:
                    messagebox.showerror("Error", f"Failed to delete message: {e}")

    def delete_selected_messages(self):
        """Deletes all selected messages in the chat window."""
        selected_ids = []
        for widget in self.messages_frame.winfo_children():
            if isinstance(widget, MessageFrame) and widget.select_var.get():
                selected_ids.append(widget.message_id)
        
        if selected_ids:
            if messagebox.askyesno("Confirm", f"Delete {len(selected_ids)} selected messages?"):
                try:
                    request = chat.DeleteMessages(username=self.username, message_ids=selected_ids)
                    response = self.stub.SendDeleteMessages(request)
                    
                    if response.error:
                        messagebox.showerror("Error", response.message)
                    else:
                        # Remove the message frames immediately
                        for widget in self.messages_frame.winfo_children():
                            if isinstance(widget, MessageFrame) and widget.message_id in selected_ids:
                                widget.destroy()
                except grpc.RpcError as e:
                    if "UNAVAILABLE" in str(e) and self.reconnect():
                        # If connection failed but we reconnected successfully, try again
                        self.delete_selected_messages()
                    else:
                        messagebox.showerror("Error", f"Failed to delete messages: {e}")

    def refresh_messages(self):
        """Fetches and displays the message history."""
        if not self.username:
            messagebox.showwarning("Warning", "Please login first")
            return

        try:  
            count = int(self.msg_count.get())  
        except ValueError:  
            count = self.config.get("message_fetch_limit", 5)  
                
        try:  
            request = chat.GetMessages(username=self.username, count=count)  
            response = self.stub.SendGetMessages(request)  
            
            if response.error:  
                messagebox.showerror("Error", response.message)  
            else:  
                self.clear_messages()  
                
                # Only show read messages  
                for msg in response.messages:  
                    if msg.read:  
                        msg_dict = {  
                            "id": msg.id,  
                            "from": msg.username,  
                            "to": msg.to,  
                            "content": msg.content,  
                            "timestamp": msg.timestamp,  
                            "read": True,  
                            "delivered_while_offline": msg.delivered_while_offline  
                        }  
                        frame = MessageFrame(self.messages_frame, msg_dict)  
                        frame.message_id = msg.id  
                        frame.pack(fill='x', padx=5, pady=2)  
        except grpc.RpcError as e:  
            if "UNAVAILABLE" in str(e) and self.reconnect():
                # If connection failed but we reconnected successfully, try again
                self.refresh_messages()
            else:
                messagebox.showerror("Error", f"Failed to fetch messages: {e}")              

    def refresh_unread_messages(self):
        """Fetches and displays only unread messages."""
        if not self.username:
            messagebox.showwarning("Warning", "Please login first")
            return
        
        try:  
            count = int(self.msg_count.get())  
        except ValueError:  
            count = self.config.get("message_fetch_limit", 10)  
                
        try:  
            request = chat.GetUndelivered(username=self.username, count=count)  
            response = self.stub.SendGetUndelivered(request)  
            
            if response.error:  
                messagebox.showerror("Error", response.message)  
            else:  
                self.clear_messages()  
                
                # Display the messages  
                for msg in response.messages:  
                    msg_dict = {  
                        "id": msg.id,  
                        "from": msg.username,  
                        "to": msg.to,  
                        "content": msg.content,  
                        "timestamp": msg.timestamp,  
                        "read": True,  # Force read=True since they're now marked  
                        "delivered_while_offline": msg.delivered_while_offline  
                    }  
                    frame = MessageFrame(self.messages_frame, msg_dict)  
                    frame.message_id = msg.id  
                    frame.pack(fill='x', padx=5, pady=2)  
        except grpc.RpcError as e:  
            if "UNAVAILABLE" in str(e) and self.reconnect():
                # If connection failed but we reconnected successfully, try again
                self.refresh_unread_messages()
            else:
                messagebox.showerror("Error", f"Failed to fetch unread messages: {e}")             
                
    def on_user_select(self, event):
        """Handles user selection from the accounts list.

        Args:
            event (tk.Event): The triggered event.
        """
        selection = self.accounts_list.selection()
        if selection:
            item = self.accounts_list.item(selection[0])
            username = item['values'][0]
            self.recipient_var.set(username)
            self.notebook.select(2)  # Switch to chat tab

    def search_accounts(self):
        """Sends a request to the server to search for users."""
        pattern = self.search_var.get()
        if not pattern:
            pattern = "*"
        elif not pattern.endswith("*"):
            pattern = pattern + "*"
            
        try:
            request = chat.ListAccounts(username=self.username or "", wildcard=pattern)
            response = self.stub.SendListAccounts(request)
            
            self.accounts_list.delete(*self.accounts_list.get_children())
            
            for user in response.users:
                self.accounts_list.insert("", "end", values=(user.username, user.status))
            
            # Update both total and online user counts
            total_users = len(response.users)
            online_users = sum(1 for user in response.users if user.status == 'online')
            self.user_count_var.set(f"Users found: {total_users}")
            self.online_count_var.set(f"Online users: {online_users}")
        except grpc.RpcError as e:
            if "UNAVAILABLE" in str(e) and self.reconnect():
                # If connection failed but we reconnected successfully, try again
                self.search_accounts()
            else:
                if self.running:  # Only show errors if we're still running
                    messagebox.showerror("Error", f"Failed to search accounts: {e}")

    def delete_account(self):
        """Sends a request to the server to delete the user's account."""
        if not self.username:
            messagebox.showwarning("Warning", "Please login first")
            return
            
        password = self.delete_password.get()
        if not password:
            messagebox.showwarning("Warning", "Please enter your password")
            return
            
        if messagebox.askyesno("Confirm", 
                              "Delete your account? This cannot be undone."):
            try:
                request = chat.DeleteAccount(username=self.username, password=password)
                response = self.stub.SendDeleteAccount(request)
                
                if response.error:
                    messagebox.showerror("Error", response.message)
                else:
                    self.username = None
                    self.status_var.set("Not logged in")
                    self.notebook.select(0)  # Back to login tab
                    self.clear_messages()
                    messagebox.showinfo("Success", "Account deleted successfully")
            except grpc.RpcError as e:
                if "UNAVAILABLE" in str(e) and self.reconnect():
                    # If connection failed but we reconnected successfully, try again
                    self.delete_account()
                else:
                    messagebox.showerror("Error", f"Failed to delete account: {e}")

    def logout(self):
        """Logs out the current user from the server."""
        if not self.username:
            messagebox.showwarning("Warning", "Not logged in")
            return
            
        try:
            self.stream_thread_stop = True  # Signal stream thread to stop
            request = chat.Logout(username=self.username)
            response = self.stub.SendLogout(request)
            
            if response.error:
                messagebox.showerror("Error", response.message)
            else:
                self.username = None
                self.status_var.set("Not logged in")
                self.notebook.select(0)  # Back to login tab
                self.clear_messages()
                messagebox.showinfo("Logout", "Logged out successfully")
        except grpc.RpcError as e:
            if "UNAVAILABLE" in str(e) and self.reconnect():
                # If connection failed but we reconnected successfully, try again
                self.logout()
            else:
                messagebox.showerror("Error", f"Failed to logout: {e}")

    def clear_messages(self):
        """Clears all messages displayed in the chat window."""
        for widget in self.messages_frame.winfo_children():
            widget.destroy()

    def on_connection_lost(self):
        """Handles server disconnection and attempts to reconnect."""
        if self.running:
            logging.warning("Connection to server lost, attempting to reconnect...")
            if self.reconnect():
                messagebox.showinfo("Reconnected", f"Reconnected to server at {self.server_list[self.current_server_index]}")
                
                # Restart stream if logged in
                if self.username:
                    self.stream_thread_stop = False
                    self.stream_thread = threading.Thread(target=self._start_stream, daemon=True)
                    self.stream_thread.start()
            else:
                messagebox.showerror("Connection Error", "Could not reconnect to any server")

    def run(self):
        """Runs the chat client application."""
        def check_connection_periodically():
            """Periodically checks connection status."""
            if self.running and self.username:
                try:
                    # Try a simple operation to check connection
                    self.search_accounts()
                except:
                    # Connection might be lost, attempt to reconnect
                    self.on_connection_lost()
                    
                # Schedule next check
                self.root.after(30000, check_connection_periodically)  # Check every 30 seconds
            else:
                # Not logged in, check less frequently
                self.root.after(60000, check_connection_periodically)  # Check every minute

        # Start periodic connection check
        self.root.after(30000, check_connection_periodically)
        
        # Start main loop
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()

    def on_closing(self):
        """Handles cleanup when the chat window is closed."""
        self.running = False
        if self.username:
            try:
                self.logout()
            except:
                pass
        try:
            self.channel.close()
        except:
            pass
        self.root.destroy()

def main():
    """Parse command-line arguments and start the chat client."""
    parser = argparse.ArgumentParser(description="Fault-Tolerant Chat Client")
    parser.add_argument("--config", type=str, help="Path to server configuration file")
    parser.add_argument("--servers", type=str, nargs='+', help="List of server addresses (host:port)")
    
    args = parser.parse_args()
    
    if args.servers:
        server_list = args.servers
    else:
        server_list = None
        
    client = FaultTolerantChatClient(server_list=server_list, config_path=args.config)
    client.run()

if __name__ == "__main__":
    main()