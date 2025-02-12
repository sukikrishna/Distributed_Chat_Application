import pytest
import socket
import threading
import time
from unittest.mock import Mock, patch
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.custom_protocol.custom_protocol import CustomWireProtocol

@pytest.fixture
def protocol():
    return CustomWireProtocol()

def test_protocol_encode_decode(protocol):
    cmd = CustomWireProtocol.CMD_LOGIN
    payload = ["testuser", "password123"]
    message = protocol.encode_message(cmd, payload)
    total_length, decoded_cmd, decoded_payload = protocol.decode_message(message)
    assert decoded_cmd == cmd
    assert total_length == len(message)

def test_encode_list_payload(protocol):
    cmd = CustomWireProtocol.CMD_DELETE_MESSAGES
    payload = [[1, 2, 3]]
    message = protocol.encode_message(cmd, payload)
    total_length, decoded_cmd, _ = protocol.decode_message(message)
    assert decoded_cmd == cmd
    assert total_length == len(message)

# def test_decode_string(protocol):
#     test_str = "Hello, World!"
#     payload = protocol.encode_message(CustomWireProtocol.CMD_SEND, [test_str])
#     _, _, decoded_payload = protocol.decode_message(payload)
#     decoded_str, _ = protocol.decode_string(decoded_payload[2:])
#     assert decoded_str == test_str

def test_success_response(protocol):
    success = True
    msg = "Success message"
    payload = protocol.encode_message(CustomWireProtocol.CMD_LOGIN, [success, msg])
    _, _, decoded_payload = protocol.decode_message(payload)
    decoded_success, decoded_msg, _ = protocol.decode_success_response(decoded_payload)
    assert decoded_success == success
    assert decoded_msg == msg