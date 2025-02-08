import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import socket
import threading
import time

class ChatGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Chat Application")
        self.root.geometry("800x600")
        
        self.socket = None
        self.username = None
        self.current_chat = None
        self.is_group_chat = False
        self.update_thread = None
        self.update_active = True
        
        self.setup_gui()
        
    def setup_gui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill='both')
        
        # Create frames
        self.login_frame = ttk.Frame(self.notebook, padding=10)
        self.contacts_frame = ttk.Frame(self.notebook, padding=10)
        self.chat_frame = ttk.Frame(self.notebook, padding=10)
        self.settings_frame = ttk.Frame(self.notebook, padding=10)
        
        self.setup_login_frame()
        self.setup_contacts_frame()
        self.setup_chat_frame()
        self.setup_settings_frame()
        
        self.notebook.add(self.login_frame, text='Login')
        self.notebook.add(self.contacts_frame, text='Contacts')
        self.notebook.add(self.chat_frame, text='Chat')
        self.notebook.add(self.settings_frame, text='Settings')
        
    def setup_login_frame(self):
        ttk.Label(self.login_frame, text="Username:").pack(pady=5)
        self.username_entry = ttk.Entry(self.login_frame)
        self.username_entry.pack(pady=5)
        
        ttk.Label(self.login_frame, text="Password:").pack(pady=5)
        self.password_entry = ttk.Entry(self.login_frame, show="*")
        self.password_entry.pack(pady=5)
        
        ttk.Button(self.login_frame, text="Login", command=self.login).pack(pady=5)
        ttk.Button(self.login_frame, text="Create Account", command=self.create_account).pack(pady=5)
        
    def setup_contacts_frame(self):
        # Search frame
        search_frame = ttk.Frame(self.contacts_frame)
        search_frame.pack(fill='x', pady=5)
        
        self.search_entry = ttk.Entry(search_frame)
        self.search_entry.pack(side='left', expand=True, fill='x', padx=(0,5))
        ttk.Button(search_frame, text="Search", command=self.search_contacts).pack(side='right')
        
        # Contacts list with three columns
        self.contacts_tree = ttk.Treeview(self.contacts_frame, columns=('username', 'status', 'unread'), show='headings')
        self.contacts_tree.heading('username', text='Username')
        self.contacts_tree.heading('status', text='Status')
        self.contacts_tree.heading('unread', text='Unread')
        self.contacts_tree.pack(expand=True, fill='both', pady=5)
        
        # Buttons
        btn_frame = ttk.Frame(self.contacts_frame)
        btn_frame.pack(fill='x')
        ttk.Button(btn_frame, text="Refresh", command=self.search_contacts).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Private Chat", command=lambda: self.start_chat(False)).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Group Chat", command=lambda: self.start_chat(True)).pack(side='left')
        
    def setup_chat_frame(self):
        self.chat_label = ttk.Label(self.chat_frame, font=('', 12, 'bold'))
        self.chat_label.pack(pady=5)
        
        self.message_area = scrolledtext.ScrolledText(self.chat_frame, wrap='word', height=20)
        self.message_area.pack(expand=True, fill='both', pady=5)
        
        input_frame = ttk.Frame(self.chat_frame)
        input_frame.pack(fill='x')
        self.msg_input = ttk.Entry(input_frame)
        self.msg_input.pack(side='left', expand=True, fill='x', padx=(0,5))
        ttk.Button(input_frame, text="Send", command=self.send_message).pack(side='right')
        
    def setup_settings_frame(self):
        ttk.Button(self.settings_frame, text="Logout", 
                  command=self.logout).pack(pady=5)
        
        ttk.Label(self.settings_frame, text="Delete Account").pack(pady=5)
        self.delete_password = ttk.Entry(self.settings_frame, show="*")
        self.delete_password.pack(pady=5)
        ttk.Button(self.settings_frame, text="Delete Account", 
                  command=self.delete_account).pack(pady=5)
        
    def connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect(("127.0.0.1", 50030))
            return True
        except:
            messagebox.showerror("Error", "Could not connect to server")
            return False
            
    def create_account(self):
        if not self.connect():
            return
            
        username = self.username_entry.get()
        password = self.password_entry.get()
        
        if not username or not password:
            messagebox.showwarning("Warning", "Enter username and password")
            return
            
        self.socket.send(f"CREATE:{username}:{password}".encode())
        response = self.socket.recv(1024).decode().split(":", 1)
        
        if response[0] == "OK":
            messagebox.showinfo("Success", "Account created")
        else:
            messagebox.showerror("Error", response[1])
            
        self.socket.close()
        self.socket = None
        
    def login(self):
        if not self.connect():
            return
            
        username = self.username_entry.get()
        password = self.password_entry.get()
        
        if not username or not password:
            messagebox.showwarning("Warning", "Enter username and password")
            return
            
        self.socket.send(f"LOGIN:{username}:{password}".encode())
        response = self.socket.recv(1024).decode().split(":", 1)
        
        if response[0] == "OK":
            self.username = username
            messagebox.showinfo("Success", f"Logged in. {response[1]} unread messages")
            self.notebook.select(1)
            self.search_contacts()
            self.start_updates()
        else:
            messagebox.showerror("Error", response[1])
            self.socket.close()
            self.socket = None
            
    def search_contacts(self):
        if not self.socket:
            return
            
        pattern = self.search_entry.get()
        self.socket.send(f"LIST:{pattern}".encode())
        response = self.socket.recv(1024).decode().split(":", 1)
        
        if response[0] == "OK":
            for item in self.contacts_tree.get_children():
                self.contacts_tree.delete(item)
                
            for account in response[1].split(","):
                if account:
                    username, status, unread = account.split(":")
                    if username != self.username:
                        self.contacts_tree.insert('', 'end', values=(username, status, unread))
                    
    def start_chat(self, is_group):
        if not is_group:
            selection = self.contacts_tree.selection()
            if not selection:
                messagebox.showwarning("Warning", "Select a contact")
                return
            self.current_chat = self.contacts_tree.item(selection[0])['values'][0]  # Get username from first column
            self.is_group_chat = False
        else:
            self.current_chat = f"group-{int(time.time())}"
            self.is_group_chat = True
            
        self.chat_label.config(text=f"{'Group: ' if is_group else 'Chat with '}{self.current_chat}")
        self.message_area.delete('1.0', 'end')
        self.notebook.select(2)
    
    def send_message(self):
        if not self.current_chat or not self.socket:
            return
            
        message = self.msg_input.get().strip()
        if not message:
            return
            
        cmd = "GROUP" if self.is_group_chat else "PRIVATE"
        payload = f"{self.username}:{self.current_chat}:{message}"
            
        self.socket.send(f"{cmd}:{payload}".encode())
        response = self.socket.recv(1024).decode().split(":")
        
        if response[0] == "OK":
            self.msg_input.delete(0, 'end')
            timestamp = time.strftime("%H:%M:%S")
            self.message_area.insert('end', f"[{timestamp}] You: {message}\n")
            self.message_area.see('end')
            
    def delete_account(self):
        if not self.socket:
            return
            
        password = self.delete_password.get()
        if not password:
            messagebox.showwarning("Warning", "Enter password")
            return
            
        if not messagebox.askyesno("Confirm", "Delete account? This cannot be undone."):
            return
            
        self.socket.send(f"DELETE_ACCOUNT:{self.username}:{password}".encode())
        response = self.socket.recv(1024).decode().split(":")
        
        if response[0] == "OK":
            messagebox.showinfo("Success", "Account deleted")
            self.reset_state()
            self.notebook.select(0)
        else:
            messagebox.showerror("Error", response[1])
            
    def logout(self):
        if self.socket:
            self.socket.send(f"LOGOUT:{self.username}".encode())
            response = self.socket.recv(1024).decode().split(":")
            
            if response[0] == "OK":
                messagebox.showinfo("Success", "Logged out successfully")
                self.reset_state()
                self.notebook.select(0)
                
    def reset_state(self):
        """Reset application state after logout/delete"""
        self.stop_updates()
        if self.socket:
            self.socket.close()
        self.socket = None
        self.username = None
        self.current_chat = None
        self.is_group_chat = False
        
        # Clear UI elements
        self.username_entry.delete(0, 'end')
        self.password_entry.delete(0, 'end')
        self.delete_password.delete(0, 'end')
        self.message_area.delete('1.0', 'end')
        for item in self.contacts_tree.get_children():
            self.contacts_tree.delete(item)
                
    def start_updates(self):
        """Start background updates thread"""
        self.update_active = True
        self.update_thread = threading.Thread(target=self.update_loop, daemon=True)
        self.update_thread.start()
        
    def stop_updates(self):
        """Stop background updates"""
        self.update_active = False
        if self.update_thread and self.update_thread.is_alive():
            self.update_thread.join(timeout=1.0)
            
    def update_loop(self):
        """Background update loop for refreshing contacts and messages"""
        while self.update_active and self.socket:
            try:
                data = self.socket.recv(1024).decode()
                if data.startswith("MSG:"):
                    _, timestamp, sender, message = data.split(":", 3)
                    if sender.endswith(" (Group)"):
                        sender = sender[:-8]  # Remove (Group) suffix
                        if self.current_chat == self.is_group_chat and self.is_group_chat:
                            self.message_area.insert('end', f"[{timestamp}] {sender}: {message}\n")
                            self.message_area.see('end')
                    elif self.current_chat == sender:
                        self.message_area.insert('end', f"[{timestamp}] {sender}: {message}\n")
                        self.message_area.see('end')
                    self.search_contacts()  # Refresh unread count
                    
            except Exception as e:
                print(f"Update error: {e}")
                break
                
        self.update_active = False
        
    def run(self):
        self.root.mainloop()
        self.stop_updates()
        if self.socket:
            self.socket.close()

if __name__ == "__main__":
    ChatGUI().run()