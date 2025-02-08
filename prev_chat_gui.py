# chat_gui.py

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import time
from datetime import datetime
from custom_protocol import CustomProtocolClient

class ChatGUI:
    def __init__(self, host="localhost", port=5000):
        self.root = tk.Tk()
        self.root.title("Chat Application")
        self.root.geometry("800x600")
        
        self.client = CustomProtocolClient(host, port)
        self.current_chat_user = None
        self.message_update_thread = None
        self.message_update_active = False
        
        # chat_gui.py (continued)

        self.setup_gui()
        self.connect_to_server()
        
    def setup_gui(self):
        self.main_container = ttk.Frame(self.root, padding="10")
        self.main_container.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.notebook = ttk.Notebook(self.main_container)
        self.notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.auth_frame = ttk.Frame(self.notebook, padding="10")
        self.chat_frame = ttk.Frame(self.notebook, padding="10")
        self.accounts_frame = ttk.Frame(self.notebook, padding="10")
        
        self.notebook.add(self.auth_frame, text="Login/Register")
        self.notebook.add(self.accounts_frame, text="Accounts")
        self.notebook.add(self.chat_frame, text="Chat")
        
        self.setup_auth_frame()
        self.setup_accounts_frame()
        self.setup_chat_frame()
        
        self.configure_grid_weights()

    def configure_grid_weights(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.main_container.columnconfigure(0, weight=1)
        self.main_container.rowconfigure(0, weight=1)
        
    def setup_auth_frame(self):
        ttk.Label(self.auth_frame, text="Username:").grid(row=0, column=0, pady=5)
        self.username_var = tk.StringVar()
        self.username_entry = ttk.Entry(self.auth_frame, textvariable=self.username_var)
        self.username_entry.grid(row=0, column=1, pady=5)
        
        ttk.Label(self.auth_frame, text="Password:").grid(row=1, column=0, pady=5)
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(self.auth_frame, textvariable=self.password_var, show="*")
        self.password_entry.grid(row=1, column=1, pady=5)
        
        ttk.Button(self.auth_frame, text="Login", command=self.login).grid(row=2, column=0, pady=10)
        ttk.Button(self.auth_frame, text="Register", command=self.register).grid(row=2, column=1, pady=10)
        
    def setup_accounts_frame(self):
        search_frame = ttk.Frame(self.accounts_frame)
        search_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=5)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        self.search_entry.bind('<Return>', lambda e: self.search_accounts())
        ttk.Button(search_frame, text="Search", command=self.search_accounts).pack(side=tk.LEFT, padx=5)
        
        columns = ('username', 'status', 'unread')
        self.accounts_tree = ttk.Treeview(self.accounts_frame, columns=columns, show='headings')
        
        for col in columns:
            self.accounts_tree.heading(col, text=col.title())
            self.accounts_tree.column(col, width=100)
        
        self.accounts_tree.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        scrollbar = ttk.Scrollbar(self.accounts_frame, orient=tk.VERTICAL, command=self.accounts_tree.yview)
        scrollbar.grid(row=1, column=2, sticky=(tk.N, tk.S))
        self.accounts_tree.configure(yscrollcommand=scrollbar.set)
        
        self.accounts_tree.bind('<Double-1>', lambda e: self.start_chat())
        ttk.Button(self.accounts_frame, text="Start Chat", command=self.start_chat).grid(row=2, column=0, columnspan=2, pady=5)
        
    def setup_chat_frame(self):
        self.chat_header = ttk.Label(self.chat_frame, text="No chat selected", font=('', 12, 'bold'))
        self.chat_header.grid(row=0, column=0, columnspan=2, pady=5, sticky=tk.W)
        
        self.message_area = scrolledtext.ScrolledText(self.chat_frame, wrap=tk.WORD, height=20)
        self.message_area.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.message_area.tag_configure('timestamp', foreground='gray')
        self.message_area.tag_configure('sender', foreground='blue')
        
        self.message_input = scrolledtext.ScrolledText(self.chat_frame, wrap=tk.WORD, height=4)
        self.message_input.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=5)
        self.message_input.bind('<Return>', self.handle_return)
        
        ttk.Button(self.chat_frame, text="Send", command=self.send_message).grid(row=2, column=1, pady=5, padx=5)

    def connect_to_server(self):
        if not self.client.connect():
            messagebox.showerror("Connection Error", "Failed to connect to server")
            self.root.quit()

    def login(self):
        username = self.username_var.get()
        password = self.password_var.get()
        
        if not username or not password:
            messagebox.showwarning("Warning", "Please enter both username and password")
            return
            
        response = self.client.login(username, password)
        if "successful" in response:
            messagebox.showinfo("Success", response)
            self.start_message_updates()
            self.notebook.select(1)
            self.search_accounts()
        else:
            messagebox.showerror("Error", response)

    def register(self):
        username = self.username_var.get()
        password = self.password_var.get()
        
        if not username or not password:
            messagebox.showwarning("Warning", "Please enter both username and password")
            return
            
        response = self.client.create_account(username, password)
        if "successfully" in response:
            messagebox.showinfo("Success", response)
            self.login()
        else:
            messagebox.showerror("Error", response)

    def search_accounts(self):
        for item in self.accounts_tree.get_children():
            self.accounts_tree.delete(item)
            
        pattern = self.search_var.get()
        accounts = self.client.list_accounts(pattern)
        
        for account_info in accounts:
            if account_info:
                username, status, unread = account_info.split(':')
                self.accounts_tree.insert('', tk.END, values=(username, status, unread))

    def start_chat(self):
        selection = self.accounts_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a user to chat with")
            return
            
        self.current_chat_user = self.accounts_tree.item(selection[0])['values'][0]
        self.chat_header.config(text=f"Chat with {self.current_chat_user}")
        self.notebook.select(2)
        self.refresh_messages()

    def handle_return(self, event):
        if event.state & 0x1:  # Shift key is pressed
            return
        event.widget.delete("insert-1c")
        self.send_message()
        return "break"

    def send_message(self):
        if not self.current_chat_user:
            messagebox.showwarning("Warning", "No chat recipient selected")
            return
            
        message = self.message_input.get('1.0', tk.END).strip()
        if not message:
            return
            
        response = self.client.send_message(self.current_chat_user, message)
        if "successfully" in response:
            self.message_input.delete('1.0', tk.END)
            self.refresh_messages()
        else:
            messagebox.showerror("Error", response)

    def refresh_messages(self):
        self.message_area.delete('1.0', tk.END)
        messages = self.client.read_messages()
        
        for message in messages:
            if message:
                msg_id, sender, timestamp, content, source = message.split(':', 4)
                if sender == self.current_chat_user or (self.client.current_user == sender and 
                                                      self.current_chat_user == self.client.current_user):
                    time_str = datetime.fromtimestamp(float(timestamp)).strftime('%Y-%m-%d %H:%M')
                    self.message_area.insert(tk.END, f"{time_str} ", 'timestamp')
                    self.message_area.insert(tk.END, f"{sender}: ", 'sender')
                    self.message_area.insert(tk.END, f"{content}\n\n")
        
        self.message_area.see(tk.END)
        self.search_accounts()

    def start_message_updates(self):
        self.message_update_active = True
        self.message_update_thread = threading.Thread(target=self._update_messages)
        self.message_update_thread.daemon = True
        self.message_update_thread.start()

    def stop_message_updates(self):
        self.message_update_active = False
        if self.message_update_thread:
            self.message_update_thread.join(timeout=1.0)

    def _update_messages(self):
        while self.message_update_active:
            if self.current_chat_user:
                self.refresh_messages()
            self.search_accounts()
            time.sleep(5)

    def run(self):
        try:
            self.root.mainloop()
        finally:
            self.stop_message_updates()
            self.client.close()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Chat Client")
    parser.add_argument("--host", type=str, default="localhost", help="Server host")
    parser.add_argument("--port", type=int, default=5000, help="Server port")
    
    args = parser.parse_args()
    
    gui = ChatGUI(host=args.host, port=args.port)
    gui.run()