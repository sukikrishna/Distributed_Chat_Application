import struct

class CustomProtocol:
    """Custom binary protocol for encoding and decoding messages."""
    
    OP_CREATE_ACCOUNT = 1
    OP_LOGIN = 2
    OP_SEND_MESSAGE = 3
    OP_READ_MESSAGES = 4
    
    @staticmethod
    def encode(opcode, username, payload):
        """Encodes a message using a custom binary format.
        
        Args:
            opcode (int): Operation code.
            username (str): Username.
            payload (str): Additional message data.
        
        Returns:
            bytes: Encoded binary message.
        """
        username_bytes = username.encode('utf-8')
        payload_bytes = payload.encode('utf-8')
        header = struct.pack('!B B I', opcode, len(username_bytes), len(payload_bytes))
        return header + username_bytes + payload_bytes
    
    @staticmethod
    def decode(data):
        """Decodes a binary message into readable components.
        
        Args:
            data (bytes): Encoded binary message.
        
        Returns:
            tuple: Decoded (opcode, username, payload).
        """
        opcode, username_length, payload_length = struct.unpack('!B B I', data[:6])
        username = data[6:6+username_length].decode('utf-8')
        payload = data[6+username_length:6+username_length+payload_length].decode('utf-8')
        return opcode, username, payload
    
    @staticmethod
    def encode_response(success, data=""):
        """Encodes a response message.
        
        Args:
            success (bool): Whether the request was successful.
            data (str, optional): Additional response data.
        
        Returns:
            bytes: Encoded response message.
        """
        response = "1" if success else "0"
        response += f"|{data}" if data else ""
        return response.encode('utf-8')
    
    @staticmethod
    def decode_response(data):
        """Decodes a response message.
        
        Args:
            data (bytes): Encoded response message.
        
        Returns:
            tuple: Success status and response payload.
        """
        response = data.decode('utf-8')
        success = response[0] == "1"
        payload = response[2:] if "|" in response else ""
        return success, payload
