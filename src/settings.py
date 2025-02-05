import os
import json
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton

CONFIG_FILE = "config.json"

def load_config():
    """Loads configuration from a JSON file. If the file doesn't exist, default values are used."""
    default_config = {
        "SERVER_HOST": "127.0.0.1",
        "SERVER_PORT": 5000,
        "DB_NAME": "chat.db",
        "LOG_FILE": "chat.log"
    }
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as file:
                return json.load(file)
        except json.JSONDecodeError:
            print("Warning: Invalid JSON format. Using default configuration.")
    
    # Save default config if file doesn't exist
    save_config(default_config)
    return default_config

def save_config(config):
    """Saves the configuration to a JSON file."""
    with open(CONFIG_FILE, "w") as file:
        json.dump(config, file, indent=4)

class Config:
    """Configuration settings for the chat application, loaded dynamically from a JSON file."""
    
    _config = load_config()
    SERVER_HOST = _config.get("SERVER_HOST", "127.0.0.1")
    SERVER_PORT = int(_config.get("SERVER_PORT", 5000))
    DB_NAME = _config.get("DB_NAME", "chat.db")
    LOG_FILE = _config.get("LOG_FILE", "chat.log")
    
    @staticmethod
    def update_config(new_config):
        """Updates the configuration and saves it to the JSON file."""
        save_config(new_config)
        Config._config = new_config
        Config.SERVER_HOST = new_config.get("SERVER_HOST", "127.0.0.1")
        Config.SERVER_PORT = int(new_config.get("SERVER_PORT", 5000))
        Config.DB_NAME = new_config.get("DB_NAME", "chat.db")
        Config.LOG_FILE = new_config.get("LOG_FILE", "chat.log")

class SettingsGUI(QWidget):
    """GUI for modifying chat application settings."""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        """Creates and arranges UI elements."""
        self.setWindowTitle("Chat Settings")
        self.setGeometry(100, 100, 300, 200)
        
        layout = QVBoxLayout()
        
        self.host_label = QLabel("Server Host:")
        self.host_input = QLineEdit(Config.SERVER_HOST)
        
        self.port_label = QLabel("Server Port:")
        self.port_input = QLineEdit(str(Config.SERVER_PORT))
        
        self.db_label = QLabel("Database Name:")
        self.db_input = QLineEdit(Config.DB_NAME)
        
        self.log_label = QLabel("Log File:")
        self.log_input = QLineEdit(Config.LOG_FILE)
        
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_settings)
        
        layout.addWidget(self.host_label)
        layout.addWidget(self.host_input)
        layout.addWidget(self.port_label)
        layout.addWidget(self.port_input)
        layout.addWidget(self.db_label)
        layout.addWidget(self.db_input)
        layout.addWidget(self.log_label)
        layout.addWidget(self.log_input)
        layout.addWidget(self.save_button)
        
        self.setLayout(layout)
    
    def save_settings(self):
        """Saves updated settings from the GUI to config.json."""
        new_config = {
            "SERVER_HOST": self.host_input.text(),
            "SERVER_PORT": int(self.port_input.text()),
            "DB_NAME": self.db_input.text(),
            "LOG_FILE": self.log_input.text()
        }
        Config.update_config(new_config)
        print("Settings saved successfully.")

if __name__ == "__main__":
    app = QApplication([])
    settings_gui = SettingsGUI()
    settings_gui.show()
    app.exec_()
