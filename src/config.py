import json
import os
import socket

class Config:
    def __init__(self):
        self.config_file = "chat_config.json"
        self.default_config = {
            "host": "127.0.0.1",
            "port": 50000,
            "message_fetch_limit": 5
        }
        self.load_config()

    def load_config(self):
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                self.config = json.load(f)
                self.config['host'] = self.get_local_ip()
                self.save_config()  # Save the updated IP
        else:
            self.config = self.default_config.copy()  # Use copy to avoid modifying default
            self.config['host'] = self.get_local_ip()  # Set IP for new config
            self.save_config()

    def get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def save_config(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=4)

    def get(self, key):
        return self.config.get(key, self.default_config.get(key))

    def update(self, key, value):
        self.config[key] = value
        self.save_config()