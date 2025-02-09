import socket
import json
import threading
import tkinter as tk
import time
from tkinter import ttk, messagebox
from config import Config

class MessageFrame(ttk.Frame):
    def __init__(self, parent, message_data, on_delete=None):
        super().__init__(parent)
        
        self.configure(relief='raised', borderwidth=1, padding=5)
        
        header_frame = ttk.Frame(self)
        header_frame.pack(fill='x', expand=True)
        
        time_str = time.strftime('%Y-%m-%d %H:%M:%S', 
                               time.localtime(message_data["timestamp"]))
        sender_label = ttk.Label(
            header_frame, 
            text=f"From: {message_data['from']} at {time_str}",
            style='Bold.TLabel'
        )
        sender_label.pack(side='left')
        
        if on_delete:
            delete_btn = ttk.Button(
                header_frame,
                text="Delete",
                command=lambda: on_delete(message_data["id"])
            )
            delete_btn.pack(side='right')
        
        content = ttk.Label(
            self,
            text=message_data["content"],
            wraplength=400
        )
        content.pack(fill='x', pady=(5, 0))

class ChatClient:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Chat Application")
        self.root.geometry("1000x800")
        
        self.config = Config()
        self.host = self.config.get("host")
        self.port = self.config.get("port")
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.socket.connect((self.host, self.port))
        except ConnectionRefusedError:
            messagebox.showerror("Error", "Could not connect to server")
            self.root.destroy()
            return
            
        self.username = None
        self.known_users = set()  # Track known users for dropdown
        self.setup_gui()
        self.message_check_thread = None
        self.running = True
        threading.Thread(target=self.receive_messages, daemon=True).start()
        
    def setup_gui(self):
        style = ttk.Style()
        style.configure('Bold.TLabel', font=('TkDefaultFont', 9, 'bold'))
        
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill='both', padx=5, pady=5)
        
        self.auth_frame = ttk.Frame(self.notebook)
        self.chat_frame = ttk.Frame(self.notebook)
        self.accounts_frame = ttk.Frame(self.notebook)
        
        self.notebook.add(self.auth_frame, text='Login/Register')
        self.notebook.add(self.chat_frame, text='Chat')
        self.notebook.add(self.accounts_frame, text='Users')
        
        self.setup_auth_frame()
        self.setup_chat_frame()
        self.setup_accounts_frame()
        
        self.status_var = tk.StringVar(value="Not logged in")
        status = ttk.Label(self.root, textvariable=self.status_var)
        status.pack(side='bottom', fill='x', padx=5, pady=2)
        
    def setup_auth_frame(self):
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
        
        controls = ttk.LabelFrame(right_frame, text="Controls", padding=5)
        controls.pack(fill='x', pady=5)
        
        ttk.Label(controls, text="Messages to show:").pack()
        self.msg_count = ttk.Entry(controls, width=5)
        self.msg_count.insert(0, self.config.get("message_fetch_limit"))
        self.msg_count.pack()
        
        ttk.Button(controls, text="Check Messages", 
                  command=self.refresh_messages).pack(fill='x', pady=5)
        
        send_frame = ttk.LabelFrame(right_frame, text="Send Message", padding=5)
        send_frame.pack(fill='x', pady=5)
        
        ttk.Label(send_frame, text="To:").pack()
        self.recipient_var = tk.StringVar()
        self.recipient_combo = ttk.Combobox(send_frame, 
                                          textvariable=self.recipient_var,
                                          state='readonly')
        self.recipient_combo.pack(fill='x')
        
        ttk.Label(send_frame, text="Message:").pack()
        self.message_text = tk.Text(send_frame, height=4, width=30)
        self.message_text.pack()
        
        ttk.Button(send_frame, text="Send", 
                  command=self.send_message).pack(fill='x', pady=5)
                  
        ttk.Button(right_frame, text="Logout",
                  command=self.logout).pack(fill='x', pady=5)
                  
    def setup_accounts_frame(self):
        controls_frame = ttk.Frame(self.accounts_frame)
        controls_frame.pack(fill='x', padx=5, pady=5)
        
        search_frame = ttk.LabelFrame(controls_frame, text="Search", padding=5)
        search_frame.pack(fill='x')
        
        ttk.Label(search_frame, text="Pattern:").pack(side='left', padx=5)
        self.search_var = tk.StringVar()
        ttk.Entry(search_frame, textvariable=self.search_var).pack(side='left', 
                                                                fill='x', expand=True, padx=5)
        ttk.Button(search_frame, text="Search", 
                command=self.search_accounts).pack(side='right', padx=5)

        # Create container frame for Treeview and scrollbar
        tree_frame = ttk.Frame(self.accounts_frame)
        tree_frame.pack(expand=True, fill='both', padx=5, pady=5)

        # Create Treeview and scrollbars
        self.accounts_list = ttk.Treeview(tree_frame, 
                                        columns=('username', 'status'),
                                        show='headings',
                                        height=15)
                                        
        yscroll = ttk.Scrollbar(tree_frame, orient='vertical', 
                            command=self.accounts_list.yview)
        xscroll = ttk.Scrollbar(tree_frame, orient='horizontal', 
                            command=self.accounts_list.xview)
        
        # Configure scrollbars for Treeview
        self.accounts_list.configure(yscrollcommand=yscroll.set, 
                                xscrollcommand=xscroll.set)

        # Set column headings and widths
        self.accounts_list.heading('username', text='Username')
        self.accounts_list.heading('status', text='Status')
        self.accounts_list.column('username', width=150, minwidth=100)
        self.accounts_list.column('status', width=100, minwidth=70)

        self.accounts_list.pack(expand=True, fill='both', padx=5, pady=5)

        delete_frame = ttk.LabelFrame(self.accounts_frame, text="Delete Account", padding=5)
        delete_frame.pack(fill='x', padx=5, pady=5)

        ttk.Label(delete_frame, text="Confirm password:").pack()
        self.delete_password = ttk.Entry(delete_frame, show="*")
        self.delete_password.pack(fill='x', pady=5)

        ttk.Button(delete_frame, text="Delete Account",
                  command=self.delete_account).pack(fill='x')

        # Grid layout for Treeview and scrollbars
        self.accounts_list.grid(row=0, column=0, sticky='nsew')
        yscroll.grid(row=0, column=1, sticky='ns')
        xscroll.grid(row=1, column=0, sticky='ew')

        # Configure grid weights
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        # Bind double-click event
        self.accounts_list.bind('<Double-1>', self.on_user_select)

        # Status frame at bottom
        status_frame = ttk.Frame(self.accounts_frame)
        status_frame.pack(fill='x', padx=5, pady=5)
        self.user_count_var = tk.StringVar(value="Users found: 0")
        ttk.Label(status_frame, textvariable=self.user_count_var).pack(side='left')

    def create_account(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        
        if not username or not password:
            messagebox.showwarning("Warning", "Please enter username and password")
            return
        
        self.send_command({
            "cmd": "create",
            "username": username,
            "password": password
        })

    def login(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        
        if not username or not password:
            messagebox.showwarning("Warning", "Please enter username and password")
            return
        
        self.send_command({
            "cmd": "login",
            "username": username,
            "password": password
        })

    def send_message(self):
        if not self.username:
            messagebox.showwarning("Warning", "Please login first")
            return
            
        recipient = self.recipient_var.get()
        message = self.message_text.get("1.0", tk.END).strip()
        
        if not recipient or not message:
            messagebox.showwarning("Warning", "Please enter recipient and message")
            return
            
        self.send_command({
            "cmd": "send",
            "to": recipient,
            "content": message
        })
        
        self.message_text.delete("1.0", tk.END)

    def delete_message(self, msg_id):
        if messagebox.askyesno("Confirm", "Delete this message?"):
            self.send_command({
                "cmd": "delete_messages",
                "message_ids": [msg_id]
            })

    def refresh_messages(self):
        try:
            count = int(self.msg_count.get())
        except ValueError:
            count = self.config.get("message_fetch_limit")
            
        self.send_command({
            "cmd": "get_messages",
            "count": count
        })

    def on_user_select(self, event):
        selection = self.accounts_list.selection()
        if selection:
            item = self.accounts_list.item(selection[0])
            username = item['values'][0]
            self.recipient_var.set(username)
            self.notebook.select(1)  # Switch to chat tab

    def search_accounts(self):
        pattern = self.search_var.get()
        if pattern and not pattern.endswith("*"):
            pattern = pattern + "*"
        self.send_command({
            "cmd": "list",
            "pattern": pattern
        })

    def delete_account(self):
        if not self.username:
            messagebox.showwarning("Warning", "Please login first")
            return
            
        password = self.delete_password.get()
        if not password:
            messagebox.showwarning("Warning", "Please enter your password")
            return
            
        if messagebox.askyesno("Confirm", 
                              "Delete your account? This cannot be undone."):
            self.send_command({
                "cmd": "delete_account",
                "password": password
            })

    def logout(self):
        if self.username:
            self.send_command({"cmd": "logout"})

    def clear_messages(self):
        for widget in self.messages_frame.winfo_children():
            widget.destroy()

    def update_users_dropdown(self):
        if self.known_users:
            users = sorted(list(self.known_users))
            self.recipient_combo['values'] = users
            if users and not self.recipient_var.get():
                self.recipient_combo.set(users[0])

    def send_command(self, command):
        try:
            self.socket.send(json.dumps(command).encode())
        except Exception as e:
            messagebox.showerror("Error", f"Failed to send command: {e}")
            self.on_connection_lost()

    def receive_messages(self):
        while self.running:
            try:
                data = self.socket.recv(4096).decode()
                if not data:
                    self.on_connection_lost()
                    break
                    
                message = json.loads(data)
                self.root.after(0, self.handle_message, message)
                
            except Exception as e:
                if self.running:
                    print(f"Error receiving message: {e}")
                    self.root.after(0, self.on_connection_lost)
                break

    def handle_message(self, message):
        if message.get("success"):
            if "username" in message:  # Login/Create response
                if "unread" in message:  # This confirms it's a login response
                    self.username = message["username"]
                    self.status_var.set(f"Logged in as: {self.username}")
                    self.notebook.select(1)  # Switch to chat tab
                    messagebox.showinfo("Messages", f"You have {message['unread']} unread messages")
                    self.refresh_messages()
                else:
                    messagebox.showinfo("Account Created", 
                                        "Account created successfully! Please log in to continue.")
            elif message.get("message_type") == "new_message":
                # Immediate message delivery
                frame = MessageFrame(
                    self.messages_frame,
                    message["message"],
                    on_delete=self.delete_message
                )
                frame.pack(fill='x', padx=5, pady=2)
                
            elif "messages" in message:  # Message delivery response
                self.clear_messages()
                for msg in message["messages"]:
                    frame = MessageFrame(
                        self.messages_frame,
                        msg,
                        on_delete=self.delete_message
                    )
                    frame.pack(fill='x', padx=5, pady=2)
                    
            elif "users" in message:  # List accounts response
                self.accounts_list.delete(*self.accounts_list.get_children())
                self.known_users.clear()
                
                for user in message["users"]:
                    username = user["username"]
                    status = user["status"]
                    
                    self.accounts_list.insert("", "end", values=(username, status))
                    self.known_users.add(username)
                
                self.user_count_var.set(f"Users found: {len(message['users'])}")
                self.update_users_dropdown()
                
            elif message.get("message") == "Logged out successfully":
                self.username = None
                self.status_var.set("Not logged in")
                self.notebook.select(0)  # Switch to login tab
                self.clear_messages()
                
            elif message.get("message") == "Account deleted":
                self.username = None
                self.status_var.set("Not logged in")
                self.notebook.select(0)
                self.clear_messages()
                messagebox.showinfo("Success", "Account deleted successfully")
        else:
            messagebox.showerror("Error", message.get("message", "Unknown error occurred"))

    def on_connection_lost(self):
        if self.running:
            self.running = False
            messagebox.showerror("Error", "Connection to server lost")
            self.root.destroy()

    # Continue from previous implementation...

    def run(self):
        # Set up periodic message checking (every 5 seconds)
        def check_messages_periodically():
            if self.username and self.running:
                self.refresh_messages()
                self.root.after(5000, check_messages_periodically)
        
        def check_users_periodically():
            if self.username and self.running:
                self.search_accounts()
                self.root.after(10000, check_users_periodically)

        # Start periodic checks
        self.root.after(5000, check_messages_periodically)
        self.root.after(10000, check_users_periodically)
        
        # Set up proper cleanup on window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Initial user list population
        self.search_accounts()
        
        # Start the main event loop
        self.root.mainloop()

    def on_closing(self):
        """Handle cleanup when the window is closed."""
        self.running = False
        if self.username:
            try:
                self.logout()
            except:
                pass
        try:
            self.socket.close()
        except:
            pass
        self.root.destroy()

def main():
    """Main entry point for the chat client."""

    # Create and run the client
    client = ChatClient()
    client.run()

if __name__ == "__main__":
    main()