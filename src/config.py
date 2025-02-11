import json
import os
import socket

class Config:
    """Handles configuration settings for the chat application.

    Attributes:
        config_file (str): Path to the configuration file.
        default_config (dict): Default configuration values.
        config (dict): Loaded configuration values.
    """

    HOST = None  # Will be assigned dynamically in `load_config()`
    
    def __init__(self):
        """Initializes the Config class, loads configuration, and ensures a valid configuration file."""
        self.config_file = "chat_config.json"
        self.default_config = {
            "port": 50000,  # Default port
            "message_fetch_limit": 5  # Default message fetch limit
        }
        self.load_config()

    def load_config(self):
        """Loads configuration from `chat_config.json` if it exists.
        If the file is missing or `host` is not set, assigns `HOST` using `get_local_ip()`.

        Raises:
            IOError: If there is an issue reading the config file.
        """
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    self.config = json.load(f)
            except IOError as e:
                raise IOError(f"Error reading config file: {e}")
        else:
            self.config = self.default_config.copy()

        # Use the host from config if available, otherwise set the default via get_local_ip()
        Config.HOST = self.config.get("host", self.get_local_ip())

        # If the host was missing, update the file so the user can see it
        if "host" not in self.config:
            self.config["host"] = Config.HOST
            self.save_config()

    def save_config(self):
        """Saves the current configuration to `chat_config.json`.

        Raises:
            IOError: If there is an issue writing to the file.
        """
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
        except IOError as e:
            raise IOError(f"Error writing config file: {e}")

    def get(self, key):
        """Retrieves a configuration value.

        Args:
            key (str): The configuration key to retrieve.

        Returns:
            Any: The value associated with the key, or None if not set.
        """
        return self.config.get(key, self.default_config.get(key))

    def update(self, key, value):
        """Updates a configuration value and saves the configuration.

        Args:
            key (str): The configuration key to update.
            value (Any): The new value for the key.
        """
        self.config[key] = value
        self.save_config()

    @staticmethod
    def get_local_ip():
        """Retrieves the local machine's IP address.

        Returns:
            str: The detected local IP address, or '127.0.0.1' if retrieval fails.
        """
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))  # Connect to Google's DNS to determine external-facing IP
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
