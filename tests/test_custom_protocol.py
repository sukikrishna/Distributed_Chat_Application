import pytest
import struct

import sys
sys.path.insert(0, "src/custom_protocol")

from custom_protocol import CustomWireProtocol

@pytest.fixture
def protocol():
    return CustomWireProtocol()

def test_encode_string_message(protocol):
    cmd = CustomWireProtocol.CMD_SEND
    payload = ["recipient", "Hello, World!"]
    message = protocol.encode_message(cmd, payload)
    
    # Check header format
    total_length = struct.unpack('!I', message[:4])[0]
    command = struct.unpack('!H', message[4:6])[0]
    
    assert command == cmd
    assert total_length == len(message)

def test_decode_message(protocol):
    cmd = CustomWireProtocol.CMD_SEND
    original_payload = ["recipient", "Hello, World!"]
    message = protocol.encode_message(cmd, original_payload)
    
    total_length, decoded_cmd, payload = protocol.decode_message(message)
    assert total_length == len(message)
    assert decoded_cmd == cmd
    assert len(payload) > 0

def test_encode_decode_string(protocol):
    original = "Test String"
    payload = protocol.encode_message(CustomWireProtocol.CMD_SEND, [original])
    _, _, encoded = protocol.decode_message(payload)
    decoded, remaining = protocol.decode_string(encoded)
    assert decoded == original
    assert len(remaining) == 0

def test_encode_decode_integer_list(protocol):
    original = [1, 2, 3]
    message = protocol.encode_message(CustomWireProtocol.CMD_DELETE_MESSAGES, [original])
    _, _, payload = protocol.decode_message(message)
    count = struct.unpack('!H', payload[:2])[0]
    assert count == len(original)

def test_encode_decode_boolean(protocol):
    cmd = CustomWireProtocol.CMD_LOGIN
    original_payload = [True, "test"]
    message = protocol.encode_message(cmd, original_payload)
    _, _, payload = protocol.decode_message(message)
    success = struct.unpack('!?', payload[:1])[0]
    assert success is True

def test_decode_success_response(protocol):
    success_message = protocol.encode_message(CustomWireProtocol.CMD_LOGIN, [True, "Success"])
    _, _, payload = protocol.decode_message(success_message)
    success, message, remaining = protocol.decode_success_response(payload)
    assert success is True
    assert message == "Success"
    assert len(remaining) == 0

def test_encode_empty_payload(protocol):
    message = protocol.encode_message(CustomWireProtocol.CMD_LOGOUT, [])
    total_length, cmd, payload = protocol.decode_message(message)
    assert total_length == len(message)
    assert cmd == CustomWireProtocol.CMD_LOGOUT
    assert len(payload) == 0

def test_encode_large_string(protocol):
    large_string = "a" * 1000
    message = protocol.encode_message(CustomWireProtocol.CMD_SEND, ["recipient", large_string])
    _, _, payload = protocol.decode_message(message)
    _, payload = protocol.decode_string(payload)  # Skip recipient
    content, _ = protocol.decode_string(payload)
    assert content == large_string

def test_encode_special_characters(protocol):
    special_string = "Hello 🌍 World! ♥ αβγ"
    message = protocol.encode_message(CustomWireProtocol.CMD_SEND, [special_string])
    _, _, payload = protocol.decode_message(message)
    decoded, _ = protocol.decode_string(payload)
    assert decoded == special_string

# def test_decode_invalid_message(protocol):
#     with pytest.raises(Exception):
#         protocol.decode_message(b'invalid')