import sqlite3
import os
import threading
import json
import time
import logging

class PersistenceManager:
    """Manages persistence of server state using SQLite.
    
    This class provides methods for storing and retrieving server state,
    including user accounts, messages, and other critical data.
    
    Attributes:
        db_path (str): Path to the SQLite database file
        conn (sqlite3.Connection): Connection to the database
        lock (threading.Lock): Lock for thread-safe database operations
    """
    
    def __init__(self, config):
        """Initialize the persistence manager.
        
        Args:
            config (ReplicationConfig): Replication configuration
        """
        self.config = config
        self.db_path = config.get_data_file()
        self.lock = threading.Lock()
        self.logger = logging.getLogger('persistence')
        
        # Set up logging
        handler = logging.FileHandler(f'persistence_{config.server_id}.log')
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
        
        # Initialize database connection
        self.conn = None
        self._initialize_db()
    
    def _initialize_db(self):
        """Initialize the database connection and schema."""
        try:
            # Create data directory if it doesn't exist
            db_dir = os.path.dirname(self.db_path)
            if not os.path.exists(db_dir):
                os.makedirs(db_dir)
            
            # Connect to database
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            
            # Create tables if they don't exist
            with self.lock:
                cursor = self.conn.cursor()
                
                # Users table
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    settings TEXT
                )
                ''')
                
                # Messages table
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_user TEXT NOT NULL,
                    to_user TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    read INTEGER DEFAULT 0,
                    delivered_while_offline INTEGER DEFAULT 0,
                    FOREIGN KEY (to_user) REFERENCES users(username)
                )
                ''')
                
                # Active users table
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS active_users (
                    username TEXT PRIMARY KEY,
                    last_active INTEGER NOT NULL,
                    FOREIGN KEY (username) REFERENCES users(username)
                )
                ''')
                
                # Operation log for replication
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS operation_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation_type TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    data TEXT NOT NULL,
                    applied INTEGER DEFAULT 0
                )
                ''')
                
                self.conn.commit()
                self.logger.info("Database initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
            raise
    
    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
    
    def save_user(self, username, password_hash, settings=None):
        """Save a user to the database.
        
        Args:
            username (str): Username
            password_hash (str): Hashed password
            settings (dict, optional): User settings
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                settings_json = json.dumps(settings) if settings else '{}'
                
                # Check if user exists
                cursor.execute("SELECT 1 FROM users WHERE username = ?", (username,))
                if cursor.fetchone():
                    # Update existing user
                    cursor.execute(
                        "UPDATE users SET password_hash = ?, settings = ? WHERE username = ?",
                        (password_hash, settings_json, username)
                    )
                else:
                    # Insert new user
                    cursor.execute(
                        "INSERT INTO users (username, password_hash, settings) VALUES (?, ?, ?)",
                        (username, password_hash, settings_json)
                    )
                
                self.conn.commit()
                return True
        except Exception as e:
            self.logger.error(f"Failed to save user {username}: {e}")
            return False
    
    def get_user(self, username):
        """Get a user from the database.
        
        Args:
            username (str): Username
            
        Returns:
            dict: User data or None if not found
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute(
                    "SELECT username, password_hash, settings FROM users WHERE username = ?",
                    (username,)
                )
                row = cursor.fetchone()
                
                if row:
                    return {
                        "username": row[0],
                        "password_hash": row[1],
                        "settings": json.loads(row[2])
                    }
                return None
        except Exception as e:
            self.logger.error(f"Failed to get user {username}: {e}")
            return None
    
    def delete_user(self, username):
        """Delete a user from the database.
        
        Args:
            username (str): Username
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                
                # Delete from users table
                cursor.execute("DELETE FROM users WHERE username = ?", (username,))
                
                # Delete from active_users table
                cursor.execute("DELETE FROM active_users WHERE username = ?", (username,))
                
                # Delete user's messages
                cursor.execute("DELETE FROM messages WHERE to_user = ?", (username,))
                
                self.conn.commit()
                return True
        except Exception as e:
            self.logger.error(f"Failed to delete user {username}: {e}")
            return False
    
    def get_all_users(self):
        """Get all users from the database.
        
        Returns:
            list: List of user dictionaries
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute("SELECT username, password_hash, settings FROM users")
                rows = cursor.fetchall()
                
                users = []
                for row in rows:
                    users.append({
                        "username": row[0],
                        "password_hash": row[1],
                        "settings": json.loads(row[2])
                    })
                return users
        except Exception as e:
            self.logger.error(f"Failed to get all users: {e}")
            return []
    
    def save_message(self, from_user, to_user, content, timestamp=None, read=False, delivered_while_offline=False):
        """Save a message to the database.
        
        Args:
            from_user (str): Sender username
            to_user (str): Recipient username
            content (str): Message content
            timestamp (int, optional): Message timestamp. If None, current time is used.
            read (bool, optional): Whether the message has been read
            delivered_while_offline (bool, optional): Whether the message was delivered while user was offline
            
        Returns:
            int: Message ID or -1 if failed
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                
                if timestamp is None:
                    timestamp = int(time.time())
                
                cursor.execute(
                    """
                    INSERT INTO messages 
                    (from_user, to_user, content, timestamp, read, delivered_while_offline)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (from_user, to_user, content, timestamp, 1 if read else 0, 1 if delivered_while_offline else 0)
                )
                
                message_id = cursor.lastrowid
                self.conn.commit()
                return message_id
        except Exception as e:
            self.logger.error(f"Failed to save message from {from_user} to {to_user}: {e}")
            return -1
    
    def get_messages(self, username, unread_only=False, limit=None):
        """Get messages for a user.
        
        Args:
            username (str): Username to get messages for
            unread_only (bool, optional): If True, only return unread messages
            limit (int, optional): Maximum number of messages to return
            
        Returns:
            list: List of message dictionaries
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                
                query = """
                SELECT id, from_user, to_user, content, timestamp, read, delivered_while_offline
                FROM messages
                WHERE to_user = ? AND read = ?
                ORDER BY timestamp DESC
                """
                params = [username, 0 if unread_only else 1]
                
                if limit:
                    query += " LIMIT ?"
                    params.append(limit)
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                messages = []
                for row in rows:
                    messages.append({
                        "id": row[0],
                        "from": row[1],
                        "to": row[2],
                        "content": row[3],
                        "timestamp": row[4],
                        "read": bool(row[5]),
                        "delivered_while_offline": bool(row[6])
                    })
                return messages
        except Exception as e:
            self.logger.error(f"Failed to get messages for user {username}: {e}")
            return []
    
    def mark_messages_as_read(self, message_ids):
        """Mark messages as read.
        
        Args:
            message_ids (list): List of message IDs to mark as read
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not message_ids:
            return True
            
        try:
            with self.lock:
                cursor = self.conn.cursor()
                
                # Convert list to comma-separated string for SQL IN clause
                id_str = ','.join('?' for _ in message_ids)
                
                cursor.execute(f"UPDATE messages SET read = 1 WHERE id IN ({id_str})", message_ids)
                self.conn.commit()
                return True
        except Exception as e:
            self.logger.error(f"Failed to mark messages as read: {e}")
            return False
    
    def delete_messages(self, message_ids):
        """Delete messages.
        
        Args:
            message_ids (list): List of message IDs to delete
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not message_ids:
            return True
            
        try:
            with self.lock:
                cursor = self.conn.cursor()
                
                # Convert list to comma-separated string for SQL IN clause
                id_str = ','.join('?' for _ in message_ids)
                
                cursor.execute(f"DELETE FROM messages WHERE id IN ({id_str})", message_ids)
                self.conn.commit()
                return True
        except Exception as e:
            self.logger.error(f"Failed to delete messages: {e}")
            return False
    
    def set_user_active(self, username, active=True):
        """Set a user's active status.
        
        Args:
            username (str): Username
            active (bool, optional): Whether the user is active
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                
                if active:
                    # Add or update user in active_users table
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO active_users (username, last_active)
                        VALUES (?, ?)
                        """,
                        (username, int(time.time()))
                    )
                else:
                    # Remove user from active_users table
                    cursor.execute("DELETE FROM active_users WHERE username = ?", (username,))
                
                self.conn.commit()
                return True
        except Exception as e:
            self.logger.error(f"Failed to set user {username} active status to {active}: {e}")
            return False
    
    def is_user_active(self, username):
        """Check if a user is active.
        
        Args:
            username (str): Username
            
        Returns:
            bool: True if user is active, False otherwise
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute("SELECT 1 FROM active_users WHERE username = ?", (username,))
                return cursor.fetchone() is not None
        except Exception as e:
            self.logger.error(f"Failed to check if user {username} is active: {e}")
            return False
    
    def get_active_users(self):
        """Get all active users.
        
        Returns:
            list: List of active usernames
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute("SELECT username FROM active_users")
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Failed to get active users: {e}")
            return []
    
    def log_operation(self, operation_type, data):
        """Log an operation for replication.
        
        Args:
            operation_type (str): Type of operation
            data (dict): Operation data
            
        Returns:
            int: Operation ID or -1 if failed
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                
                cursor.execute(
                    """
                    INSERT INTO operation_log (operation_type, timestamp, data, applied)
                    VALUES (?, ?, ?, 1)
                    """,
                    (operation_type, int(time.time()), json.dumps(data))
                )
                
                operation_id = cursor.lastrowid
                self.conn.commit()
                return operation_id
        except Exception as e:
            self.logger.error(f"Failed to log operation {operation_type}: {e}")
            return -1
    
    def get_pending_operations(self):
        """Get all pending operations for replication.
        
        Returns:
            list: List of operation dictionaries
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute(
                    """
                    SELECT id, operation_type, timestamp, data
                    FROM operation_log
                    WHERE applied = 0
                    ORDER BY timestamp
                    """
                )
                
                operations = []
                for row in cursor.fetchall():
                    operations.append({
                        "id": row[0],
                        "operation_type": row[1],
                        "timestamp": row[2],
                        "data": json.loads(row[3])
                    })
                return operations
        except Exception as e:
            self.logger.error(f"Failed to get pending operations: {e}")
            return []
    
    def mark_operation_as_applied(self, operation_id):
        """Mark an operation as applied.
        
        Args:
            operation_id (int): Operation ID
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                cursor.execute(
                    "UPDATE operation_log SET applied = 1 WHERE id = ?",
                    (operation_id,)
                )
                self.conn.commit()
                return True
        except Exception as e:
            self.logger.error(f"Failed to mark operation {operation_id} as applied: {e}")
            return False
    
    def get_full_state(self):
        """Get the full server state for state transfer.
        
        Returns:
            dict: Full server state
        """
        try:
            with self.lock:
                # Get all users
                users = self.get_all_users()
                
                # Get all messages
                cursor = self.conn.cursor()
                cursor.execute(
                    """
                    SELECT id, from_user, to_user, content, timestamp, read, delivered_while_offline
                    FROM messages
                    """
                )
                
                messages = []
                for row in cursor.fetchall():
                    messages.append({
                        "id": row[0],
                        "from": row[1],
                        "to": row[2],
                        "content": row[3],
                        "timestamp": row[4],
                        "read": bool(row[5]),
                        "delivered_while_offline": bool(row[6])
                    })
                
                # Get active users
                active_users = self.get_active_users()
                
                # Get operation log
                cursor.execute(
                    """
                    SELECT id, operation_type, timestamp, data, applied
                    FROM operation_log
                    ORDER BY timestamp
                    """
                )
                
                operations = []
                for row in cursor.fetchall():
                    operations.append({
                        "id": row[0],
                        "operation_type": row[1],
                        "timestamp": row[2],
                        "data": json.loads(row[3]),
                        "applied": bool(row[4])
                    })
                
                return {
                    "users": users,
                    "messages": messages,
                    "active_users": active_users,
                    "operations": operations
                }
        except Exception as e:
            self.logger.error(f"Failed to get full state: {e}")
            return {"users": [], "messages": [], "active_users": [], "operations": []}
    
    def apply_full_state(self, state):
        """Apply a full state received during state transfer.
        
        Args:
            state (dict): Full server state
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with self.lock:
                cursor = self.conn.cursor()
                
                # Begin transaction
                self.conn.execute("BEGIN TRANSACTION")
                
                # Clear existing data
                cursor.execute("DELETE FROM users")
                cursor.execute("DELETE FROM messages")
                cursor.execute("DELETE FROM active_users")
                cursor.execute("DELETE FROM operation_log")
                
                # Insert users
                for user in state["users"]:
                    cursor.execute(
                        "INSERT INTO users (username, password_hash, settings) VALUES (?, ?, ?)",
                        (user["username"], user["password_hash"], json.dumps(user["settings"]))
                    )
                
                # Insert messages
                for msg in state["messages"]:
                    cursor.execute(
                        """
                        INSERT INTO messages 
                        (id, from_user, to_user, content, timestamp, read, delivered_while_offline)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            msg["id"], 
                            msg["from"], 
                            msg["to"], 
                            msg["content"], 
                            msg["timestamp"], 
                            1 if msg["read"] else 0, 
                            1 if msg["delivered_while_offline"] else 0
                        )
                    )
                
                # Insert active users
                for username in state["active_users"]:
                    cursor.execute(
                        "INSERT INTO active_users (username, last_active) VALUES (?, ?)",
                        (username, int(time.time()))
                    )
                
                # Insert operations
                for op in state["operations"]:
                    cursor.execute(
                        """
                        INSERT INTO operation_log (id, operation_type, timestamp, data, applied)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            op["id"],
                            op["operation_type"],
                            op["timestamp"],
                            json.dumps(op["data"]),
                            1 if op["applied"] else 0
                        )
                    )
                
                # Commit transaction
                self.conn.commit()
                return True
        except Exception as e:
            self.logger.error(f"Failed to apply full state: {e}")
            # Rollback transaction
            self.conn.rollback()
            return False