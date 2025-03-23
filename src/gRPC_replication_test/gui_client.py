import tkinter as tk
import threading
import time
from tkinter import ttk, scrolledtext
from base_client import ChatClientBase
import tkinter.messagebox as messagebox
from ttkthemes import ThemedStyle
import signal

import spec_pb2


class ChatClientGUI(tk.Tk, ChatClientBase):
    def __init__(self, addresses):
        tk.Tk.__init__(self)
        ChatClientBase.__init__(self, addresses)

        self.title("Chat App")
        self.geometry("900x700")

        self.create_widgets()

        user_list_update_thread = threading.Thread(
            target=self.update_user_list)
        user_list_update_thread.daemon = True
        user_list_update_thread.start()

        chat_update_thread = threading.Thread(
            target=self.update_chat)
        chat_update_thread.daemon = True
        chat_update_thread.start()

        notification_update_thread = threading.Thread(
            target=self.update_notification)
        notification_update_thread.daemon = True
        notification_update_thread.start()

        self.protocol("WM_DELETE_WINDOW", self.exit_)

        signal.signal(signal.SIGINT, self.exit_)

    def exit_(self, *args, **kwargs):
        try:
            self.logout()
        except Exception as e:
            print("Error logging out:", e)
        self.destroy()



    def search_users(self):
        pattern = self.recipient_var.get()
        if not pattern:
            pattern = "*"
        elif not pattern.endswith("*"):
            pattern += "*"

        try:
            request = spec_pb2.ListUsersRequest(wildcard=pattern)
            response = self.stub.ListUsers(request)

            self.user_listbox.delete(0, tk.END)
            for user in response.user:
                self.user_listbox.insert(tk.END, f"{user.username} [{user.status}]")
        except Exception as e:
            messagebox.showerror("Error", f"Search failed: {e}")


    def select_user_from_list(self, event):
        try:
            selection = self.user_listbox.get(self.user_listbox.curselection())
            username = selection.split(' [')[0]
            self.recipient_var.set(username)
            self.clear_chat()
            self.load_chat_history(username)
        except Exception:
            pass  # ignore if no selection



    def create_widgets(self):

        style = ThemedStyle(self)
        style.set_theme("adapta")

        scrolledtext.ScrolledText.style = "TScrolledText"

        # Create frames
        top_frame = ttk.Frame(self)
        top_frame.pack(side=tk.TOP, fill=tk.X)

        # print("stub:", self.stub)
        if not self.stub:
            self.retry_button = ttk.Button(
                top_frame, text="Retry Connection", command=self.retry_connection)
            self.retry_button.pack(side=tk.LEFT, padx=5)
            messagebox.showerror(
                "Error", "Failed to establish connection. Click the Retry Connection button to try again.")

        chat_frame = ttk.Frame(self)
        chat_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        recipient_frame = ttk.Frame(self)
        recipient_frame.pack(side=tk.TOP, fill=tk.X)

        message_frame = ttk.Frame(self)
        message_frame.pack(side=tk.TOP, fill=tk.X)



        results_frame = ttk.LabelFrame(self, text="Matched Users", padding=5)
        results_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        self.user_listbox = tk.Listbox(results_frame, height=4)
        self.user_listbox.pack(fill=tk.X)
        self.user_listbox.bind('<<ListboxSelect>>', self.select_user_from_list)



        # Create input fields and labels
        self.logged_in_label = ttk.Label(top_frame, text="Logged in as:")
        self.logged_in_label.pack(side=tk.LEFT, padx=5)
        self.logged_in_label.pack_forget()

        self.username_label = ttk.Label(top_frame, text="Username:")
        self.username_label.pack(side=tk.LEFT, padx=5)

        self.username_entry = ttk.Entry(top_frame)
        self.username_entry.pack(side=tk.LEFT, padx=5)

        self.password_label = ttk.Label(top_frame, text="Password:")
        self.password_label.pack(side=tk.LEFT, padx=5)

        self.password_entry = ttk.Entry(top_frame, show="*")
        self.password_entry.pack(side=tk.LEFT, padx=5)

        # Create buttons
        self.signup_button = ttk.Button(
            top_frame, text="Sign up", command=self.signup)
        self.signup_button.pack(side=tk.LEFT, padx=5)

        # Create buttons
        self.login_button = ttk.Button(
            top_frame, text="Login", command=self.login)
        self.login_button.pack(side=tk.LEFT, padx=5)

        # logout button
        self.logout_button = ttk.Button(
            top_frame, text="Logout", command=self.logout)
        self.logout_button.pack(side=tk.LEFT, padx=5)
        self.logout_button.pack_forget()

        # Create notification area inside chat_frame
        self.notification_text = scrolledtext.ScrolledText(
            chat_frame, wrap=tk.WORD, state='disabled', height=4)
        self.notification_text.pack(
            side=tk.TOP, padx=5, pady=(0, 2), fill=tk.X, expand=False)

        # Add a separator line between notification_text and chat_text
        separator = ttk.Separator(chat_frame, orient="horizontal")
        separator.pack(side=tk.TOP, padx=5, pady=5, fill=tk.X)

        # Create chat display area
        self.chat_text = scrolledtext.ScrolledText(
            chat_frame, wrap=tk.WORD, state='disabled')
        self.chat_text.pack(fill=tk.BOTH, expand=True)

        # Create message input field and send button
        self.message_entry = ttk.Entry(message_frame)
        self.message_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        send_button = ttk.Button(
            message_frame, text="Send", command=self.send_message)
        send_button.pack(side=tk.RIGHT, padx=5)

        recipient_label = ttk.Label(recipient_frame, text="")
        recipient_label.pack(side=tk.LEFT, padx=5)

        # choosen_recipient = tk.StringVar()
        # self.recipient_combobox = ttk.Combobox(
        #     recipient_frame, state="readonly", textvariable=choosen_recipient)
        # self.recipient_combobox.pack(
        #     side=tk.LEFT, padx=5, expand=True, fill=tk.X)

        # # Add this line to bind the callback function to the variable
        # self.recipient_combobox.bind(
        #     "<<ComboboxSelected>>", self.change_recipient)

        # list_users_button = ttk.Button(
        #     recipient_frame, text="List Users", command=self.display_users)
        # list_users_button.pack(side=tk.RIGHT, padx=5)

        ttk.Label(recipient_frame, text="To:").pack(side=tk.LEFT, padx=(5, 2))

        self.recipient_var = tk.StringVar()
        self.recipient_entry = ttk.Entry(
            recipient_frame, textvariable=self.recipient_var)
        self.recipient_entry.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        self.search_button = ttk.Button(
            recipient_frame, text="Search", command=self.search_users)
        self.search_button.pack(side=tk.LEFT, padx=5)


        clear_button = ttk.Button(
            chat_frame, text="Clear", command=self.clear_chat)
        clear_button.pack(side=tk.BOTTOM, pady=5)

    def display_notification(self, notification_text):
        self.notification_text.configure(state='normal')
        self.notification_text.insert(tk.END, notification_text + "\n")
        self.notification_text.configure(state='disabled')
        self.notification_text.see(tk.END)

    def signup(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        response = ChatClientBase.create_account(self, username, password)
        if response.error_code != 0:
            messagebox.showerror("Error", response.error_message)
            return
        self.login()

    def login(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        response = ChatClientBase.login(self, username, password)

        if response.error_code == 0:
            self.user_session_id = response.session_id
            # threading.Thread(target=self.receive_thread).start()
            self.username_label.pack_forget()
            self.username_entry.pack_forget()
            self.password_label.pack_forget()
            self.password_entry.pack_forget()
            self.login_button.pack_forget()
            self.signup_button.pack_forget()

            self.logout_button.pack(side="left", padx=(10, 0))

            self.logged_in_label.config(text=f"Logged in as: {username}")
            self.logged_in_label.pack(side="left")

        else:
            messagebox.showerror("Error", response.error_message)

    def relogin(self):
        messagebox.showerror(
            "Error", "Server failed, connected to backup server. Please relogin")
        try:
            self.logged_in_label.pack_forget()
            self.logout_button.pack_forget()

            self.username_label.pack(side="left")
            self.username_entry.pack(side="left")
            self.password_label.pack(side="left")
            self.password_entry.pack(side="left")
            self.login_button.pack(side="left")
            self.signup_button.pack(side="left")
        except Exception as e:
            print(e)

    def logout(self):
        response = ChatClientBase.logout(self)

        if response.error_code == 0:
            self.logged_in_label.pack_forget()
            self.logout_button.pack_forget()

            self.username_label.pack(side="left")
            self.username_entry.pack(side="left")
            self.password_label.pack(side="left")
            self.password_entry.pack(side="left")
            self.login_button.pack(side="left")
            self.signup_button.pack(side="left")

    def display_users(self):
        response = ChatClientBase.list_users(self)

        if response:
            users = [user for user in response]

            # self.recipient_combobox["values"] = tuple(
            #     [user.username for user in users])

            self.notification_text.config(state='normal')
            self.notification_text.insert(tk.END, "List of users:\n")
            for user in users:
                self.notification_text.insert(
                    tk.END, f"{user.username} [{user.status}]\n")
            self.notification_text.config(state='disabled')

    def send_message(self):
        to = self.recipient_var.get()
        message = self.message_entry.get()

        if to and message:
            response = ChatClientBase.send_message(self, to, message)
            # print(to, message, response)
            if response.error_code == 0:
                self.message_entry.delete(0, tk.END)
                # self.display_message(f"You: {message}")
            else:
                messagebox.showerror("Error", response.error_message)
        else:
            messagebox.showerror(
                "Error", "Please select a recipient and enter a message.")

    def retry_connection(self):
        self.connect()
        if self.stub:
            messagebox.showinfo("Success", "Connection re-established.")
            self.retry_button.pack_forget()
        else:
            messagebox.showerror(
                "Error", "Failed to establish connection. Try again.")

    def clear_chat(self):
        self.chat_text.config(state='normal')
        self.chat_text.delete(1.0, tk.END)
        self.chat_text.config(state='disabled')

    def change_recipient(self, event):
        self.clear_chat()
        self.load_chat_history(event.widget.get())

    def load_chat_history(self, recipient):

        # print("inside load_chat_history: ", recipient)

        if recipient:
            response = ChatClientBase.get_chat(self, recipient)

            if response.error_code == 0:
                self.clear_chat()
                self.chat_text.config(state='normal')
                self.chat_text.delete(1.0, tk.END)
                for message in response.message:
                    self.chat_text.insert(
                        tk.END, f"{message.from_}: {message.message}\n")
                self.chat_text.config(state='disabled')
            else:
                pass
                # print(response.error_message)

    def update_notification(self):

        while True:

            msgs = ChatClientBase.receive_messages(self)
            # print('messages: ', msgs)
            if msgs:
                if msgs.error_code == 0:
                    for message in msgs.message:
                        # here building a cache of messages for each user
                        # might be a good idea isntead of asking the server each time
                        # for update in the update method
                        self.display_notification(
                            f"Message from:{message.from_}")

            time.sleep(2)

    def update_chat(self):
        while True:
            # here it might be a good idea
            # to only load a certain amount of messages
            # and have that built in capability on the server side as well
            self.load_chat_history(self.recipient_var.get())
            time.sleep(1)

    # def update_user_list(self, interval=2):
    #     while True:
    #         users = self.list_users()

    #         self.recipient_combobox['values'] = [
    #             user.username for user in users]
    #         time.sleep(interval)

    def update_user_list(self, interval=2):
        while True:
            users = self.list_users()
            # users = self.list_users("*")  # explicitly pass wildcard
            time.sleep(interval)

    @classmethod
    def run(cls, addresses):
        app = cls(addresses)
        app.mainloop()


if __name__ == "__main__":
    import argparse

    # take in a list of available address with the first one being
    # the master
    parser = argparse.ArgumentParser(
        description="Start a chat client.")
    parser.add_argument('-a', '--addresses', nargs='+',
                        help='<Required> give list of available servers', required=True)

    args = parser.parse_args()
    addresses = args.addresses
    # print(addresses)

    ChatClientGUI.run(addresses)
