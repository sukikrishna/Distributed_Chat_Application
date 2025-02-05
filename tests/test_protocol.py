import pytest
from protocol import CustomProtocol
from json_protocol import JSONProtocol

def test_custom_protocol_encoding_decoding():
    """Tests encoding and decoding using the Custom Binary Protocol."""
    encoded = CustomProtocol.encode(CustomProtocol.OP_CREATE_ACCOUNT, "alice", "password123")
    decoded = CustomProtocol.decode(encoded)
    assert decoded == (CustomProtocol.OP_CREATE_ACCOUNT, "alice", "password123")

def test_json_protocol_encoding_decoding():
    """Tests encoding and decoding using the JSON Protocol."""
    encoded = JSONProtocol.encode(JSONProtocol.OP_CREATE_ACCOUNT, "alice", "password123")
    decoded = JSONProtocol.decode(encoded)
    assert decoded == (JSONProtocol.OP_CREATE_ACCOUNT, "alice", "password123")

def test_custom_protocol_response():
    """Tests encoding and decoding of responses using the Custom Binary Protocol."""
    encoded = CustomProtocol.encode_response(True, "Success")
    decoded = CustomProtocol.decode_response(encoded)
    assert decoded == (True, "Success")
    
    encoded = CustomProtocol.encode_response(False, "Error")
    decoded = CustomProtocol.decode_response(encoded)
    assert decoded == (False, "Error")

def test_json_protocol_response():
    """Tests encoding and decoding of responses using the JSON Protocol."""
    encoded = JSONProtocol.encode_response(True, "Success")
    decoded = JSONProtocol.decode_response(encoded)
    assert decoded == (True, "Success")
    
    encoded = JSONProtocol.encode_response(False, "Error")
    decoded = JSONProtocol.decode_response(encoded)
    assert decoded == (False, "Error")
