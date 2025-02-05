import hashlib

def hash_password(password):
    """Hashes a password using SHA-256.
    
    Args:
        password (str): The password to hash.
    
    Returns:
        str: The hashed password in hexadecimal format.
    """
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, hashed_password):
    """Verifies if a given password matches the stored hash.
    
    Args:
        password (str): The plaintext password to verify.
        hashed_password (str): The stored hashed password.
    
    Returns:
        bool: True if the password matches the hash, False otherwise.
    """
    return hash_password(password) == hashed_password

def format_message(sender, recipient, message):
    """Formats a chat message for display.
    
    Args:
        sender (str): The sender's username.
        recipient (str): The recipient's username.
        message (str): The message content.
    
    Returns:
        str: A formatted string representing the message.
    """
    return f"{sender}->{recipient}: {message}"