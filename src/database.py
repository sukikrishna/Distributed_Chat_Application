import sqlite3
import bcrypt

class Database:
    def __init__(self, db_name='chat.db'):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.setup_database()
    
    def setup_database(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT NOT NULL,
                recipient TEXT NOT NULL,
                message TEXT NOT NULL,
                delivered INTEGER DEFAULT 0
            )
        """)
        self.conn.commit()
    
    def create_account(self, username, password):
        try:
            password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            self.cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
    
    def login(self, username, password):
        self.cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
        result = self.cursor.fetchone()
        if result and bcrypt.checkpw(password.encode(), result[0].encode()):
            return True
        return False
    
    def send_message(self, sender, recipient, message):
        self.cursor.execute("INSERT INTO messages (sender, recipient, message) VALUES (?, ?, ?)", (sender, recipient, message))
        self.conn.commit()
        return True
    
    def read_messages(self, username):
        self.cursor.execute("SELECT sender, message FROM messages WHERE recipient = ? AND delivered = 0", (username,))
        messages = self.cursor.fetchall()
        self.cursor.execute("UPDATE messages SET delivered = 1 WHERE recipient = ?", (username,))
        self.conn.commit()
        return messages
