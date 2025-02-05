import hashlib

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, hashed_password):
    return hash_password(password) == hashed_password

def format_message(sender, recipient, message):
    return f"{sender}->{recipient}: {message}"