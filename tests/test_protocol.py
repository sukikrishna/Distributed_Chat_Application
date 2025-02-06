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

def test_protocol_invalid_decoding():
    """Tests protocol decoding failure on invalid input."""
    with pytest.raises(Exception):
        CustomProtocol.decode(b"invalid data")
    
    with pytest.raises(Exception):
        JSONProtocol.decode(b"not a json string")
