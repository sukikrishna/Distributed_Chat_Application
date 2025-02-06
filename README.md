# Chat Application (Starter Code)

## Overview
This is a client-server chat application that supports two implementations for message communication:
1. **Custom Binary Protocol (Efficient & Minimal Overhead)**
2. **JSON Protocol (Readable & Easy to Debug)**

The application enables:
- User authentication (account creation & login)
- Real-time messaging between clients
- PyQt-based GUI for a seamless chat experience
- Dynamic configuration via GUI (no manual file editing required)
- Full unit test coverage using `pytest`

---

## **Project Structure**
```
chat_app/
│── src/
│   ├── server.py            # Chat server implementation
│   ├── client.py            # Chat client implementation
│   ├── protocol.py          # Custom Binary Protocol implementation
│   ├── json_protocol.py     # JSON-based Protocol implementation
│   ├── database.py          # Database handling (SQLite)
│   ├── config.py            # Dynamic Configuration Handling
│   ├── gui.py               # PyQt GUI with integrated settings panel
│   ├── logger.py            # Logging utilities
│   ├── utils.py             # Helper functions
│── tests/
│   ├── test_server.py       # Unit tests for server
│   ├── test_client.py       # Unit tests for client
│   ├── test_protocol.py     # Unit tests for protocol
│   ├── test_database.py     # Unit tests for database
│   ├── test_gui.py          # Unit tests for GUI
│── requirements.txt         # Dependencies
│── README.md                # Documentation & setup guide
│── engineering_notebook.md  # Analysis of protocols & performance
│── .gitignore               # Ignored files
```

---

## **1. Setup & Installation**

### **1.1 Install Dependencies**
Run the following command to install all required dependencies:
```sh
pip install -r requirements.txt
```

### **1.2 Start the Chat Server**
```sh
python src/server.py
```
The server will start based on the configuration settings in `config.json`. If the file does not exist, default values will be used.

### **1.3 Run the GUI Client**
```sh
python src/gui.py
```
This will open the chat interface where users can log in, send messages, and adjust settings.

---

## **2. Configuring the Application**
The application is **fully configurable via the GUI**:
- Open **`gui.py`**
- Select **protocol** (Custom Binary or JSON)
- Set **server IP and port**
- Save settings (Automatically updates `config.json`)

---

## **3. Running the Two Implementations**
The application provides two protocol implementations for communication:

### **3.1 Custom Binary Protocol (Efficient & Minimal Overhead)**
- Uses a structured binary format for message transmission.
- Faster and more efficient in network usage.
- Suitable for high-performance applications.

### **3.2 JSON Protocol (Readable & Easy to Debug)**
- Uses JSON encoding for message transmission.
- Easier to inspect and debug due to human-readable format.
- Suitable for general applications where efficiency is less critical.

### **3.3 How to Select a Protocol?**
- **From GUI:** Select **Custom Binary Protocol** or **JSON Protocol** before logging in.
- **From Code:** When starting the server/client, change the `use_json` flag:
```python
server = ChatServer(use_json=True)  # JSON Protocol
server = ChatServer(use_json=False)  # Custom Binary Protocol
```

---

## **4. Running Tests**
To ensure everything is working as expected, run:
```sh
pytest tests/
```
This will execute unit tests covering:
- **Server functionality** (`test_server.py`)
- **Client functionality** (`test_client.py`)
- **Protocol encoding & decoding** (`test_protocol.py`)
- **Database operations** (`test_database.py`)
- **GUI interactions** (`test_gui.py`)

---

## **5. Protocol Comparison**
| Feature           | Custom Binary Protocol | JSON Protocol |
|------------------|----------------------|--------------|
| Efficiency      | ✅ Faster & minimal overhead | ❌ Slightly larger messages |
| Readability     | ❌ Not human-readable  | ✅ Easy to inspect |
| Debugging       | ❌ Harder to debug | ✅ Human-readable JSON |
| Use Case        | ✅ High-performance apps | ✅ General applications |

---

## **6. FAQs**
**Q: Can I change the protocol at runtime?**
- Yes, you can select **JSON or Custom Binary Protocol** in the GUI before logging in.

**Q: Where are settings stored?**
- All configuration settings are saved in `config.json` automatically.

**Q: What if the server IP changes?**
- Update it from the **GUI settings panel**.

---
