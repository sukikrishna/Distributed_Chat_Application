import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import socket
import threading
from custom_protocol import CustomProtocolServer
from config import Config

class ChatGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Chat Application")
        self.root.geometry("1000x600")

        self.config = Config()
        self.host = self.config.get("host")
        self.port = self.config.get("port")
        self.username = None
        self.client_socket = None
        self.current_chat = None
        self.contacts = []
        self.logged_in = False
        self.is_group_chat = False

        # Check for existing connection
        # try:
        #     test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        #     test_socket.connect((self.host, self.port))
        #     test_socket.close()
        # except:
        #     # Start server if not running
        #     self.start_server()

        self.setup_gui()

    def connect_socket(self):
        try:
            if self.client_socket:
                try:
                    self.client_socket.close()
                except:
                    pass
            
            # Reload config to get potentially updated port
            self.config.load_config()
            self.port = self.config.get("port")
            
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.client_socket.connect((self.host, self.port))
            return True
        except Exception as e:
            messagebox.showerror("Error", f"Connection failed: {str(e)}")
            return False

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
        
        # Contacts list
        self.contacts_tree = ttk.Treeview(self.contacts_frame, columns=('username', 'status', 'unread'), show='headings')
        self.contacts_tree.heading('username', text='Username')
        self.contacts_tree.heading('status', text='Status')
        self.contacts_tree.heading('unread', text='Unread')
        self.contacts_tree.pack(expand=True, fill='both', pady=5)
        
        # Buttons
        btn_frame = ttk.Frame(self.contacts_frame)
        btn_frame.pack(fill='x')
        ttk.Button(btn_frame, text="Refresh", command=self.search_contacts).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Private Chat", command=self.start_chat).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Group Chat", command=self.start_group_chat).pack(side='left')

    def setup_chat_frame(self):
        self.chat_header = ttk.Label(self.chat_frame, text="No chat selected", font=('', 12, 'bold'))
        self.chat_header.pack(pady=5)

        self.message_area = scrolledtext.ScrolledText(self.chat_frame, wrap=tk.WORD)
        self.message_area.pack(expand=True, fill='both', pady=5)
        self.message_area.tag_configure('right', justify='right')
        self.message_area.tag_configure('left', justify='left')

        input_frame = ttk.Frame(self.chat_frame)
        input_frame.pack(fill='x')
        self.message_input = scrolledtext.ScrolledText(input_frame, wrap=tk.WORD, height=4)
        self.message_input.pack(side='left', expand=True, fill='x', padx=(0,5))
        ttk.Button(input_frame, text="Send", command=self.send_message).pack(side='right')

    def setup_settings_frame(self):
        """Set up the settings frame"""
        # Messages per fetch
        ttk.Label(self.settings_frame, text="Messages per fetch:").grid(row=0, column=0, pady=5)
        self.msgs_per_fetch_var = tk.StringVar(value="10")
        ttk.Entry(self.settings_frame, textvariable=self.msgs_per_fetch_var).grid(row=0, column=1, pady=5)
        
        # Save settings button
        ttk.Button(self.settings_frame, text="Save Settings", command=self.save_settings).grid(row=4, column=0, columnspan=2, pady=10)
        
        # Delete account section
        ttk.Label(self.settings_frame, text="Delete Account", font=('', 12, 'bold')).grid(row=5, column=0, columnspan=2, pady=20)
        ttk.Label(self.settings_frame, text="Password:").grid(row=6, column=0, pady=5)
        self.delete_password_var = tk.StringVar()
        ttk.Entry(self.settings_frame, textvariable=self.delete_password_var, show="*").grid(row=6, column=1, pady=5)
        
        # Delete account button
        ttk.Button(self.settings_frame, text="Delete Account",
                  command=self.delete_account,
                  style="Danger.TButton").grid(row=7, column=0, columnspan=2, pady=10)
        
        # Logout button
        ttk.Button(self.settings_frame, text="Logout",
                  command=self.logout).grid(row=8, column=0, columnspan=2, pady=20)

    def create_account(self):
        username = self.username_entry.get()
        password = self.password_entry.get()

        if not username or not password:
            messagebox.showerror("Error", "Please enter both username and password")
            return

        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((self.host, self.port))
            
            message = f"CREATE:{username}:{password}"
            self.client_socket.send(message.encode())
            
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
                self.client_socket = None

    def login(self):
        username = self.username_entry.get()
        password = self.password_entry.get()

        if not username or not password:
            messagebox.showerror("Error", "Please enter both username and password")
            return

        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((self.host, self.port))
            
            message = f"LOGIN:{username}:{password}"
            self.client_socket.send(message.encode())
            
            response = self.client_socket.recv(1024).decode()
            if response == "SUCCESS":
                parts = response.split(":")
                unread_count = int(parts[1]) if len(parts) > 1 else 0
                self.username = username
                self.logged_in = True
                messagebox.showinfo("Success", f"Logged in successfully\nYou have {unread_count} unread messages")
                self.notebook.select(1)  # Switch to contacts tab
                self.update_contacts()
                threading.Thread(target=self.receive_messages, daemon=True).start()
            else:
                messagebox.showerror("Error", response)
                if self.client_socket:
                    self.client_socket.close()
                    self.client_socket = None
                
        except Exception as e:
            messagebox.showerror("Error", f"Could not connect to server: {str(e)}")

    def search_contacts(self):
        pattern = self.search_entry.get()
        self.client_socket.send("LIST_ACCOUNTS".encode())
        response = self.client_socket.recv(1024).decode()
        contacts = response.split(",")
        
        for item in self.contacts_tree.get_children():
            self.contacts_tree.delete(item)
            
        for contact in contacts:
            if contact and contact != self.username and (not pattern or pattern in contact):
                # For now, we'll set status as "online" and unread as 0
                # You can enhance this by tracking actual status and unread counts
                self.contacts_tree.insert('', 'end', values=(contact, "online", "0"))

    def start_chat(self):
        if not self.logged_in:
            messagebox.showerror("Error", "Please login first")
            return

        selection = self.contacts_tree.selection()
        if not selection:
            messagebox.showerror("Error", "Please select a contact")
            return

        recipient = self.contacts_tree.item(selection[0])['values'][0]
        self.current_chat = recipient
        self.is_group_chat = False
        self.chat_header.config(text=f"Chat with {recipient}")
        self.message_area.delete('1.0', tk.END)
        self.notebook.select(2)  # Switch to chat tab

    def start_group_chat(self):
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
            self.is_group_chat = True
            self.chat_header.config(text="Group Chat")
            self.message_area.delete('1.0', tk.END)
            self.message_area.insert(tk.END, "Connected to group chat!\n")
            
            self.notebook.select(2)  # Switch to chat tab
            threading.Thread(target=self.receive_messages, daemon=True).start()
            
        except ConnectionRefusedError:
            messagebox.showerror("Error", "Could not connect to server")

    def send_message(self):
        if not self.client_socket:
            messagebox.showerror("Error", "Not connected to any chat")
            return

        message = self.message_input.get("1.0", tk.END).strip()
        if message:
            try:
                if self.is_group_chat:
                    self.client_socket.send(message.encode())
                else:
                    formatted_message = f"MSG:{self.current_chat}:{message}"
                    self.client_socket.send(formatted_message.encode())
                self.message_input.delete("1.0", tk.END)
            except:
                messagebox.showerror("Error", "Connection lost")

    def receive_messages(self):
        while True:
            try:
                message = self.client_socket.recv(1024).decode()
                if not message:
                    break
                
                if ': ' in message:
                    username = message.split(': ')[0]
                    if username.startswith('['):  # Remove timestamp if present
                        username = username.split('] ')[1]
                    
                    if username == self.username:
                        self.message_area.insert(tk.END, message + "\n", 'right')
                    else:
                        self.message_area.insert(tk.END, message + "\n", 'left')
                else:
                    self.message_area.insert(tk.END, message + "\n")
                    
                self.message_area.yview(tk.END)
                
            except:
                self.message_area.insert(tk.END, "Disconnected from server\n")
                break

    def save_settings(self):
        """Save user settings"""
        try:
            new_settings = {
                'messages_per_fetch': int(self.msgs_per_fetch_var.get()),
            }
            response = self.client.update_settings(new_settings)
            if "updated successfully" in response:
                messagebox.showinfo("Success", "Settings saved successfully")
            else:
                messagebox.showerror("Error", response)
        except ValueError:
            messagebox.showerror("Error", "Invalid messages per fetch value")
            

    def delete_account(self):
        """Delete user account"""
        if not messagebox.askyesno("Confirm", "Are you sure you want to delete your account? This cannot be undone."):
            return

        password = self.delete_password_var.get()
        if not password:
            messagebox.showwarning("Warning", "Enter your password")
            return
            
        try:
            message = f"DELETE_ACCOUNT:{self.username}:{password}"
            self.client_socket.send(message.encode())
            response = self.client_socket.recv(1024).decode()
            
            if response == "SUCCESS":
                messagebox.showinfo("Success", "Account deleted successfully")
                self.reset_state()
                self.notebook.select(0)  # Return to login tab
            else:
                messagebox.showerror("Error", response)
        except Exception as e:
            messagebox.showerror("Error", f"Connection error: {str(e)}")

    def logout(self):
        if not self.logged_in:
            return
            
        try:
            if self.is_group_chat:
                self.client_socket.send(f"LEAVE_GROUP:{self.username}".encode())
                
            message = f"LOGOUT:{self.username}"
            self.client_socket.send(message.encode())
            self.reset_state()
            messagebox.showinfo("Success", "Logged out successfully")
            self.notebook.select(0)
        except:
            messagebox.showerror("Error", "Connection error")

    def reset_state(self):
        if self.client_socket:
            self.client_socket.close()
        self.client_socket = None
        self.username = None
        self.current_chat = None
        self.is_group_chat = False
        self.logged_in = False
        
        self.username_entry.delete(0, 'end')
        self.password_entry.delete(0, 'end')
        self.delete_password.delete(0, 'end')
        self.message_area.delete('1.0', 'end')
        for item in self.contacts_tree.get_children():
            self.contacts_tree.delete(item)

    def update_contacts(self):
        try:
            self.client_socket.send("LIST_ACCOUNTS".encode())
            response = self.client_socket.recv(1024).decode()
            self.contacts = response.split(",")
            
            for item in self.contacts_tree.get_children():
                self.contacts_tree.delete(item)
            
            for contact in self.contacts:
                if contact and contact != self.username:
                    self.contacts_tree.insert('', 'end', values=(contact, "online", "0"))
                    
        except Exception as e:
            messagebox.showerror("Error", f"Could not update contacts: {str(e)}")

    def run(self):
        self.root.mainloop()
        if self.client_socket:
            self.client_socket.close()

if __name__ == "__main__":
    chat_gui = ChatGUI()
    chat_gui.run()