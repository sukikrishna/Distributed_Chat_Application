import os
import json

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
