from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QComboBox, QFileDialog
import sys
import json
from client import ChatClient
from config import Config

CONFIG_FILE = "config.json"

def load_config():
    """Loads configuration from a JSON file. If the file doesn't exist, default values are used."""
    default_config = {
        "SERVER_HOST": "127.0.0.1",
        "SERVER_PORT": 5000,
        "DB_NAME": "chat.db",
        "LOG_FILE": "chat.log"
    }
    
    try:
        with open(CONFIG_FILE, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        save_config(default_config)
        return default_config

def save_config(config):
    """Saves the configuration to a JSON file."""
    with open(CONFIG_FILE, "w") as file:
        json.dump(config, file, indent=4)

class ChatGUI(QWidget):
    """Graphical User Interface for the Chat Application using PyQt5."""
    
    def __init__(self):
        """Initializes the chat GUI with login, messaging, and settings functionalities."""
        super().__init__()
        self.client = None
        self.config = load_config()
        self.init_ui()
    
    def init_ui(self):
        """Creates and arranges UI elements within the layout."""
        self.setWindowTitle("Chat Application")
        self.setGeometry(100, 100, 400, 550)
        
        layout = QVBoxLayout()
        
        self.protocol_label = QLabel("Select Protocol:")
        self.protocol_select = QComboBox()
        self.protocol_select.addItems(["Custom Binary Protocol", "JSON Protocol"])
        
        self.server_label = QLabel("Server Address:")
        self.server_input = QLineEdit(self.config.get("SERVER_HOST", "127.0.0.1"))
        
        self.port_label = QLabel("Port:")
        self.port_input = QLineEdit(str(self.config.get("SERVER_PORT", 5000)))
        
        self.username_label = QLabel("Username:")
        self.username_input = QLineEdit()
        self.password_label = QLabel("Password:")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        
        self.login_button = QPushButton("Login")
        self.login_button.clicked.connect(self.login)
        
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        
        self.message_input = QLineEdit()
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_message)
        
        self.save_settings_button = QPushButton("Save Settings")
        self.save_settings_button.clicked.connect(self.save_settings)
        
        layout.addWidget(self.protocol_label)
        layout.addWidget(self.protocol_select)
        layout.addWidget(self.server_label)
        layout.addWidget(self.server_input)
        layout.addWidget(self.port_label)
        layout.addWidget(self.port_input)
        layout.addWidget(self.username_label)
        layout.addWidget(self.username_input)
        layout.addWidget(self.password_label)
        layout.addWidget(self.password_input)
        layout.addWidget(self.login_button)
        layout.addWidget(self.chat_display)
        layout.addWidget(self.message_input)
        layout.addWidget(self.send_button)
        layout.addWidget(self.save_settings_button)
        
        self.setLayout(layout)
    
    def login(self):
        """Handles user login and initializes the client with the selected protocol."""
        username = self.username_input.text()
        password = self.password_input.text()
        use_json = self.protocol_select.currentText() == "JSON Protocol"
        
        self.client = ChatClient(use_json=use_json)
        success = self.client.login(username, password)
        if success:
            self.chat_display.append("Logged in successfully.")
        else:
            self.chat_display.append("Login failed.")
    
    def send_message(self):
        """Sends a chat message and updates the chat display."""
        if not self.client:
            self.chat_display.append("Error: Not logged in.")
            return
        
        sender = self.username_input.text()
        recipient = "bob"  # For now, sending to a static user
        message = self.message_input.text()
        
        self.client.send_message(sender, recipient, message)
        self.chat_display.append(f"You: {message}")
        self.message_input.clear()
    
    def save_settings(self):
        """Saves updated settings from the GUI to config.json."""
        new_config = {
            "SERVER_HOST": self.server_input.text(),
            "SERVER_PORT": int(self.port_input.text()),
            "DB_NAME": "chat.db",
            "LOG_FILE": "chat.log"
        }
        save_config(new_config)
        self.chat_display.append("Settings saved successfully.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = ChatGUI()
    gui.show()
    sys.exit(app.exec_())
