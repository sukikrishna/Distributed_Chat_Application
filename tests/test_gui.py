import pytest
from PyQt5.QtWidgets import QApplication
from gui import ChatGUI

@pytest.fixture(scope="module")
def app():
    """Creates a QApplication instance for testing."""
    return QApplication([])

@pytest.fixture
def gui(app):
    """Provides a ChatGUI instance for testing."""
    return ChatGUI()

def test_gui_initialization(gui):
    """Tests whether the GUI initializes properly."""
    assert gui.windowTitle() == "Chat Application"

def test_gui_protocol_selection(gui):
    """Tests protocol selection in the GUI."""
    gui.protocol_select.setCurrentIndex(1)  # Select JSON Protocol
    assert gui.protocol_select.currentText() == "JSON Protocol"

def test_gui_login(gui, monkeypatch):
    """Tests login behavior from the GUI."""
    monkeypatch.setattr(gui, "login", lambda: gui.chat_display.append("Login Success"))
    gui.login()
    assert "Login Success" in gui.chat_display.toPlainText()

def test_gui_send_message(gui, monkeypatch):
    """Tests sending messages from the GUI."""
    monkeypatch.setattr(gui, "send_message", lambda: gui.chat_display.append("Message Sent"))
    gui.send_message()
    assert "Message Sent" in gui.chat_display.toPlainText()
