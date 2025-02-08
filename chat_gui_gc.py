import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog
import socket
import threading
from custom_protocol import MessageType
import json

class ChatGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Chat Application")
        self.root.geometry("1000x600")

        self.host = "127.0.0.1"
        self.port = 50011
        self.username = None
        self.client_socket = None
        self.current_chat = None
        self.contacts = []
        self.logged_in = False

        self.setup_gui()

    def setup_gui(self):
        self.main_container = ttk.Frame(self.root, padding="10")
        self.main_container.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        self.notebook = ttk.Notebook(self.main_container)
        self.notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        self.accounts_frame = ttk.Frame(self.notebook, padding="10")
        self.chat_frame = ttk.Frame(self.notebook, padding="10")

        self.notebook.add(self.accounts_frame, text="Accounts")
        self.notebook.add(self.chat_frame, text="Messages")

        self.setup_accounts_frame()
        self.setup_chat_frame()

    def setup_accounts_frame(self):
        # Login Section
        login_frame = ttk.LabelFrame(self.accounts_frame, text="Login", padding="10")
        login_frame.grid(row=0, column=0, columnspan=2, pady=5, sticky=(tk.W, tk.E))

        ttk.Label(login_frame, text="Username:").grid(row=0, column=0, padx=5)
        self.username_entry = ttk.Entry(login_frame)
        self.username_entry.grid(row=0, column=1, padx=5)

        ttk.Label(login_frame, text="Password:").grid(row=1, column=0, padx=5)
        self.password_entry = ttk.Entry(login_frame, show="*")
        self.password_entry.grid(row=1, column=1, padx=5)

        button_frame = ttk.Frame(login_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=10)

        ttk.Button(button_frame, text="Login", command=self.login).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Create Account", command=self.create_account).pack(side=tk.LEFT, padx=5)

        # Chat Buttons Section
        buttons_frame = ttk.Frame(self.accounts_frame)
        buttons_frame.grid(row=1, column=0, columnspan=2, pady=5)

        ttk.Button(buttons_frame, text="Start Chat", command=self.start_chat).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Group Chat", command=self.start_group_chat).pack(side=tk.LEFT, padx=5)

        # Contacts Section
        contacts_frame = ttk.LabelFrame(self.accounts_frame, text="Contacts", padding="10")
        contacts_frame.grid(row=2, column=0, columnspan=2, pady=5, sticky=(tk.W, tk.E, tk.N, tk.S))

        self.contacts_listbox = tk.Listbox(contacts_frame, height=10)
        self.contacts_listbox.pack(fill=tk.BOTH, expand=True)

    def setup_chat_frame(self):
        self.chat_header = ttk.Label(self.chat_frame, text="No chat selected", font=('', 12, 'bold'))
        self.chat_header.grid(row=0, column=0, columnspan=2, pady=5, sticky=(tk.W))

        self.message_area = scrolledtext.ScrolledText(self.chat_frame, wrap=tk.WORD)
        self.message_area.grid(row=1, column=0, columnspan=2, pady=5)
        self.message_area.tag_configure('right', justify='right')
        self.message_area.tag_configure('left', justify='left')

        self.message_input = scrolledtext.ScrolledText(self.chat_frame, wrap=tk.WORD, height=4)
        self.message_input.grid(row=2, column=0, pady=5)

        send_button = ttk.Button(self.chat_frame, text="Send", command=self.send_message)
        send_button.grid(row=2, column=1, pady=5, padx=5)

    def create_account(self):
        username = self.username_entry.get()
        password = self.password_entry.get()

        if not username or not password:
            messagebox.showerror("Error", "Please enter both username and password")
            return

        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((self.host, self.port))
            
            # Send create account request
            message = f"CREATE:{username}:{password}"
            self.client_socket.send(message.encode())
            
            # Get response
            response = self.client_socket.recv(1024).decode()
            if response == "SUCCESS":
                messagebox.showinfo("Success", "Account created successfully")
            else:
                messagebox.showerror("Error", response)
                
        except Exception as e:
            messagebox.showerror("Error", f"Could not connect to server: {str(e)}")
        finally:
            if self.client_socket:
                self.client_socket.close()

    def login(self):
        username = self.username_entry.get()
        password = self.password_entry.get()

        if not username or not password:
            messagebox.showerror("Error", "Please enter both username and password")
            return

        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((self.host, self.port))
            
            # Send login request
            message = f"LOGIN:{username}:{password}"
            self.client_socket.send(message.encode())
            
            # Get response
            response = self.client_socket.recv(1024).decode()
            if response == "SUCCESS":
                self.username = username
                self.logged_in = True
                messagebox.showinfo("Success", "Logged in successfully")
                self.update_contacts()
            else:
                messagebox.showerror("Error", response)
                
        except Exception as e:
            messagebox.showerror("Error", f"Could not connect to server: {str(e)}")

    def update_contacts(self):
        try:
            self.client_socket.send("LIST_ACCOUNTS".encode())
            response = self.client_socket.recv(1024).decode()
            self.contacts = json.loads(response)
            
            self.contacts_listbox.delete(0, tk.END)
            for contact in self.contacts:
                if contact != self.username:
                    self.contacts_listbox.insert(tk.END, contact)
                    
        except Exception as e:
            messagebox.showerror("Error", f"Could not update contacts: {str(e)}")

    def start_chat(self):
        if not self.logged_in:
            messagebox.showerror("Error", "Please login first")
            return

        selected = self.contacts_listbox.curselection()
        if not selected:
            messagebox.showerror("Error", "Please select a contact")
            return

        recipient = self.contacts_listbox.get(selected[0])
        self.current_chat = recipient
        self.chat_header.config(text=f"Chat with {recipient}")
        self.message_area.delete('1.0', tk.END)
        self.notebook.select(1)  # Switch to chat tab

        # Start receiving messages for private chat
        threading.Thread(target=self.receive_messages, daemon=True).start()

    def start_group_chat(self):
        """Start a group chat session."""
        if not self.logged_in:
            messagebox.showerror("Error", "Please login first")
            return

        if self.client_socket:
            self.client_socket.close()

        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.client_socket.connect((self.host, self.port))
            self.client_socket.send(f"GROUP_CHAT:{self.username}".encode())
            
            self.current_chat = "GROUP"
            self.chat_header.config(text="Group Chat")
            self.message_area.delete('1.0', tk.END)
            self.message_area.insert(tk.END, "Connected to group chat!\n")
            
            # Switch to chat tab
            self.notebook.select(1)
            
            # Start receiving messages
            threading.Thread(target=self.receive_messages, daemon=True).start()
            
        except ConnectionRefusedError:
            messagebox.showerror("Error", "Could not connect to server")
            return

    def receive_messages(self):
        """Receive messages from the server."""
        while True:
            try:
                message = self.client_socket.recv(1024).decode()
                if not message:
                    break
                
                # Parse the message to determine if it's from the current user
                if ': ' in message:
                    username = message.split(': ')[0]
                    if username.startswith('['):  # Remove timestamp if present
                        username = username.split('] ')[1]
                    
                    # Apply different alignment based on sender
                    if username == self.username:
                        self.message_area.insert(tk.END, message + "\n", 'right')
                    else:
                        self.message_area.insert(tk.END, message + "\n", 'left')
                else:
                    # System messages or notifications
                    self.message_area.insert(tk.END, message + "\n")
                    
                self.message_area.yview(tk.END)
                
            except (ConnectionResetError, OSError):
                self.message_area.insert(tk.END, "Disconnected from server\n")
                break

    def send_message(self):
        """Send a message to the current chat."""
        if not self.client_socket:
            messagebox.showerror("Error", "Not connected to any chat")
            return

        message = self.message_input.get("1.0", tk.END).strip()
        if message:
            try:
                if self.current_chat == "GROUP":
                    self.client_socket.send(message.encode())
                else:
                    # Private chat message format
                    formatted_message = f"MSG:{self.current_chat}:{message}"
                    self.client_socket.send(formatted_message.encode())
                self.message_input.delete("1.0", tk.END)
            except (ConnectionResetError, OSError):
                messagebox.showerror("Error", "Connection lost")

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    chat_gui = ChatGUI()
    chat_gui.run()